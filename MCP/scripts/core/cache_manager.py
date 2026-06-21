"""缓存和工具调用管理."""

import asyncio
import time
import hashlib
import json
from typing import Optional, Dict, Any

from .config import config

class CacheManager:
    """缓存管理器 - 响应缓存、工具缓存、上下文缓存."""

    def __init__(self):
        # 响应缓存: {(platform, message_hash): {"result": str, "ts": float, "hits": int}}
        self._response_cache: Dict[tuple, Dict] = {}
        self._cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
        self._lock_response = asyncio.Lock()

        # 工具调用缓存: {(tool_name, args_hash): {"result": str, "ts": float}}
        self._tool_cache: Dict[tuple, Dict] = {}
        self._lock_tool = asyncio.Lock()

        # 上下文缓存: {context_key: {"text": str, "hits": int, "tokens": int, "ts": float}}
        self._context_cache: Dict[str, Dict] = {}
        self._context_cache_stats = {"hits": 0, "misses": 0, "tokens_saved": 0}
        self._lock_context = asyncio.Lock()

    # ── 响应缓存 ─────────────────────────────────────────
    async def get_response(self, platform: str, message: str) -> Optional[str]:
        """获取缓存的响应（线程安全）."""
        msg_hash = hashlib.md5(message.encode()).hexdigest()
        key = (platform, msg_hash)
        async with self._lock_response:
            cached = self._response_cache.get(key)
            if cached and (time.time() - cached["ts"]) < config.cache_ttl:
                cached["hits"] = cached.get("hits", 0) + 1
                self._cache_stats["hits"] += 1
                return f"[缓存] {cached['result']}"
            self._cache_stats["misses"] += 1
            return None

    async def set_response(self, platform: str, message: str, result: str):
        """保存响应到缓存（线程安全）."""
        msg_hash = hashlib.md5(message.encode()).hexdigest()
        key = (platform, msg_hash)
        async with self._lock_response:
            # 清理过期和超限缓存（在锁内同步执行，避免死锁）
            now = time.time()
            expired = [k for k, v in self._response_cache.items() if (now - v["ts"]) > config.cache_ttl]
            for k in expired:
                del self._response_cache[k]
                self._cache_stats["evictions"] += 1
            if len(self._response_cache) > config.cache_max:
                sorted_keys = sorted(self._response_cache.keys(), key=lambda k: self._response_cache[k].get("hits", 0))
                while len(self._response_cache) > config.cache_max:
                    del self._response_cache[sorted_keys.pop(0)]
                    self._cache_stats["evictions"] += 1
            # 保存新条目
            self._response_cache[key] = {"result": result, "ts": time.time(), "hits": 0}

    async def _evict_cache(self):
        """LRU 缓存淘汰."""
        now = time.time()
        # 移除过期
        async with self._lock_response:
            expired = [k for k, v in self._response_cache.items() if (now - v["ts"]) > config.cache_ttl]
            for k in expired:
                del self._response_cache[k]
                self._cache_stats["evictions"] += 1

            # 超限淘汰
            if len(self._response_cache) > config.cache_max:
                sorted_keys = sorted(self._response_cache.keys(), key=lambda k: self._response_cache[k].get("hits", 0))
                while len(self._response_cache) > config.cache_max:
                    del self._response_cache[sorted_keys.pop(0)]
                    self._cache_stats["evictions"] += 1

    async def invalidate_platform(self, platform: str) -> int:
        """清除指定平台的所有缓存."""
        async with self._lock_response:
            keys_to_remove = [k for k in self._response_cache if k[0] == platform]
            for k in keys_to_remove:
                del self._response_cache[k]
            self._cache_stats["evictions"] += len(keys_to_remove)
            return len(keys_to_remove)

    # ── 工具缓存 ─────────────────────────────────────────
    async def get_tool(self, tool_name: str, **kwargs) -> Optional[str]:
        """获取工具调用缓存."""
        args_hash = hashlib.md5(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()
        key = (tool_name, args_hash)
        async with self._lock_tool:
            cached = self._tool_cache.get(key)
            if cached and (time.time() - cached["ts"]) < config.tool_ttl:
                return f"[缓存命中] {cached['result']}"
            return None

    async def set_tool(self, tool_name: str, result: str, **kwargs):
        """保存工具调用结果."""
        args_hash = hashlib.md5(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()
        key = (tool_name, args_hash)
        async with self._lock_tool:
            # 保存新条目
            self._tool_cache[key] = {"result": result, "ts": time.time()}
            # 清理过期
            now = time.time()
            expired = [k for k, v in self._tool_cache.items() if (now - v["ts"]) > config.tool_ttl]
            for k in expired:
                del self._tool_cache[k]
            # 大小限制（LRU）- tool cache 无独立 max 配置，使用固定上限 200
            if len(self._tool_cache) > 200:
                sorted_keys = sorted(self._tool_cache.keys(), key=lambda k: self._tool_cache[k]["ts"])
                while len(self._tool_cache) > 200:
                    del self._tool_cache[sorted_keys.pop(0)]

    # ── 上下文缓存 ───────────────────────────────────────
    def _get_context_key(self, text: str, task: str = "", iteration: int = 0) -> str:
        """生成上下文缓存键."""
        normalized = (task + ":" + str(iteration) + ":" + text.strip().lower()[:200])
        return hashlib.md5(normalized.encode()).hexdigest()

    async def get_context(self, text: str, task: str = "", iteration: int = 0) -> Optional[str]:
        """获取上下文缓存."""
        key = self._get_context_key(text, task, iteration)
        async with self._lock_context:
            entry = self._context_cache.get(key)
            if entry:
                if (time.time() - entry["ts"]) < config.context_ttl:
                    entry["hits"] += 1
                    self._context_cache_stats["hits"] += 1
                    self._context_cache_stats["tokens_saved"] += entry["tokens"]
                    return entry["text"]
                else:
                    # 过期，删除
                    del self._context_cache[key]
            self._context_cache_stats["misses"] += 1
            return None

    async def set_context(self, text: str, task: str = "", iteration: int = 0, tokens: int = 0):
        """保存上下文."""
        key = self._get_context_key(text, task, iteration)
        async with self._lock_context:
            # 清理过期和超限缓存（在锁内同步执行，避免死锁）
            now = time.time()
            expired = [k for k, v in self._context_cache.items() if (now - v["ts"]) > config.context_ttl]
            for k in expired:
                del self._context_cache[k]
            if len(self._context_cache) > config.context_max:
                sorted_keys = sorted(self._context_cache.keys(), key=lambda k: self._context_cache[k]["hits"])
                while len(self._context_cache) > config.context_max:
                    del self._context_cache[sorted_keys.pop(0)]
            # 保存新条目
            if tokens == 0:
                tokens = len(text) // 4
            self._context_cache[key] = {
                "text": text,
                "hits": 0,
                "tokens": tokens,
                "ts": time.time()
            }

    async def _evict_context_cache(self):
        """清理上下文缓存."""
        now = time.time()
        async with self._lock_context:
            expired = [k for k, v in self._context_cache.items() if (now - v["ts"]) > config.context_ttl]
            for k in expired:
                del self._context_cache[k]

            if len(self._context_cache) > config.context_max:
                sorted_keys = sorted(self._context_cache.keys(), key=lambda k: self._context_cache[k]["hits"])
                while len(self._context_cache) > config.context_max:
                    del self._context_cache[sorted_keys.pop(0)]

    async def get_stats(self) -> dict:
        """获取缓存统计."""
        async with self._lock_response:
            response_size = len(self._response_cache)
            response_hits = self._cache_stats["hits"]
            response_misses = self._cache_stats["misses"]
        async with self._lock_tool:
            tool_size = len(self._tool_cache)
        async with self._lock_context:
            context_size = len(self._context_cache)
            context_hits = self._context_cache_stats["hits"]
            tokens_saved = self._context_cache_stats["tokens_saved"]
        return {
            "response_cache_size": response_size,
            "tool_cache_size": tool_size,
            "context_cache_size": context_size,
            "response_hits": response_hits,
            "response_misses": response_misses,
            "context_hits": context_hits,
            "tokens_saved": tokens_saved,
        }

    async def clear_all(self):
        """清除所有缓存（线程安全）."""
        async with self._lock_response:
            self._response_cache.clear()
        async with self._lock_tool:
            self._tool_cache.clear()
        async with self._lock_context:
            self._context_cache.clear()

# 全局缓存实例
cache_manager = CacheManager()

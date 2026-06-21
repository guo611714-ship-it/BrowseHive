"""API Key 池 — 多Key轮转 + 独立限流 + 429自动切换"""

import time
import asyncio
import logging
import threading
from typing import List, Optional, Dict, Any
from . import RateLimiter

logger = logging.getLogger(__name__)


class APIKeyPool:
    """多Key轮转池，每个Key独立限流，429自动切换"""

    def __init__(self, keys: List[str], provider: str = "nvidia",
                 interval: float = 2.0, window: int = 60, max_requests: int = 8,
                 account_max_requests: int = 60):
        if not keys:
            raise ValueError("至少需要一个 API Key")

        self.provider = provider
        self._keys = list(keys)  # 复制，防止外部修改
        self._current = 0
        self._limiters: Dict[str, RateLimiter] = {}
        self._disabled_until: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()

        # 账号级限流：同账号的Key共享配额
        self._account_max_requests = account_max_requests
        self._account_timestamps: Dict[str, list] = {}  # account_id -> [timestamps]
        self._account_interval = 1.5  # 账号级最小间隔

        # 项目级子池（可选）
        self._sub_pools: Dict[str, "APIKeyPool"] = {}

        for key in keys:
            self._limiters[key] = RateLimiter(
                interval=interval, window=window, max_requests=max_requests
            )

        logger.info(f"APIKeyPool 初始化: {len(keys)} 个Key, provider={provider}, "
                     f"per_key={max_requests}/min, account={account_max_requests}/min")

    def _mask_key(self, key: str) -> str:
        if len(key) > 12:
            return key[:8] + "..." + key[-4:]
        return key[:4] + "..."

    def _cleanup_expired(self):
        """清理过期的禁用条目"""
        with self._sync_lock:
            now = time.time()
            expired = [k for k, v in self._disabled_until.items() if now >= v]
            for k in expired:
                del self._disabled_until[k]

    def _get_available_keys(self) -> List[str]:
        self._cleanup_expired()
        now = time.time()
        return [k for k in self._keys if now >= self._disabled_until.get(k, 0)]

    def next_key(self) -> Optional[str]:
        """获取下一个可用的Key（轮转 + 跳过禁用 + 账号级限流）"""
        available = self._get_available_keys()
        if not available:
            return None

        idx = self._current % len(available)
        self._current += 1
        key = available[idx]

        # 检查账号级限流（不记录时间戳，成功返回时才记录）
        account_msg = self._check_account_limit()
        if account_msg:
            logger.warning(f"[账号限流] {account_msg}")
            return None

        # 检查Key级限流（不再重新检查账号限流，避免双重消耗）
        limiter = self._limiters[key]
        rate_msg = limiter.check(self.provider)
        if rate_msg:
            for _ in range(len(available) - 1):
                key = available[self._current % len(available)]
                self._current += 1
                limiter = self._limiters[key]
                rate_msg = limiter.check(self.provider)
                if not rate_msg:
                    # Key级通过，记录账号时间戳
                    self._record_account_timestamp()
                    return key
            return None

        # 成功获取Key，记录账号时间戳
        self._record_account_timestamp()
        return key

    def _check_account_limit(self) -> Optional[str]:
        """检查账号级请求配额（不记录时间戳，仅检查）"""
        now = time.time()
        if "global" not in self._account_timestamps:
            self._account_timestamps["global"] = []

        with self._sync_lock:
            # 清理过期记录
            self._account_timestamps["global"] = [
                t for t in self._account_timestamps["global"] if (now - t) < 60
            ]

            # 账号级最小间隔
            if self._account_timestamps["global"]:
                last = self._account_timestamps["global"][-1]
                if (now - last) < self._account_interval:
                    return f"账号请求过快，请等待{self._account_interval - (now - last):.1f}秒"

            # 账号级窗口请求数
            if len(self._account_timestamps["global"]) >= self._account_max_requests:
                return f"账号窗口内请求数已达上限({self._account_max_requests}/min)"

        return None

    def _record_account_timestamp(self):
        """记录账号级请求时间戳（仅在成功获取Key后调用）"""
        with self._sync_lock:
            now = time.time()
            if "global" not in self._account_timestamps:
                self._account_timestamps["global"] = []
            self._account_timestamps["global"].append(now)

    def peek_key(self) -> Optional[str]:
        """获取下一个可用Key但不检查限流（用于last-iteration避免phantom timestamp）"""
        available = self._get_available_keys()
        if not available:
            return None
        return available[self._current % len(available)]

    async def next_key_async(self) -> Optional[str]:
        async with self._lock:
            return self.next_key()

    async def peek_key_async(self) -> Optional[str]:
        async with self._lock:
            return self.peek_key()

    def report_429(self, key: str, retry_after: float = 60.0):
        with self._sync_lock:
            self._disabled_until[key] = time.time() + retry_after
            available = len(self._get_available_keys())
            logger.warning(
                f"Key {self._mask_key(key)} 被429禁用 {retry_after:.0f}s "
                f"(剩余可用: {available}/{len(self._keys)})"
            )

    def report_success(self, key: str):
        """报告请求成功"""
        with self._sync_lock:
            pass  # RateLimiter 已在 next_key() 的 check() 中记录

    def report_auth_failure(self, key: str):
        """报告认证失败（401/403），长期禁用该Key"""
        with self._sync_lock:
            self._disabled_until[key] = time.time() + 3600  # 1小时
            logger.error(f"Key {self._mask_key(key)} 认证失败，禁用1小时")

    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        self._cleanup_expired()
        stats: Dict[str, Any] = {
            "total_keys": len(self._keys),
            "available_keys": len(self._get_available_keys()),
            "disabled_keys": [
                {"key": self._mask_key(k), "remaining": max(0, v - now)}
                for k, v in self._disabled_until.items()
            ],
            "per_key": {},
            "sub_pools": list(self._sub_pools.keys()),
        }
        for key in self._keys:
            limiter_stats = self._limiters[key].get_stats(self.provider)
            stats["per_key"][self._mask_key(key)] = {
                **limiter_stats,
                "disabled": now < self._disabled_until.get(key, 0)
            }
        return stats

    # ── 项目级子池 ──

    def create_sub_pool(self, project_id: str, key_count: int = 3,
                        project_max_requests: int = 15) -> "APIKeyPool":
        """从主池中分配 key_count 个Key给项目子池。

        子池独立限流，但共享账号级配额。
        project_max_requests: 该项目每分钟最大请求数。
        """
        if project_id in self._sub_pools:
            return self._sub_pools[project_id]

        available = [k for k in self._keys if k not in self._assigned_keys()]
        assigned = available[:key_count]
        if not assigned:
            raise ValueError(f"无可用Key分配给项目 {project_id}")

        sub = APIKeyPool(
            keys=assigned, provider=self.provider,
            interval=2.0, window=60, max_requests=8,
            account_max_requests=project_max_requests,
        )
        # 子池不维护账号级限流（由主池统一管理）
        sub._account_timestamps = {}
        self._sub_pools[project_id] = sub
        logger.info(f"子池 {project_id}: {len(assigned)} 个Key, "
                     f"project_max={project_max_requests}/min")
        return sub

    def get_sub_pool(self, project_id: str) -> Optional["APIKeyPool"]:
        """获取项目子池"""
        return self._sub_pools.get(project_id)

    def _assigned_keys(self) -> set:
        """已分配给子池的Key集合"""
        assigned = set()
        for sub in self._sub_pools.values():
            assigned.update(sub._keys)
        return assigned

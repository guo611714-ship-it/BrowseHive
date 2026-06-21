"""CacheManager 单元测试."""

import asyncio
import hashlib
import time
import pytest
from core.cache_manager import CacheManager


def _make_key(platform: str, message: str) -> tuple:
    """构造缓存 key."""
    return (platform, hashlib.md5(message.encode()).hexdigest())


@pytest.mark.asyncio
async def test_response_cache_hit():
    """缓存命中：set 后 get 应返回带 [缓存] 前缀的结果."""
    cm = CacheManager()
    await cm.set_response("doubao", "hello", "world")
    result = await cm.get_response("doubao", "hello")
    assert result is not None
    assert "[缓存]" in result
    assert "world" in result


@pytest.mark.asyncio
async def test_response_cache_miss():
    """缓存未命中：未 set 的 key 返回 None."""
    cm = CacheManager()
    result = await cm.get_response("doubao", "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_response_cache_different_platform():
    """不同平台的相同消息应独立缓存."""
    cm = CacheManager()
    await cm.set_response("doubao", "msg", "doubao_result")
    await cm.set_response("deepseek", "msg", "deepseek_result")
    r1 = await cm.get_response("doubao", "msg")
    r2 = await cm.get_response("deepseek", "msg")
    assert "doubao_result" in r1
    assert "deepseek_result" in r2


@pytest.mark.asyncio
async def test_response_cache_expiration():
    """缓存过期后应返回 None."""
    cm = CacheManager()
    await cm.set_response("doubao", "msg", "result")
    key = _make_key("doubao", "msg")
    cm._response_cache[key]["ts"] = time.time() - 9999
    result = await cm.get_response("doubao", "msg")
    assert result is None


@pytest.mark.asyncio
async def test_response_cache_lru_eviction():
    """缓存超过 max 时应触发 LRU 淘汰."""
    cm = CacheManager()
    from core.config import Config
    cfg = Config()
    # 填充超过上限
    for i in range(cfg.cache_max + 10):
        await cm.set_response("doubao", f"msg_{i}", f"result_{i}")
    # 缓存大小不应超过 cache_max + 1（淘汰在下次 set 时触发）
    assert len(cm._response_cache) <= cfg.cache_max + 1


@pytest.mark.asyncio
async def test_response_cache_stats():
    """缓存统计：hits/misses 应正确计数."""
    cm = CacheManager()
    await cm.set_response("doubao", "hit_msg", "ok")
    await cm.get_response("doubao", "hit_msg")  # hit
    await cm.get_response("doubao", "miss_msg")  # miss
    stats = await cm.get_stats()
    assert stats["response_hits"] >= 1
    assert stats["response_misses"] >= 1


@pytest.mark.asyncio
async def test_tool_cache_hit_miss():
    """工具缓存命中/未命中."""
    cm = CacheManager()
    await cm.set_tool("search", "result_data", query="test")
    hit = await cm.get_tool("search", query="test")
    assert hit is not None
    assert "result_data" in hit

    miss = await cm.get_tool("search", query="other")
    assert miss is None


@pytest.mark.asyncio
async def test_tool_cache_expiration():
    """工具缓存过期."""
    cm = CacheManager()
    await cm.set_tool("search", "data", query="q")
    # 直接篡改缓存中的时间戳
    for key, val in cm._tool_cache.items():
        if key[0] == "search":
            val["ts"] = time.time() - 9999
            break
    result = await cm.get_tool("search", query="q")
    assert result is None


@pytest.mark.asyncio
async def test_context_cache_hit_miss():
    """上下文缓存命中/未命中."""
    cm = CacheManager()
    await cm.set_context("some context text", task="test", tokens=100)
    hit = await cm.get_context("some context text", task="test")
    assert hit is not None
    assert "some context text" in hit

    miss = await cm.get_context("different text", task="test")
    assert miss is None


@pytest.mark.asyncio
async def test_invalidate_platform():
    """清除指定平台缓存."""
    cm = CacheManager()
    await cm.set_response("doubao", "a", "1")
    await cm.set_response("doubao", "b", "2")
    await cm.set_response("deepseek", "a", "3")
    removed = await cm.invalidate_platform("doubao")
    assert removed == 2
    # deepseek 缓存应保留
    r = await cm.get_response("deepseek", "a")
    assert r is not None


@pytest.mark.asyncio
async def test_clear_all():
    """清除所有缓存."""
    cm = CacheManager()
    await cm.set_response("doubao", "x", "y")
    await cm.set_tool("t", "r", arg=1)
    await cm.clear_all()
    assert await cm.get_response("doubao", "x") is None
    assert await cm.get_tool("t", arg=1) is None


@pytest.mark.asyncio
async def test_response_cache_overwrite():
    """覆盖已有 key 不会丢失数据（新值覆盖旧值）."""
    cm = CacheManager()
    await cm.set_response("doubao", "key", "old_value")
    await cm.set_response("doubao", "key", "new_value")
    result = await cm.get_response("doubao", "key")
    assert "new_value" in result

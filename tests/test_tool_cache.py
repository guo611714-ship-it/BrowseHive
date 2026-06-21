"""Tests for tool caching decorator and batch_js tool"""

import asyncio
import time
import pytest

from agent.tools.tool_registry import cached, clear_cache, cache_stats


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# cached decorator tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(autouse=True)
def _clean_cache():
    """Clear cache before and after each test."""
    clear_cache()
    yield
    clear_cache()


class TestCachedDecorator:
    """Tests for the @cached tool result caching decorator."""

    @pytest.mark.asyncio
    async def test_cached_returns_same_result(self):
        """Second call with same args returns cached result."""
        call_count = 0

        @cached(ttl=60)
        async def my_tool(x: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"value": x * 2}

        r1 = await my_tool(5)
        r2 = await my_tool(5)
        assert r1 == {"value": 10}
        assert r2 == {"value": 10}
        assert call_count == 1  # only called once

    @pytest.mark.asyncio
    async def test_cached_different_args_different_cache(self):
        """Different arguments produce different cache entries."""
        call_count = 0

        @cached(ttl=60)
        async def my_tool(x: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"value": x}

        r1 = await my_tool(1)
        r2 = await my_tool(2)
        assert r1 == {"value": 1}
        assert r2 == {"value": 2}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_cached_ttl_expiry(self):
        """Cache expires after TTL seconds."""
        call_count = 0

        @cached(ttl=0)  # 0秒TTL = 立即过期
        async def my_tool(x: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"value": x}

        await my_tool(5)
        time.sleep(0.01)
        await my_tool(5)
        assert call_count == 2  # expired, called again

    @pytest.mark.asyncio
    async def test_cached_kwargs(self):
        """Cache works with keyword arguments."""
        call_count = 0

        @cached(ttl=60)
        async def my_tool(a: int, b: str = "hello") -> dict:
            nonlocal call_count
            call_count += 1
            return {"a": a, "b": b}

        r1 = await my_tool(1, b="world")
        r2 = await my_tool(1, b="world")
        assert r1 == {"a": 1, "b": "world"}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_clear_cache_specific(self):
        """clear_cache(tool_name) clears only matching entries."""
        @cached(ttl=60)
        async def tool_a() -> dict:
            return {"a": 1}

        @cached(ttl=60)
        async def tool_b() -> dict:
            return {"b": 2}

        await tool_a()
        await tool_b()
        assert cache_stats()["entries"] == 2

        clear_cache("tool_a")
        assert cache_stats()["entries"] == 1

    @pytest.mark.asyncio
    async def test_clear_cache_all(self):
        """clear_cache() with no args clears everything."""
        @cached(ttl=60)
        async def tool_a() -> dict:
            return {"a": 1}

        await tool_a()
        assert cache_stats()["entries"] == 1

        clear_cache()
        assert cache_stats()["entries"] == 0

    @pytest.mark.asyncio
    async def test_cache_preserves_function_name(self):
        """Cached wrapper preserves function metadata."""
        @cached(ttl=60)
        async def my_tool() -> dict:
            """My tool docstring."""
            return {}

        assert my_tool.__name__ == "my_tool"
        assert my_tool.__doc__ == "My tool docstring."

    @pytest.mark.asyncio
    async def test_cache_ttl_attribute(self):
        """Wrapper exposes _cache_ttl attribute."""
        @cached(ttl=120)
        async def my_tool() -> dict:
            return {}

        assert hasattr(my_tool, "_cache_ttl")
        assert my_tool._cache_ttl == 120

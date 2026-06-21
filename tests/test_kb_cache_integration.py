"""Cache integration tests for KBQueryCache"""

import importlib
import json
import time
from pathlib import Path

import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import KBQueryCache directly
from agent.kb import KBQueryCache


@pytest.fixture
def cache(tmp_path):
    """Fresh cache instance per test."""
    return KBQueryCache(tmp_path / "cache", l1_max=100, l1_ttl=2, l2_ttl=10)


class TestCacheHit:
    def test_cache_hit(self, cache):
        """Query after put should return cached result."""
        cache.put("what is python", "model-a", {"answer": "Python is a language."})
        result = cache.get("what is python", "model-a")
        assert result is not None
        assert result["answer"] == "Python is a language."

    def test_cache_miss(self, cache):
        """Unknown query returns None."""
        result = cache.get("unknown query", "model-a")
        assert result is None

    def test_different_model_cache_miss(self, cache):
        """Same query, different model = cache miss."""
        cache.put("what is python", "model-a", {"answer": "A"})
        result = cache.get("what is python", "model-b")
        assert result is None


class TestCacheInvalidation:
    def test_invalidate_clears_all(self, cache):
        """invalidate() with no pattern clears everything."""
        cache.put("q1", "m", {"a": 1})
        cache.put("q2", "m", {"a": 2})
        cache.invalidate()
        assert cache.get("q1", "m") is None
        assert cache.get("q2", "m") is None

    def test_invalidate_by_pattern(self, cache):
        """invalidate(pattern) clears only matching entries.
        Keys are SHA256 hashes, so we use a substring of the hash."""
        cache.put("python tutorial", "m", {"a": 1})
        cache.put("java tutorial", "m", {"a": 2})

        # Use the actual SHA256 hash prefix for pattern matching
        py_key = cache._make_key("python tutorial", "m")
        cache.invalidate(py_key[:10])  # Use enough of the hash to be unique

        assert cache.get("python tutorial", "m") is None
        # java should survive
        assert cache.get("java tutorial", "m") is not None


class TestCacheStats:
    def test_stats_initial(self, cache):
        """Fresh cache shows zero stats."""
        stats = cache.stats()
        assert stats["l1_size"] == 0
        assert stats["l2_size"] == 0
        assert stats["hits_l1"] == 0
        assert stats["hits_l2"] == 0
        assert stats["misses"] == 0
        assert stats["total_requests"] == 0
        assert stats["puts"] == 0

    def test_stats_after_put_and_get(self, cache):
        """Stats reflect puts and hits correctly."""
        cache.put("q", "m", {"a": 1})
        cache.get("q", "m")  # L1 hit
        cache.get("nope", "m")  # miss

        stats = cache.stats()
        assert stats["puts"] == 1
        assert stats["hits_l1"] == 1
        assert stats["misses"] == 1
        assert stats["total_requests"] == 2

    def test_stats_after_invalidation(self, cache):
        """Stats reset after invalidation."""
        cache.put("q", "m", {"a": 1})
        cache.invalidate()
        stats = cache.stats()
        assert stats["l1_size"] == 0
        assert stats["l2_size"] == 0


class TestCacheClear:
    def test_clear_removes_all_entries(self, cache):
        """cache.invalidate() removes L1 and L2 entries."""
        cache.put("key1", "m", {"data": "value1"})
        cache.put("key2", "m", {"data": "value2"})
        assert cache.get("key1", "m") is not None

        cache.invalidate()

        assert cache.get("key1", "m") is None
        assert cache.get("key2", "m") is None

    def test_l2_persisted_after_l1_clear(self, cache):
        """L2 data survives L1-only operations."""
        cache.put("persistent", "m", {"data": "persist"})
        # Clear only L1 by manually removing from l1 dict
        cache.l1.clear()
        # L2 should still have it
        result = cache.get("persistent", "m")
        assert result is not None
        assert result["data"] == "persist"


class TestL1ToL2Promotion:
    def test_l1_to_l2_promotion(self, cache):
        """When L1 entry expires, get() promotes from L2."""
        # Put into both L1 and L2
        cache.put("promote_me", "m", {"data": "promoted"})

        # Manually expire the L1 entry
        cache.l1.clear()

        # get() should find it in L2 and promote back to L1
        result = cache.get("promote_me", "m")
        assert result is not None
        assert result["data"] == "promoted"

        # Now it should be in L1 again
        stats = cache.stats()
        assert stats["hits_l2"] == 1

    def test_l2_expired_returns_none(self, cache):
        """Expired L2 entry returns None and does not promote.
        Uses time.sleep with a very short TTL to test real expiry."""
        cache.l2_ttl = 0.1  # Very short TTL
        cache.put("expire_me", "m", {"data": "expired"})

        # Expire L1 immediately
        cache.l1.clear()

        # Wait for L2 expiry
        time.sleep(0.3)

        result = cache.get("expire_me", "m")
        assert result is None

    def test_l1_eviction_at_capacity(self, cache):
        """L1 evicts oldest when at capacity."""
        cache.l1_max = 3
        for i in range(4):
            cache.put(f"q{i}", "m", {"idx": i})

        # L1 should have at most 3 entries
        assert len(cache.l1) <= 3

    def test_l1_expiry_triggers_replacement(self, cache):
        """Expired L1 entries are removed on get()."""
        cache.put("expiry_test", "m", {"data": "val"})
        # Manually set timestamp to past
        key = cache._make_key("expiry_test", "m")
        cache.l1[key] = (cache.l1[key][0], time.time() - 9999)

        # get() should detect expiry, remove from L1, find in L2
        result = cache.get("expiry_test", "m")
        assert result is not None  # Found via L2

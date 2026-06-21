"""cache.py - Cache management mixin."""


class CacheMixin:
    """Mixin: cache management commands."""

    def cache_stats(self):
        """Print cache statistics"""
        stats = self.cache.stats()
        print("\n[CACHE] Query Cache Statistics:")
        print("=" * 50)
        print(f"  L1 size:       {stats['l1_size']} / {stats['l1_max']}")
        print(f"  L1 TTL:        {stats['l1_ttl_s']}s ({stats['l1_ttl_s'] // 60}min)")
        print(f"  L2 size:       {stats['l2_size']} entries")
        print(f"  L2 TTL:        {stats['l2_ttl_s']}s ({stats['l2_ttl_s'] // 3600}h)")
        print(f"  Hits (L1):     {stats['hits_l1']}")
        print(f"  Hits (L2):     {stats['hits_l2']}")
        print(f"  Misses:        {stats['misses']}")
        print(f"  Total requests:{stats['total_requests']}")
        print(f"  Hit rate:      {stats['hit_rate']}")
        print(f"  Total puts:    {stats['puts']}")
        print("=" * 50)
        return stats

    def cache_clear(self):
        """Clear all cache"""
        self.cache.invalidate()
        print("[CACHE] All cache cleared (L1 + L2)")

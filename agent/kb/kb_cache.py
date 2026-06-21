#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KB Query Cache - Two-level cache for Knowledge Base queries

L1: In-memory dict with TTL (1 hour, max 1000 entries)
L2: SQLite on disk (24 hour TTL)
"""

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class KBQueryCache:
    """Two-level query result cache: L1 (memory) + L2 (SQLite)."""

    def __init__(self, cache_dir: Path, l1_max: int = 1000, l1_ttl: int = 3600,
                 l2_ttl: int = 86400):
        self.cache_dir = Path(cache_dir)
        self.l1_max = l1_max
        self.l1_ttl = l1_ttl
        self.l2_ttl = l2_ttl
        self._lock = threading.Lock()
        self.l1: Dict[str, tuple] = {}  # {key: (result, timestamp)}

        # Stats
        self._hits_l1 = 0
        self._hits_l2 = 0
        self._misses = 0
        self._puts = 0

        self._init_db()

    # -- Public API --

    def get(self, query: str, model: str = "") -> Optional[dict]:
        """Look up cached result. Returns None on miss."""
        key = self._make_key(query, model)
        now = time.time()

        # L1 check
        with self._lock:
            if key in self.l1:
                result, ts = self.l1[key]
                if now - ts < self.l1_ttl:
                    self._hits_l1 += 1
                    return result
                else:
                    del self.l1[key]

        # L2 check
        result = self._l2_get(key)
        if result is not None:
            self._hits_l2 += 1
            # Promote to L1
            with self._lock:
                self._l1_put_inner(key, result, now)
            return result

        self._misses += 1
        return None

    def put(self, query: str, model: str, result: dict):
        """Write result to both cache levels."""
        key = self._make_key(query, model)
        now = time.time()

        with self._lock:
            self._l1_put_inner(key, result, now)
        self._l2_put(key, result)
        self._puts += 1

    def invalidate(self, pattern: str = ""):
        """Clear cache entries matching pattern. Empty pattern = clear all."""
        with self._lock:
            if not pattern:
                self.l1.clear()
            else:
                keys_to_del = [k for k in self.l1 if pattern in k]
                for k in keys_to_del:
                    del self.l1[k]

        # L2: delete matching or all rows
        conn = self._db_conn()
        try:
            if not pattern:
                conn.execute("DELETE FROM cache")
            else:
                conn.execute("DELETE FROM cache WHERE key LIKE ?",
                             (f"%{pattern}%",))
            conn.commit()
        except Exception as e:
            logger.debug("caught exception: %s", e)
        finally:
            conn.close()

    def stats(self) -> dict:
        """Return cache statistics."""
        l1_size = len(self.l1)
        l2_size = 0
        try:
            conn = self._db_conn()
            try:
                row = conn.execute("SELECT COUNT(*) FROM cache").fetchone()
                l2_size = row[0] if row else 0
            finally:
                conn.close()
        except Exception as e:
            logger.debug("caught exception: %s", e)

        total = self._hits_l1 + self._hits_l2 + self._misses
        hit_rate = (self._hits_l1 + self._hits_l2) / total if total > 0 else 0.0

        return {
            "l1_size": l1_size,
            "l1_max": self.l1_max,
            "l1_ttl_s": self.l1_ttl,
            "l2_size": l2_size,
            "l2_ttl_s": self.l2_ttl,
            "hits_l1": self._hits_l1,
            "hits_l2": self._hits_l2,
            "misses": self._misses,
            "total_requests": total,
            "hit_rate": f"{hit_rate:.1%}",
            "puts": self._puts,
        }

    def cleanup(self):
        """Remove expired entries from L1 and L2."""
        now = time.time()

        # L1
        with self._lock:
            expired = [k for k, (_, ts) in self.l1.items()
                       if now - ts >= self.l1_ttl]
            for k in expired:
                del self.l1[k]

        # L2
        cutoff = now - self.l2_ttl
        conn = self._db_conn()
        try:
            conn.execute("DELETE FROM cache WHERE ts < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()

    # -- Internal --

    def _make_key(self, query: str, model: str) -> str:
        raw = f"{query.strip()}|{model.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _init_db(self):
        """Create the SQLite table if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.cache_dir / "cache.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    ts    REAL NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _db_conn(self) -> sqlite3.Connection:
        db_path = self.cache_dir / "cache.db"
        return sqlite3.connect(str(db_path), timeout=5)

    def _l1_put_inner(self, key: str, result: dict, now: float):
        """Insert into L1, evicting oldest if at capacity. Caller holds lock."""
        if len(self.l1) >= self.l1_max and key not in self.l1:
            # Evict oldest
            oldest_key = min(self.l1, key=lambda k: self.l1[k][1])
            del self.l1[oldest_key]
        self.l1[key] = (result, now)

    def _l2_get(self, key: str) -> Optional[dict]:
        conn = self._db_conn()
        try:
            row = conn.execute(
                "SELECT value, ts FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            value_str, ts = row
            if time.time() - ts >= self.l2_ttl:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                return None
            return json.loads(value_str)
        except Exception as e:
            logger.debug("caught exception: %s", e)
            return None
        finally:
            conn.close()

    def _l2_put(self, key: str, result: dict):
        conn = self._db_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, ts) VALUES (?, ?, ?)",
                (key, json.dumps(result, ensure_ascii=False), time.time())
            )
            conn.commit()
        except Exception as e:
            logger.debug("caught exception: %s", e)
        finally:
            conn.close()

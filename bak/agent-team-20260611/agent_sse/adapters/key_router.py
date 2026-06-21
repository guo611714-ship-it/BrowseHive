"""Key 路由轮询模块"""

import time
import logging
from typing import List, Dict, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class KeyRouter:
    """Key 路由轮询器（非线程安全，多线程环境需加锁）"""

    def __init__(self, keys: List[str], mode: str = "global"):
        self._keys = keys
        self._mode = mode
        self._current_index = 0
        self._stats = defaultdict(lambda: {
            "success_count": 0,
            "failure_count": 0,
            "total_count": 0,
            "last_used": 0,
        })
        self._cooldown_until: Dict[str, float] = {}
        self._max_failure_rate = 0.2
        self._max_usage_rate = 0.9
        self._cooldown_seconds = 60
        self._min_calls_for_stats = 10

    def get_next_key(self) -> str:
        """获取下一个可用的 Key"""
        available_keys = [
            k for k in self._keys
            if not self._is_cooled_down(k)
        ]

        if not available_keys:
            # 所有 Key 都冷却了，重置冷却时间
            self._cooldown_until.clear()
            available_keys = self._keys

        # 轮询选择
        key = available_keys[self._current_index % len(available_keys)]
        self._current_index += 1

        # 更新使用统计
        self._stats[key]["last_used"] = time.time()
        self._stats[key]["total_count"] += 1

        return key

    def report_success(self, key: str) -> None:
        """报告请求成功"""
        self._stats[key]["success_count"] += 1

    def report_failure(self, key: str) -> None:
        """报告请求失败"""
        self._stats[key]["failure_count"] += 1

        # 检查是否需要冷却
        stats = self._stats[key]
        total = stats["success_count"] + stats["failure_count"]

        if total >= self._min_calls_for_stats:
            failure_rate = stats["failure_count"] / total
            if failure_rate > self._max_failure_rate:
                self._cooldown_until[key] = time.time() + self._cooldown_seconds
                logger.warning(
                    f"Key {key[:8]}... failure rate {failure_rate:.1%} exceeded threshold, cooling down {self._cooldown_seconds}s"
                )

    def _is_cooled_down(self, key: str) -> bool:
        """检查 Key 是否在冷却期"""
        if key not in self._cooldown_until:
            return False
        return time.time() < self._cooldown_until[key]

    def get_stats(self, key: str) -> Dict:
        """获取 Key 统计信息"""
        stats = self._stats[key].copy()
        stats["is_cooled_down"] = self._is_cooled_down(key)
        return stats

    def get_all_stats(self) -> Dict:
        """获取所有 Key 统计信息"""
        return {
            key: self.get_stats(key)
            for key in self._keys
        }

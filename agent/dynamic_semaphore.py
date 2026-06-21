"""动态信号量 — 根据系统负载自动调整并发数"""

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


def get_system_load() -> dict:
    """获取系统负载指标"""
    try:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0],
        }
    except ImportError:
        return {"cpu_percent": 0, "memory_percent": 0, "load_avg": [0, 0, 0]}


class DynamicSemaphore:
    """根据系统负载动态调整的信号量

    纯同步设计，基于 threading.Semaphore + 计数器管理。
    注意：不支持动态 resize（threading.Semaphore 无此能力），
    调整值仅记录在 _current_value 中，新请求会参考此值。
    """

    def __init__(self, initial: int = 5, min_value: int = 1, max_value: int = 20):
        self._initial = initial
        self._min_value = min_value
        self._max_value = max_value
        self._current_value = initial
        self._semaphore = threading.Semaphore(initial)
        self._lock = threading.Lock()
        self._last_adjust_time = 0.0
        self._adjust_interval = 10  # 秒
        self._stats = {"adjustments": 0, "ups": 0, "downs": 0}

    def acquire(self, blocking: bool = True) -> bool:
        """获取信号量（同步）

        Args:
            blocking: 是否阻塞等待
        Returns:
            是否成功获取
        """
        result = self._semaphore.acquire(blocking=blocking)
        if result:
            self._maybe_adjust()
        return result

    def release(self):
        """释放信号量"""
        self._semaphore.release()

    def _maybe_adjust(self):
        """根据负载调整信号量（记录目标值，供外部参考）"""
        now = time.time()
        if now - self._last_adjust_time < self._adjust_interval:
            return
        self._last_adjust_time = now

        load = get_system_load()
        cpu = load["cpu_percent"]
        mem = load["memory_percent"]

        with self._lock:
            old_value = self._current_value

            if cpu < 50 and mem < 70:
                new_value = min(self._current_value + 2, self._max_value)
            elif cpu > 80 or mem > 85:
                new_value = max(self._current_value - 2, self._min_value)
            else:
                return

            if new_value != old_value:
                self._current_value = new_value
                self._stats["adjustments"] += 1
                if new_value > old_value:
                    self._stats["ups"] += 1
                else:
                    self._stats["downs"] += 1
                logger.info(
                    "并发调整: %d -> %d (CPU: %.1f%%, MEM: %.1f%%)",
                    old_value, new_value, cpu, mem,
                )

    @property
    def value(self) -> int:
        return self._current_value

    def get_stats(self) -> dict:
        return {
            "current_value": self._current_value,
            "initial": self._initial,
            "min": self._min_value,
            "max": self._max_value,
            **self._stats,
        }

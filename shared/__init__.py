"""共享限流器 — 基于 Browser AI 的自适应限流，供 Agent Team 复用"""

import time
from typing import Optional


class RateLimiter:
    """自适应限流器：滑动窗口 + 最小间隔"""

    def __init__(self, interval: float = 3.0, window: int = 60, max_requests: int = 10):
        self.interval = interval
        self.window = window
        self.max_requests = max_requests
        self._timestamps: dict[str, list[float]] = {}

    def check(self, key: str) -> Optional[str]:
        """检查是否允许请求，返回 None 表示允许，否则返回限流提示"""
        now = time.time()
        if key not in self._timestamps:
            self._timestamps[key] = []

        # 清理过期记录
        self._timestamps[key] = [t for t in self._timestamps[key] if (now - t) < self.window]

        # 最小间隔检查
        if self._timestamps[key]:
            last = self._timestamps[key][-1]
            if (now - last) < self.interval:
                wait = self.interval - (now - last)
                return f"[限流] {key} 请求过快，请等待{wait:.1f}秒"

        # 窗口内请求数检查
        if len(self._timestamps[key]) >= self.max_requests:
            return f"[限流] {key} 窗口内请求数已达上限({self.max_requests})"

        self._timestamps[key].append(now)
        return None

    def record(self, key: str):
        """手动记录一次请求（用于外部调用后补充）"""
        now = time.time()
        if key not in self._timestamps:
            self._timestamps[key] = []
        self._timestamps[key].append(now)

    def get_stats(self, key: str) -> dict:
        """获取限流统计"""
        now = time.time()
        timestamps = self._timestamps.get(key, [])
        active = [t for t in timestamps if (now - t) < self.window]
        return {
            "key": key,
            "window_requests": len(active),
            "max_requests": self.max_requests,
            "interval": self.interval,
        }

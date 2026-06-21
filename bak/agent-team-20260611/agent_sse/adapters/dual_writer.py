# agent_sse/adapters/dual_writer.py
"""双写机制：新旧系统同时写入，保证数据一致性"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class DualWriter:
    """双写器：新旧系统同时写入"""

    def __init__(self, new_system: Any, old_system: Any, retry_count: int = 3):
        self.new_system = new_system
        self.old_system = old_system
        self._retry_count = retry_count
        self._stats = {
            "new_success": 0,
            "new_failure": 0,
            "old_success": 0,
            "old_failure": 0,
            "dual_success": 0,
            "partial_failure": 0,
        }

    async def write(self, data: Dict[str, Any]) -> bool:
        """双写数据到新旧两个系统

        两个系统独立写入，互不阻塞。
        返回 True 表示双写成功，False 表示至少一个系统写入失败。
        """
        success_new = False
        success_old = False

        # 写入新系统（带重试）
        for attempt in range(self._retry_count):
            try:
                if asyncio.iscoroutinefunction(self.new_system.write):
                    await self.new_system.write(data)
                else:
                    self.new_system.write(data)
                success_new = True
                self._stats["new_success"] += 1
                break
            except Exception as e:
                logger.warning("新系统写入失败 (attempt %d/%d): %s", attempt + 1, self._retry_count, e)
                if attempt == self._retry_count - 1:
                    self._stats["new_failure"] += 1

        # 写入旧系统（带重试）
        for attempt in range(self._retry_count):
            try:
                if asyncio.iscoroutinefunction(self.old_system.write):
                    await self.old_system.write(data)
                else:
                    self.old_system.write(data)
                success_old = True
                self._stats["old_success"] += 1
                break
            except Exception as e:
                logger.warning("旧系统写入失败 (attempt %d/%d): %s", attempt + 1, self._retry_count, e)
                if attempt == self._retry_count - 1:
                    self._stats["old_failure"] += 1

        if success_new and success_old:
            self._stats["dual_success"] += 1
        else:
            self._stats["partial_failure"] += 1
            logger.error(
                "双写不一致: new=%s, old=%s", success_new, success_old
            )

        return success_new and success_old

    async def write_new_only(self, data: Dict[str, Any]) -> bool:
        """仅写入新系统（用于迁移期新功能数据）"""
        try:
            if asyncio.iscoroutinefunction(self.new_system.write):
                await self.new_system.write(data)
            else:
                self.new_system.write(data)
            self._stats["new_success"] += 1
            return True
        except Exception as e:
            logger.error("新系统写入失败: %s", e)
            self._stats["new_failure"] += 1
            return False

    async def write_old_only(self, data: Dict[str, Any]) -> bool:
        """仅写入旧系统（用于降级场景）"""
        try:
            if asyncio.iscoroutinefunction(self.old_system.write):
                await self.old_system.write(data)
            else:
                self.old_system.write(data)
            self._stats["old_success"] += 1
            return True
        except Exception as e:
            logger.error("旧系统写入失败: %s", e)
            self._stats["old_failure"] += 1
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取双写统计"""
        total = sum(self._stats.values())
        dual_rate = (
            self._stats["dual_success"] / total * 100
            if total > 0
            else 0.0
        )
        return {
            **self._stats,
            "total_writes": total,
            "dual_success_rate": round(dual_rate, 2),
        }

    def reset_stats(self) -> None:
        """重置统计"""
        for key in self._stats:
            self._stats[key] = 0

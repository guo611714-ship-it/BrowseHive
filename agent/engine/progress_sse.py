"""Progress SSE — 实时进度广播

Phase 2: 服务化组件
- 将 AgentProgressEvent 转换为 SSE 事件流
- 支持多订阅者
- 支持按 manifest_id 过滤
"""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Set, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    """SSE 事件"""
    event: str       # progress | complete | error | heartbeat
    data: Dict[str, Any]
    id: Optional[str] = None
    retry: Optional[int] = None

    def format(self) -> str:
        """格式化为 SSE 文本"""
        lines = []
        if self.id:
            lines.append(f"id: {self.id}")
        if self.retry:
            lines.append(f"retry: {self.retry}")
        lines.append(f"event: {self.event}")
        data_str = json.dumps(self.data, ensure_ascii=False)
        for line in data_str.split("\n"):
            lines.append(f"data: {line}")
        lines.append("")
        return "\n".join(lines) + "\n"


class ProgressBroadcaster:
    """进度广播器 — 将引擎事件推送给所有订阅者

    用法:
        broadcaster = ProgressBroadcaster()

        # 订阅
        async for event in broadcaster.subscribe("manifest-1"):
            print(event)

        # 推送
        broadcaster.publish("manifest-1", SSEEvent(
            event="progress",
            data={"shard": 1, "status": "running"}
        ))
    """

    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._global_subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self, manifest_id: Optional[str] = None) -> asyncio.Queue:
        """订阅事件流。manifest_id=None 表示订阅所有事件。"""
        queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            if manifest_id:
                self._subscribers.setdefault(manifest_id, set()).add(queue)
            else:
                self._global_subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue, manifest_id: Optional[str] = None):
        """取消订阅"""
        async with self._lock:
            if manifest_id and manifest_id in self._subscribers:
                self._subscribers[manifest_id].discard(queue)
            self._global_subscribers.discard(queue)

    def publish(self, manifest_id: str, event: SSEEvent):
        """推送事件给所有相关订阅者"""
        event.id = f"{manifest_id}-{int(time.time() * 1000)}"

        # 推送给 manifest 特定订阅者
        for queue in self._subscribers.get(manifest_id, set()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"订阅者队列已满，丢弃事件: {manifest_id}")

        # 推送给全局订阅者
        for queue in self._global_subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("全局订阅者队列已满，丢弃事件")

    def publish_progress(self, manifest_id: str, shard_id: int,
                         total_shards: int, message: str,
                         status: str = "running"):
        """便捷方法：发布进度事件"""
        self.publish(manifest_id, SSEEvent(
            event="progress",
            data={
                "manifest_id": manifest_id,
                "shard_id": shard_id,
                "total_shards": total_shards,
                "message": message,
                "status": status,
                "timestamp": datetime.now().isoformat(),
            }
        ))

    def publish_complete(self, manifest_id: str, result: Dict[str, Any]):
        """发布完成事件"""
        self.publish(manifest_id, SSEEvent(
            event="complete",
            data={
                "manifest_id": manifest_id,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        ))

    def publish_error(self, manifest_id: str, error: str):
        """发布错误事件"""
        self.publish(manifest_id, SSEEvent(
            event="error",
            data={
                "manifest_id": manifest_id,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }
        ))

    @property
    def subscriber_count(self) -> int:
        manifest_subs = sum(len(q) for q in self._subscribers.values())
        return manifest_subs + len(self._global_subscribers)


# 模块级广播器实例
_broadcaster: Optional[ProgressBroadcaster] = None


def get_broadcaster() -> ProgressBroadcaster:
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = ProgressBroadcaster()
    return _broadcaster

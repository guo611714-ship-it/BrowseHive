"""全局事件总线 -- 组件间解耦通信"""

import time
import threading
import logging
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """事件数据"""
    event_type: str
    payload: Dict[str, Any]
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = ""


class EventBus:
    """全局事件总线"""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._event_log: List[Event] = []
        self._max_log_size = 1000

    def subscribe(self, event_type: str, callback: Callable):
        """订阅事件"""
        with self._lock:
            self._subscribers[event_type].append(callback)
            logger.debug("订阅事件: %s -> %s", event_type, callback.__name__)

    def unsubscribe(self, event_type: str, callback: Callable):
        """取消订阅"""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    cb for cb in self._subscribers[event_type] if cb != callback
                ]

    def publish(self, event: Event):
        """发布事件"""
        with self._lock:
            # 记录事件日志
            self._event_log.append(event)
            if len(self._event_log) > self._max_log_size:
                self._event_log = self._event_log[-self._max_log_size:]

            # 通知订阅者
            subscribers = list(self._subscribers.get(event.event_type, []))
            wildcards = list(self._subscribers.get("*", []))

        # 在锁外执行回调，避免死锁
        for callback in subscribers + wildcards:
            try:
                callback(event)
            except Exception as e:
                logger.error("事件回调执行失败 %s: %s", event.event_type, e)

    def emit(self, event_type: str, payload: Dict[str, Any], source: str = ""):
        """便捷发布方法"""
        event = Event(event_type=event_type, payload=payload, source=source)
        self.publish(event)

    def get_recent_events(self, event_type: str = None, limit: int = 50) -> List[Event]:
        """获取最近的事件"""
        with self._lock:
            if event_type:
                events = [e for e in self._event_log if e.event_type == event_type]
            else:
                events = list(self._event_log)
        return events[-limit:]

    def clear_log(self):
        """清空事件日志"""
        with self._lock:
            self._event_log.clear()


# 全局实例
_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局事件总线实例"""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus

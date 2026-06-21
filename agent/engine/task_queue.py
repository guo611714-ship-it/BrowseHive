"""Task Queue — 引擎任务队列管理

Phase 2: 服务化核心组件
- 提交/取消/查询任务
- 优先级队列（critical > high > normal > low）
- 任务状态追踪（pending → running → done/failed）
- 历史记录持久化
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from enum import Enum
import logging
import uuid

from .manifest import TaskManifest, FixTask, TaskPriority

logger = logging.getLogger(__name__)

# 任务状态
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskEntry:
    """队列中的任务条目"""
    entry_id: str
    manifest_id: str
    task: FixTask
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0  # 数字越小优先级越高
    submitted_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    shard_id: Optional[int] = None

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "manifest_id": self.manifest_id,
            "task_id": self.task.task_id,
            "description": self.task.description,
            "files": self.task.files,
            "status": self.status.value,
            "priority": self.priority,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed": round(self.elapsed, 2),
            "error": self.error,
        }


class TaskQueue:
    """任务队列 — 管理提交/执行/查询

    特性:
    - 优先级排序
    - 状态追踪
    - 历史持久化（JSON）
    - 并发安全
    """

    def __init__(self, history_path: Optional[Path] = None, max_history: int = 1000):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._entries: Dict[str, TaskEntry] = {}  # entry_id -> TaskEntry
        self._manifest_counter = 0
        self._lock = asyncio.Lock()
        self._history_path = history_path
        self._max_history = max_history
        self._running: Set[str] = set()

        # 加载历史
        if history_path:
            self._load_history()

    def _priority_value(self, priority: TaskPriority) -> int:
        return {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
        }.get(priority, 2)

    async def submit(self, manifest: TaskManifest) -> str:
        """提交任务清单，返回 manifest_id"""
        async with self._lock:
            self._manifest_counter += 1
            manifest_id = f"m-{self._manifest_counter}-{uuid.uuid4().hex[:8]}"

            for task in manifest.tasks:
                entry = TaskEntry(
                    entry_id=f"e-{uuid.uuid4().hex[:12]}",
                    manifest_id=manifest_id,
                    task=task,
                    priority=self._priority_value(task.priority),
                )
                self._entries[entry.entry_id] = entry
                await self._queue.put((entry.priority, entry.submitted_at, entry.entry_id))

            logger.info(f"提交 manifest {manifest_id}: {len(manifest.tasks)} tasks")
            return manifest_id

    async def cancel(self, entry_id: str) -> bool:
        """取消任务"""
        async with self._lock:
            entry = self._entries.get(entry_id)
            if not entry or entry.status != TaskStatus.PENDING:
                return False
            entry.status = TaskStatus.CANCELLED
            entry.completed_at = time.time()
            self._running.discard(entry_id)
            return True

    async def cancel_manifest(self, manifest_id: str) -> int:
        """取消整个 manifest 的所有 pending 任务"""
        cancelled = 0
        async with self._lock:
            for entry in self._entries.values():
                if (entry.manifest_id == manifest_id and
                        entry.status == TaskStatus.PENDING):
                    entry.status = TaskStatus.CANCELLED
                    entry.completed_at = time.time()
                    cancelled += 1
        return cancelled

    async def next_batch(self, batch_size: int = 5) -> List[TaskEntry]:
        """获取下一批待执行任务（按优先级排序）"""
        batch = []
        temp = []

        while len(batch) < batch_size and not self._queue.empty():
            priority, ts, entry_id = await self._queue.get()
            entry = self._entries.get(entry_id)
            if entry and entry.status == TaskStatus.PENDING:
                batch.append(entry)
            else:
                temp.append((priority, ts, entry_id))

        # 把未取走的放回
        for item in temp:
            await self._queue.put(item)

        return batch

    async def mark_running(self, entry_id: str):
        """标记任务开始执行"""
        async with self._lock:
            entry = self._entries.get(entry_id)
            if entry:
                entry.status = TaskStatus.RUNNING
                entry.started_at = time.time()
                self._running.add(entry_id)

    async def mark_completed(self, entry_id: str, result: Dict[str, Any]):
        """标记任务完成"""
        async with self._lock:
            entry = self._entries.get(entry_id)
            if entry:
                entry.status = TaskStatus.COMPLETED
                entry.completed_at = time.time()
                entry.result = result
                self._running.discard(entry_id)

    async def mark_failed(self, entry_id: str, error: str):
        """标记任务失败"""
        async with self._lock:
            entry = self._entries.get(entry_id)
            if entry:
                entry.status = TaskStatus.FAILED
                entry.completed_at = time.time()
                entry.error = error
                self._running.discard(entry_id)

    def get_entry(self, entry_id: str) -> Optional[TaskEntry]:
        return self._entries.get(entry_id)

    def get_manifest_entries(self, manifest_id: str) -> List[TaskEntry]:
        return [e for e in self._entries.values()
                if e.manifest_id == manifest_id]

    @property
    def pending_count(self) -> int:
        return sum(1 for e in self._entries.values()
                   if e.status == TaskStatus.PENDING)

    @property
    def running_count(self) -> int:
        return len(self._running)

    @property
    def stats(self) -> Dict[str, int]:
        counts = {}
        for entry in self._entries.values():
            counts[entry.status.value] = counts.get(entry.status.value, 0) + 1
        counts["total"] = len(self._entries)
        return counts

    def _load_history(self):
        """从文件加载历史"""
        try:
            if self._history_path and self._history_path.exists():
                data = json.loads(self._history_path.read_text(encoding="utf-8"))
                self._manifest_counter = data.get("manifest_counter", 0)
                logger.info(f"加载历史: {self._manifest_counter} manifests")
        except Exception as e:
            logger.warning(f"加载历史失败: {e}")

    async def save_history(self):
        """保存历史到文件"""
        if not self._history_path:
            return

        # 只保留最近 N 条
        recent = sorted(
            self._entries.values(),
            key=lambda e: e.submitted_at,
            reverse=True
        )[:self._max_history]

        data = {
            "manifest_counter": self._manifest_counter,
            "entries": [e.to_dict() for e in recent],
        }

        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"保存历史失败: {e}")

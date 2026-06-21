"""统一任务状态管理器 — 并发安全 + 依赖追踪"""

import atexit
import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Literal, Set
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class TaskState:
    id: str
    name: str
    status: Literal["pending", "running", "done", "failed"] = "pending"
    result: Optional[str] = None
    agent_type: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class TaskStateManager:
    def __init__(self, state_path: str = ".team/task_state.json"):
        self.state_path = Path(state_path)
        self.tasks: Dict[str, TaskState] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._flush_interval = 2.0
        self._flush_timer: Optional[threading.Timer] = None
        atexit.register(self.shutdown)
        self._load()

    def _load(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                for t in data.get("tasks", []):
                    self.tasks[t["id"]] = TaskState(**t)
            except Exception as e:
                logger.debug("caught exception: %s", e)

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"tasks": [asdict(t) for t in self.tasks.values()]}
        self.state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _flush(self):
        """Timer callback: flush dirty state to disk."""
        with self._lock:
            self._flush_timer = None
            if self._dirty:
                self._dirty = False
                self._save()

    def _mark_dirty(self):
        """Mark state as dirty and schedule a delayed flush if not already pending."""
        self._dirty = True
        if self._flush_timer is None:
            self._flush_timer = threading.Timer(self._flush_interval, self._flush)
            self._flush_timer.daemon = True
            self._flush_timer.start()

    def save_now(self):
        """Force immediate write to disk. For critical paths."""
        with self._lock:
            if self._flush_timer is not None:
                self._flush_timer.cancel()
                self._flush_timer = None
            self._dirty = False
            self._save()

    def shutdown(self):
        """Flush any pending dirty state. Safe to call multiple times."""
        with self._lock:
            if self._flush_timer is not None:
                self._flush_timer.cancel()
                self._flush_timer = None
            if self._dirty:
                self._dirty = False
                self._save()

    def add_task(self, task_id: str, name: str,
                 agent_type: str = None, depends_on: List[str] = None) -> TaskState:
        with self._lock:
            task = TaskState(
                id=task_id, name=name,
                agent_type=agent_type,
                depends_on=depends_on or []
            )
            self.tasks[task_id] = task
            self._mark_dirty()
            return task

    def update_status(self, task_id: str, status: str, result: str = None) -> bool:
        with self._lock:
            if task_id not in self.tasks:
                return False
            self.tasks[task_id].status = status
            self.tasks[task_id].updated_at = datetime.now().isoformat()
            if result:
                self.tasks[task_id].result = result
            self._mark_dirty()
            return True

    def get_ready_tasks(self) -> List[TaskState]:
        """获取所有依赖已完成、可执行的任务"""
        with self._lock:
            ready = []
            for task in self.tasks.values():
                if task.status != "pending":
                    continue
                deps_done = all(
                    self.tasks.get(dep, TaskState(id=dep, name="")).status == "done"
                    for dep in task.depends_on
                )
                if deps_done:
                    ready.append(task)
            return ready

    def get_dependencies(self, task_id: str) -> Set[str]:
        """获取任务的所有递归依赖"""
        with self._lock:
            visited: Set[str] = set()
            stack = [task_id]
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                task = self.tasks.get(current)
                if task:
                    stack.extend(task.depends_on)
            visited.discard(task_id)
            return visited

    def get_progress(self) -> Dict:
        with self._lock:
            total = len(self.tasks)
            done = sum(1 for t in self.tasks.values() if t.status in ("done", "completed"))
            failed = sum(1 for t in self.tasks.values() if t.status == "failed")
            running = sum(1 for t in self.tasks.values() if t.status == "running")
            pending = sum(1 for t in self.tasks.values() if t.status == "pending")
            return {
                "total": total, "done": done, "failed": failed,
                "running": running, "pending": pending,
                "percent": round(done / total * 100) if total else 0,
            }

    def to_dict(self) -> Dict:
        return {
            "tasks": [asdict(t) for t in self.tasks.values()],
            "progress": self.get_progress(),
        }


_manager = None


def get_task_state_manager() -> TaskStateManager:
    global _manager
    if _manager is None:
        _manager = TaskStateManager()
    return _manager

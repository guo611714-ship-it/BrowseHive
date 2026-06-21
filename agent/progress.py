"""任务进度追踪与ETA预估"""

import time
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class TaskProgress:
    task_id: str
    description: str
    total_steps: int
    current_step: int = 0
    start_time: float = field(default_factory=time.time)
    step_times: list = field(default_factory=list)

    @property
    def percentage(self) -> float:
        return (self.current_step / self.total_steps * 100) if self.total_steps > 0 else 0

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def eta_seconds(self) -> float:
        if self.current_step == 0:
            return 0
        avg = self.elapsed / self.current_step
        return avg * (self.total_steps - self.current_step)

    def update(self, step: int = None, description: str = None):
        if step is not None:
            self.current_step = step
        if description is not None:
            self.description = description
        self.step_times.append(time.time())


class ProgressTracker:
    """全局进度追踪器"""

    def __init__(self):
        self._tasks: Dict[str, TaskProgress] = {}
        self._lock = threading.Lock()
        self._callback = None

    def set_callback(self, callback):
        self._callback = callback

    def start_task(self, task_id: str, description: str, total_steps: int) -> TaskProgress:
        with self._lock:
            task = TaskProgress(task_id=task_id, description=description, total_steps=total_steps)
            self._tasks[task_id] = task
            return task

    def update_task(self, task_id: str, step: int = None, description: str = None):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(step, description)
                if self._callback:
                    self._callback(self._tasks[task_id])

    def get_task(self, task_id: str) -> Optional[TaskProgress]:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> Dict[str, TaskProgress]:
        return dict(self._tasks)


# 全局实例
_tracker = ProgressTracker()


def get_progress_tracker() -> ProgressTracker:
    return _tracker

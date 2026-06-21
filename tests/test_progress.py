"""progress.py 测试 -- 任务进度追踪与ETA预估"""

import time
from agent.progress import TaskProgress, ProgressTracker, get_progress_tracker


class TestTaskProgress:
    """TaskProgress 数据类测试"""

    def test_init_defaults(self):
        p = TaskProgress(task_id="t1", description="test", total_steps=10)
        assert p.task_id == "t1"
        assert p.total_steps == 10
        assert p.current_step == 0
        assert p.step_times == []

    def test_percentage_zero(self):
        p = TaskProgress(task_id="t1", description="test", total_steps=10)
        assert p.percentage == 0.0

    def test_percentage_half(self):
        p = TaskProgress(task_id="t1", description="test", total_steps=10)
        p.current_step = 5
        assert p.percentage == 50.0

    def test_percentage_zero_steps(self):
        p = TaskProgress(task_id="t1", description="test", total_steps=0)
        assert p.percentage == 0.0

    def test_eta_zero_at_start(self):
        p = TaskProgress(task_id="t1", description="test", total_steps=10)
        assert p.eta_seconds == 0

    def test_eta_positive_after_update(self):
        p = TaskProgress(task_id="t1", description="test", total_steps=10)
        p.start_time = time.time() - 10  # 模拟已过10秒
        p.current_step = 5
        assert p.eta_seconds > 0

    def test_update_step(self):
        p = TaskProgress(task_id="t1", description="test", total_steps=10)
        p.update(step=3)
        assert p.current_step == 3
        assert len(p.step_times) == 1

    def test_update_description(self):
        p = TaskProgress(task_id="t1", description="old", total_steps=10)
        p.update(description="new")
        assert p.description == "new"

    def test_elapsed_positive(self):
        p = TaskProgress(task_id="t1", description="test", total_steps=10)
        time.sleep(0.01)
        assert p.elapsed > 0


class TestProgressTracker:
    """ProgressTracker 测试"""

    def test_start_task(self):
        tracker = ProgressTracker()
        p = tracker.start_task("t1", "desc", 5)
        assert p.task_id == "t1"
        assert tracker.get_task("t1") is p

    def test_update_task(self):
        tracker = ProgressTracker()
        tracker.start_task("t1", "desc", 5)
        tracker.update_task("t1", step=2)
        assert tracker.get_task("t1").current_step == 2

    def test_update_nonexistent_task(self):
        tracker = ProgressTracker()
        tracker.update_task("nonexistent", step=1)

    def test_callback_called(self):
        tracker = ProgressTracker()
        called = []
        tracker.set_callback(lambda p: called.append(p.task_id))
        tracker.start_task("t1", "desc", 5)
        tracker.update_task("t1", step=1)
        assert "t1" in called

    def test_get_all_tasks(self):
        tracker = ProgressTracker()
        tracker.start_task("t1", "a", 5)
        tracker.start_task("t2", "b", 3)
        all_tasks = tracker.get_all_tasks()
        assert len(all_tasks) == 2
        assert "t1" in all_tasks

    def test_global_tracker_singleton(self):
        t1 = get_progress_tracker()
        t2 = get_progress_tracker()
        assert t1 is t2

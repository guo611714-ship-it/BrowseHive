"""task_state模块测试"""

import json
from pathlib import Path

import pytest
from agent.state.task_state import TaskState, TaskStateManager


@pytest.fixture
def mgr(tmp_path):
    """创建临时TaskStateManager"""
    return TaskStateManager(str(tmp_path / "task_state.json"))


class TestTaskState:
    def test_defaults(self):
        t = TaskState(id="t1", name="task1")
        assert t.status == "pending"
        assert t.result is None
        assert t.depends_on == []
        assert t.created_at is not None

    def test_custom_fields(self):
        t = TaskState(id="t2", name="task2", agent_type="coding", depends_on=["t1"])
        assert t.agent_type == "coding"
        assert t.depends_on == ["t1"]


class TestAddTask:
    def test_add_single(self, mgr):
        task = mgr.add_task("t1", "First task")
        assert task.id == "t1"
        assert task.name == "First task"
        assert task.status == "pending"

    def test_add_with_deps(self, mgr):
        mgr.add_task("t1", "A")
        mgr.add_task("t2", "B", depends_on=["t1"])
        ready = mgr.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t1"

    def test_add_with_agent_type(self, mgr):
        task = mgr.add_task("t1", "Code review", agent_type="典簿")
        assert task.agent_type == "典簿"


class TestUpdateStatus:
    def test_update_existing(self, mgr):
        mgr.add_task("t1", "Task")
        result = mgr.update_status("t1", "running")
        assert result is True
        assert mgr.tasks["t1"].status == "running"

    def test_update_with_result(self, mgr):
        mgr.add_task("t1", "Task")
        mgr.update_status("t1", "done", result="Success")
        assert mgr.tasks["t1"].result == "Success"

    def test_update_nonexistent(self, mgr):
        result = mgr.update_status("no_such", "done")
        assert result is False


class TestGetReadyTasks:
    def test_no_deps(self, mgr):
        mgr.add_task("t1", "A")
        mgr.add_task("t2", "B")
        ready = mgr.get_ready_tasks()
        assert len(ready) == 2

    def test_dep_not_done(self, mgr):
        mgr.add_task("t1", "A")
        mgr.add_task("t2", "B", depends_on=["t1"])
        ready = mgr.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t1"

    def test_dep_done(self, mgr):
        mgr.add_task("t1", "A")
        mgr.add_task("t2", "B", depends_on=["t1"])
        mgr.update_status("t1", "done")
        ready = mgr.get_ready_tasks()
        # t1 is "done" (not pending), t2 is now unblocked
        assert len(ready) == 1
        assert ready[0].id == "t2"

    def test_chain_dependency(self, mgr):
        mgr.add_task("t1", "A")
        mgr.add_task("t2", "B", depends_on=["t1"])
        mgr.add_task("t3", "C", depends_on=["t2"])
        ready = mgr.get_ready_tasks()
        assert [t.id for t in ready] == ["t1"]

        mgr.update_status("t1", "done")
        ready = mgr.get_ready_tasks()
        assert [t.id for t in ready] == ["t2"]

        mgr.update_status("t2", "done")
        ready = mgr.get_ready_tasks()
        assert [t.id for t in ready] == ["t3"]


class TestGetDependencies:
    def test_no_deps(self, mgr):
        mgr.add_task("t1", "A")
        deps = mgr.get_dependencies("t1")
        assert deps == set()

    def test_direct_dep(self, mgr):
        mgr.add_task("t1", "A")
        mgr.add_task("t2", "B", depends_on=["t1"])
        deps = mgr.get_dependencies("t2")
        assert deps == {"t1"}

    def test_transitive_deps(self, mgr):
        mgr.add_task("t1", "A")
        mgr.add_task("t2", "B", depends_on=["t1"])
        mgr.add_task("t3", "C", depends_on=["t2"])
        deps = mgr.get_dependencies("t3")
        assert deps == {"t1", "t2"}


class TestGetProgress:
    def test_empty(self, mgr):
        progress = mgr.get_progress()
        assert progress["total"] == 0
        assert progress["percent"] == 0

    def test_mixed_statuses(self, mgr):
        mgr.add_task("t1", "A")
        mgr.add_task("t2", "B")
        mgr.add_task("t3", "C")
        mgr.update_status("t1", "done")
        mgr.update_status("t2", "failed")
        mgr.update_status("t3", "running")
        progress = mgr.get_progress()
        assert progress["total"] == 3
        assert progress["done"] == 1
        assert progress["failed"] == 1
        assert progress["running"] == 1
        assert progress["pending"] == 0
        assert progress["percent"] == 33


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "state.json"
        mgr1 = TaskStateManager(str(path))
        mgr1.add_task("t1", "Persistent task")
        mgr1.save_now()

        mgr2 = TaskStateManager(str(path))
        assert "t1" in mgr2.tasks
        assert mgr2.tasks["t1"].name == "Persistent task"

    def test_shutdown_flushes(self, tmp_path):
        path = tmp_path / "state.json"
        mgr = TaskStateManager(str(path))
        mgr.add_task("t1", "Task")
        mgr.shutdown()
        assert path.exists()

    def test_corrupt_file_handled(self, tmp_path):
        path = tmp_path / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT JSON{{{", encoding="utf-8")
        mgr = TaskStateManager(str(path))
        assert len(mgr.tasks) == 0


class TestToDict:
    def test_to_dict(self, mgr):
        mgr.add_task("t1", "A")
        d = mgr.to_dict()
        assert "tasks" in d
        assert "progress" in d
        assert len(d["tasks"]) == 1

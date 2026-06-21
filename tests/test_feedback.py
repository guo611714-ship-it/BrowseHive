"""feedback模块测试"""

import time
import pytest
from pathlib import Path
from agent.feedback import FeedbackLoop, TaskFeedback


@pytest.fixture
def feedback(tmp_path):
    return FeedbackLoop(tmp_path / "feedback")


class TestTaskFeedback:
    def test_defaults(self):
        f = TaskFeedback(task_id="t1", model="gpt-4", complexity=3, scenario="coding", success=True, duration_ms=100)
        assert f.task_id == "t1"
        assert f.success is True

    def test_with_error(self):
        f = TaskFeedback(task_id="t1", model="gpt-4", complexity=1, scenario="test", success=False, duration_ms=50, error="timeout")
        assert f.error == "timeout"


class TestFeedbackLoop:
    def test_record(self, feedback):
        fb = TaskFeedback(task_id="t1", model="m1", complexity=3, scenario="coding", success=True, duration_ms=100)
        feedback.record(fb)
        assert len(feedback._cache) == 1

    def test_get_model_stats(self, feedback):
        feedback.record(TaskFeedback(task_id="t1", model="m1", complexity=3, scenario="coding", success=True, duration_ms=100))
        feedback.record(TaskFeedback(task_id="t2", model="m1", complexity=3, scenario="coding", success=True, duration_ms=200))
        feedback.record(TaskFeedback(task_id="t3", model="m1", complexity=3, scenario="coding", success=False, duration_ms=50))
        stats = feedback.get_model_stats("m1")
        assert stats["total"] == 3
        assert stats["success_rate"] == pytest.approx(2/3, abs=0.01)

    def test_get_scenario_stats(self, feedback):
        feedback.record(TaskFeedback(task_id="t1", model="m1", complexity=3, scenario="coding", success=True, duration_ms=100))
        feedback.record(TaskFeedback(task_id="t2", model="m2", complexity=3, scenario="coding", success=True, duration_ms=50))
        stats = feedback.get_scenario_stats("coding")
        assert stats["total"] == 2

    def test_suggest_model_no_data(self, feedback):
        model = feedback.suggest_model("unknown_scenario", 2)
        assert model == "nvidia-step-3.7-flash"

    def test_suggest_model_with_data(self, feedback):
        for _ in range(10):
            feedback.record(TaskFeedback(task_id="t1", model="best", complexity=3, scenario="coding", success=True, duration_ms=100))
        for _ in range(3):
            feedback.record(TaskFeedback(task_id="t2", model="bad", complexity=3, scenario="coding", success=False, duration_ms=500))
        assert feedback.suggest_model("coding", 3) == "best"

    def test_persistence(self, tmp_path):
        fb1 = FeedbackLoop(tmp_path / "fb")
        fb1.record(TaskFeedback(task_id="t1", model="m1", complexity=1, scenario="test", success=True, duration_ms=10))
        fb2 = FeedbackLoop(tmp_path / "fb")
        assert len(fb2._cache) == 1

    def test_cleanup_old(self, feedback):
        feedback.record(TaskFeedback(task_id="t1", model="m1", complexity=1, scenario="test", success=True, duration_ms=10))
        feedback._cache[0]["timestamp"] = time.time() - 100 * 86400
        feedback.cleanup_old(retention_days=90)
        assert len(feedback._cache) == 0

    def test_get_all_stats(self, feedback):
        feedback.record(TaskFeedback(task_id="t1", model="m1", complexity=1, scenario="test", success=True, duration_ms=10))
        stats = feedback.get_all_stats()
        assert stats["total"] == 1

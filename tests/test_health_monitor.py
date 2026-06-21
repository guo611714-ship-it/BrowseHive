"""agent/health_monitor.py 测试"""

import pytest
import tempfile
from pathlib import Path
from agent.health_monitor import HealthMonitor

# 使用 STABILITY_RANK 中存在的模型名
TEST_MODEL = "nvidia-gemma-e2b"


class TestHealthMonitor:
    def test_default_healthy(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        assert hm.is_healthy("unknown_model") is True

    def test_record_success(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        hm.record_result(TEST_MODEL, True, latency_ms=100)
        report = hm.get_report()
        assert report[TEST_MODEL]["success"] == 1
        assert report[TEST_MODEL]["total"] == 1

    def test_record_failure(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        hm.record_result(TEST_MODEL, False)
        report = hm.get_report()
        assert report[TEST_MODEL]["fail"] == 1

    def test_consecutive_failures_mark_unhealthy(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        hm.record_result(TEST_MODEL, False)
        hm.record_result(TEST_MODEL, False)
        assert hm.is_healthy(TEST_MODEL) is False

    def test_consecutive_successes_restore_health(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        hm.record_result(TEST_MODEL, False)
        hm.record_result(TEST_MODEL, False)
        assert hm.is_healthy(TEST_MODEL) is False
        hm.record_result(TEST_MODEL, True)
        hm.record_result(TEST_MODEL, True)
        hm.record_result(TEST_MODEL, True)
        assert hm.is_healthy(TEST_MODEL) is True

    def test_mark_unhealthy(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        hm.mark_unhealthy(TEST_MODEL)
        assert hm.is_healthy(TEST_MODEL) is False

    def test_mark_healthy(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        hm.mark_unhealthy(TEST_MODEL)
        hm.mark_healthy(TEST_MODEL)
        assert hm.is_healthy(TEST_MODEL) is True

    def test_get_healthy_models(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        hm.mark_unhealthy(TEST_MODEL)
        healthy = hm.get_healthy_models()
        assert TEST_MODEL not in healthy

    def test_persistence(self):
        path = Path(tempfile.mktemp(suffix=".json"))
        hm1 = HealthMonitor(health_json_path=path)
        hm1.record_result(TEST_MODEL, True)
        hm2 = HealthMonitor(health_json_path=path)
        report = hm2.get_report()
        assert report[TEST_MODEL]["success"] == 1

    def test_trend_report(self):
        hm = HealthMonitor(health_json_path=Path(tempfile.mktemp(suffix=".json")))
        for _ in range(5):
            hm.record_result(TEST_MODEL, False)
        trends = hm.get_trend_report()
        assert TEST_MODEL in trends.get("degrading_models", {})

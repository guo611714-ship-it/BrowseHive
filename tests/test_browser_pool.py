"""browser_pool.py 测试 — 浏览器实例池 + 监控告警"""

import time
import pytest
from unittest.mock import patch
from agent.tools.browser.browser_pool import (
    BrowserPool, BrowserInstance, Monitor, AlertRule,
    get_browser_pool, get_monitor,
)


# ── BrowserPool 测试 ──

class TestBrowserPoolInit:
    def test_default_max_size(self):
        pool = BrowserPool()
        assert pool.max_size == 3
        assert pool._instances == {}

    def test_custom_max_size(self):
        pool = BrowserPool(max_size=5)
        assert pool.max_size == 5


class TestBrowserPoolGetRelease:
    def test_create_new_instance(self):
        pool = BrowserPool()
        inst = pool.get_or_create("ws://localhost:9222")
        assert inst is not None
        assert inst.status == "busy"
        assert inst.cdp_url == "ws://localhost:9222"
        assert inst.request_count == 0  # 新建实例不计数

    def test_reuse_idle_instance(self):
        pool = BrowserPool()
        inst1 = pool.get_or_create()
        pool.release(inst1.instance_id)
        inst2 = pool.get_or_create()
        assert inst1.instance_id == inst2.instance_id
        assert inst2.request_count == 1  # 复用时计数+1

    def test_pool_full_returns_none(self):
        pool = BrowserPool(max_size=1)
        pool.get_or_create()
        assert pool.get_or_create() is None

    def test_release_nonexistent_is_safe(self):
        pool = BrowserPool()
        pool.release("nonexistent")  # 不应抛异常


class TestBrowserPoolStats:
    def test_stats_empty_pool(self):
        pool = BrowserPool()
        stats = pool.get_stats()
        assert stats == {"total": 0, "idle": 0, "busy": 0, "max_size": 3}

    def test_stats_mixed_states(self):
        pool = BrowserPool()
        inst1 = pool.get_or_create()
        pool.get_or_create()
        pool.release(inst1.instance_id)
        stats = pool.get_stats()
        assert stats["total"] == 2
        assert stats["idle"] == 1
        assert stats["busy"] == 1


# ── Monitor 测试 ──

class TestMonitorAlerts:
    def test_fail_rate_triggers_alert(self):
        mon = Monitor()
        # 快速记录足够失败数据，窗口内失败率 = 100%
        for _ in range(5):
            mon.record("browser_fail_rate", 1.0)
        alerts = mon.get_alerts()
        assert len(alerts) >= 1
        assert "browser_fail_rate" in alerts[0]["rule"]

    def test_latency_triggers_alert(self):
        mon = Monitor()
        for _ in range(5):
            mon.record("browser_high_latency", 8000)
        alerts = mon.get_alerts()
        assert any("browser_high_latency" in a["rule"] for a in alerts)

    def test_cooldown_prevents_duplicate(self):
        mon = Monitor()
        mon._alert_cooldowns["browser_fail_rate"] = time.time()
        for _ in range(5):
            mon.record("browser_fail_rate", 1.0)
        rate_alerts = [a for a in mon.get_alerts() if "fail_rate" in a["rule"]]
        assert len(rate_alerts) == 0  # 冷却期内不触发

    def test_no_alert_when_below_threshold(self):
        mon = Monitor()
        for _ in range(5):
            mon.record("browser_fail_rate", 0.0)
        assert mon.get_alerts() == []


class TestMonitorMetrics:
    def test_metrics_summary(self):
        mon = Monitor()
        for v in [100, 200, 300]:
            mon.record("latency", v)
        summary = mon.get_metrics_summary()
        assert "latency" in summary
        assert summary["latency"]["count"] == 3
        assert summary["latency"]["avg"] == 200
        assert summary["latency"]["max"] == 300

    def test_metrics_summary_empty(self):
        mon = Monitor()
        assert mon.get_metrics_summary() == {}


# ── 单例函数测试 ──

class TestSingletons:
    @patch("agent.tools.browser.browser_pool._browser_pool", None)
    def test_get_browser_pool_singleton(self):
        p1 = get_browser_pool()
        p2 = get_browser_pool()
        assert p1 is p2

    @patch("agent.tools.browser.browser_pool._monitor", None)
    def test_get_monitor_singleton(self):
        m1 = get_monitor()
        m2 = get_monitor()
        assert m1 is m2

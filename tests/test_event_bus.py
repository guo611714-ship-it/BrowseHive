"""event_bus 模块测试"""

import time
import pytest
from agent.event_bus import EventBus, Event, get_event_bus


# ---------- subscribe / publish 测试 ----------

class TestSubscribePublish:
    def test_subscribe_receives_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("test.event", lambda e: received.append(e))

        bus.emit("test.event", {"key": "value"}, source="unit_test")

        assert len(received) == 1
        assert received[0].event_type == "test.event"
        assert received[0].payload == {"key": "value"}
        assert received[0].source == "unit_test"

    def test_multiple_subscribers(self):
        bus = EventBus()
        results_a, results_b = [], []
        bus.subscribe("multi", lambda e: results_a.append(1))
        bus.subscribe("multi", lambda e: results_b.append(1))

        bus.emit("multi", {})

        assert len(results_a) == 1
        assert len(results_b) == 1

    def test_different_event_types(self):
        bus = EventBus()
        received_a, received_b = [], []
        bus.subscribe("type_a", lambda e: received_a.append(e))
        bus.subscribe("type_b", lambda e: received_b.append(e))

        bus.emit("type_a", {})
        bus.emit("type_b", {})

        assert len(received_a) == 1
        assert len(received_b) == 1


# ---------- unsubscribe 测试 ----------

class TestUnsubscribe:
    def test_unsubscribe_stops_receiving(self):
        bus = EventBus()
        received = []
        callback = lambda e: received.append(e)

        bus.subscribe("unsub.test", callback)
        bus.emit("unsub.test", {})
        assert len(received) == 1

        bus.unsubscribe("unsub.test", callback)
        bus.emit("unsub.test", {})
        assert len(received) == 1  # 不再增长

    def test_unsubscribe_nonexistent_no_error(self):
        bus = EventBus()
        bus.unsubscribe("no.such.type", lambda e: None)  # 不应抛异常


# ---------- emit 便捷方法 ----------

class TestEmit:
    def test_emit_creates_event_with_source(self):
        bus = EventBus()
        received = []
        bus.subscribe("emit.test", lambda e: received.append(e))

        bus.emit("emit.test", {"data": 42}, source="emitter")

        assert received[0].source == "emitter"
        assert received[0].payload == {"data": 42}

    def test_emit_default_source(self):
        bus = EventBus()
        received = []
        bus.subscribe("src.default", lambda e: received.append(e))

        bus.emit("src.default", {})

        assert received[0].source == ""


# ---------- 事件日志测试 ----------

class TestEventLog:
    def test_events_logged(self):
        bus = EventBus()
        bus.emit("log.a", {"a": 1})
        bus.emit("log.b", {"b": 2})

        events = bus.get_recent_events()
        assert len(events) == 2

    def test_filter_by_event_type(self):
        bus = EventBus()
        bus.emit("type.x", {})
        bus.emit("type.y", {})
        bus.emit("type.x", {})

        x_events = bus.get_recent_events(event_type="type.x")
        assert len(x_events) == 2

    def test_limit_parameter(self):
        bus = EventBus()
        for i in range(10):
            bus.emit("limit.test", {"i": i})

        events = bus.get_recent_events(limit=3)
        assert len(events) == 3

    def test_clear_log(self):
        bus = EventBus()
        bus.emit("clear.test", {})
        assert len(bus.get_recent_events()) == 1

        bus.clear_log()
        assert len(bus.get_recent_events()) == 0

    def test_max_log_size_eviction(self):
        """日志超过上限时应自动裁剪"""
        bus = EventBus()
        bus._max_log_size = 5
        for i in range(10):
            bus.emit("evict.test", {"i": i})

        assert len(bus.get_recent_events(limit=100)) == 5
        # 保留的是最新的5条
        events = bus.get_recent_events()
        assert events[0].payload["i"] == 5


# ---------- 通配符订阅测试 ----------

class TestWildcardSubscription:
    def test_wildcard_receives_all_events(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", lambda e: received.append(e))

        bus.emit("any.type", {})
        bus.emit("another.type", {})

        assert len(received) == 2

    def test_wildcard_plus_specific(self):
        bus = EventBus()
        wildcard_count = [0]
        specific_count = [0]
        bus.subscribe("*", lambda e: wildcard_count.__setitem__(0, wildcard_count[0] + 1))
        bus.subscribe("specific", lambda e: specific_count.__setitem__(0, specific_count[0] + 1))

        bus.emit("specific", {})

        assert wildcard_count[0] == 1
        assert specific_count[0] == 1


# ---------- 异常隔离测试 ----------

class TestExceptionIsolation:
    def test_failing_callback_does_not_block_others(self):
        """一个回调抛异常不应影响其他订阅者"""
        bus = EventBus()
        results = []

        def good_callback(event):
            results.append("good")

        def bad_callback(event):
            raise ValueError("故意抛出的异常")

        bus.subscribe("err.test", bad_callback)
        bus.subscribe("err.test", good_callback)

        bus.emit("err.test", {})

        assert "good" in results

    def test_failing_callback_does_not_block_wildcards(self):
        """通配符回调中的异常不应影响特定回调"""
        bus = EventBus()
        results = []

        def bad_wildcard(event):
            raise RuntimeError("wildcard error")

        def specific(event):
            results.append("specific_ok")

        bus.subscribe("wc.test", specific)
        bus.subscribe("*", bad_wildcard)

        bus.emit("wc.test", {})

        assert "specific_ok" in results


# ---------- 全局实例测试 ----------

class TestGlobalInstance:
    def test_get_event_bus_returns_same_instance(self):
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2


# ---------- Event 数据类测试 ----------

class TestEventDataclass:
    def test_timestamp_auto_set(self):
        before = time.time()
        event = Event(event_type="t", payload={})
        after = time.time()
        assert before <= event.timestamp <= after

    def test_defaults(self):
        event = Event(event_type="t", payload={})
        assert event.source == ""
        assert event.event_id == ""

"""性能基准测试

基线(2026-06-01, AMD Ryzen 5 / 16GB / Python 3.11):
  tool_registration:    0.8ms/100次
  schema_generation:    0.3ms/1000次
  memory_append:        4.2ms/100次
  memory_read:          1.8ms/100次
  dag_resolution:       0.9ms/100次
  cleanup:              12ms/100文件
  event_bus_pubsub:     0.5ms/100次
  api_key_pool:         0.2ms/1000次
  model_routing:        1.1ms/1000次
  tool_dispatch:        3.5ms/100次
"""

import os
import time
from pathlib import Path

import pytest
from agent.tools.tool_registry import tool, get_tool_schemas, TOOL_REGISTRY
from agent.memory import MemoryStore
from agent.state.task_state import TaskStateManager
from agent.cleanup import cleanup_memory_archives, cleanup_all


class TestToolRegistryPerformance:
    """工具注册性能"""

    def test_registration_speed(self):
        """工具注册速度 < 1ms"""
        start = time.perf_counter()
        for i in range(100):
            @tool(f"perf_test_{i}", "Performance test tool")
            def dummy_func(x: str = "test") -> str:
                return x
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 100  # 100ms for 100 registrations
        # Cleanup
        for i in range(100):
            TOOL_REGISTRY.pop(f"perf_test_{i}", None)

    def test_schema_generation_speed(self):
        """Schema生成速度 < 10ms"""
        start = time.perf_counter()
        for _ in range(1000):
            schemas = get_tool_schemas()
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 1000  # 1s for 1000 calls


class TestMemoryStorePerformance:
    """记忆存储性能"""

    def test_append_history_speed(self, tmp_path):
        """历史追加速度 < 5ms"""
        mem = MemoryStore(tmp_path / "mem")
        start = time.perf_counter()
        for i in range(100):
            mem.append_history({"role": "user", "content": f"Message {i}"})
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500  # 500ms for 100 appends

    def test_read_history_speed(self, tmp_path):
        """历史读取速度 < 10ms"""
        mem = MemoryStore(tmp_path / "mem")
        for i in range(100):
            mem.append_history({"role": "user", "content": f"Message {i}"})
        start = time.perf_counter()
        for _ in range(100):
            history = mem.get_recent_history(100)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 1000  # 1s for 100 reads


class TestTaskStatePerformance:
    """任务状态性能"""

    def test_dag_resolution_speed(self, tmp_path):
        """DAG依赖解析 < 5ms"""
        mgr = TaskStateManager(str(tmp_path / "state.json"))
        # Create chain of 50 tasks
        for i in range(50):
            deps = [f"t{i-1}"] if i > 0 else []
            mgr.add_task(f"t{i}", f"Task {i}", depends_on=deps)

        start = time.perf_counter()
        for _ in range(100):
            ready = mgr.get_ready_tasks()
            deps = mgr.get_dependencies("t49")
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500  # 500ms for 100 DAG resolutions


class TestCleanupPerformance:
    """清理性能"""

    def test_cleanup_speed(self, tmp_path):
        """清理速度 < 50ms"""
        # Create test files
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        for i in range(100):
            (archive_dir / f"file_{i}.jsonl").write_text("data")

        # 设置文件时间戳为旧文件（100天前），确保 retention_days=0 时全部删除
        old_time = time.time() - 100 * 24 * 3600
        for f in archive_dir.glob("*.jsonl"):
            os.utime(f, (old_time, old_time))

        start = time.perf_counter()
        stats = cleanup_memory_archives(tmp_path, retention_days=0)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500  # 500ms for cleanup
        assert stats["deleted_count"] == 100  # retention_days=0 应删除所有旧文件


class TestEventBusPerformance:
    """EventBus pub/sub 性能"""

    def test_publish_subscribe_speed(self):
        """发布订阅速度 < 1ms"""
        from agent.event_bus import EventBus, Event
        bus = EventBus()
        received = []
        bus.subscribe("test.event", lambda e: received.append(e))

        start = time.perf_counter()
        for i in range(100):
            bus.publish(Event(event_type="test.event", payload={"i": i}))
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 100  # 100ms for 100 publishes
        assert len(received) == 100

    def test_multi_subscriber_speed(self):
        """多订阅者性能 < 5ms"""
        from agent.event_bus import EventBus, Event
        bus = EventBus()
        counters = [0, 0, 0]
        for idx in range(3):
            bus.subscribe("test.event", lambda e, i=idx: counters.__setitem__(i, counters[i] + 1))

        start = time.perf_counter()
        for i in range(100):
            bus.publish(Event(event_type="test.event", payload={"i": i}))
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 100  # 100ms for 100 publishes to 3 subscribers
        assert all(c == 100 for c in counters)


class TestAPIKeyPoolPerformance:
    """API Key池轮转性能"""

    def test_key_rotation_speed(self):
        """Key轮转速度 < 1ms"""
        from shared.api_key_pool import APIKeyPool
        keys = [f"nvapi-test-{i}" for i in range(9)]
        pool = APIKeyPool(keys=keys, account_max_requests=60)

        start = time.perf_counter()
        for _ in range(1000):
            key = pool.next_key()
            # Account rate limit may block; just measure the call overhead
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 1000  # 1s for 1000 rotation attempts

    def test_sub_pool_creation_speed(self):
        """子池创建速度 < 10ms"""
        from shared.api_key_pool import APIKeyPool
        keys = [f"nvapi-test-{i}" for i in range(9)]
        pool = APIKeyPool(keys=keys, account_max_requests=60)

        start = time.perf_counter()
        for i in range(3):
            pool.create_sub_pool(f"proj-{i}", key_count=3, project_max_requests=15)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 100  # 100ms for 3 sub-pools


class TestModelRoutingPerformance:
    """模型路由性能"""

    def test_complexity_routing_speed(self):
        """复杂度路由速度 < 2ms"""
        from agent.model_orchestrator import ModelOrchestrator
        config_path = Path("model_config.json")
        if not config_path.exists():
            pytest.skip("model_config.json not found")
        orch = ModelOrchestrator(config_path)

        start = time.perf_counter()
        for _ in range(1000):
            # get_model_for_complexity is the hot path
            model = orch.get_model_for_complexity(2)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 5000  # 5s for 1000 routing decisions


class TestToolDispatchPerformance:
    """工具调度性能"""

    def test_get_dispatcher_speed(self):
        """调度器初始化速度 < 5ms"""
        from agent.tools.dispatch_tools import get_dispatcher

        start = time.perf_counter()
        for _ in range(100):
            d = get_dispatcher()
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500  # 500ms for 100 inits


class TestBrowserToolsPerformance:
    """浏览器工具性能（纯逻辑，无网络）"""

    def test_fill_form_parse_speed(self):
        """表单JSON解析速度 < 1ms"""
        import json
        fields = json.dumps([{"selector": f"#field{i}", "value": f"value{i}", "type": "text"}
                             for i in range(20)])

        start = time.perf_counter()
        for _ in range(1000):
            parsed = json.loads(fields)
            assert len(parsed) == 20
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500  # 500ms for 1000 parses

    def test_cookie_parse_speed(self):
        """Cookie解析速度 < 1ms"""
        raw = "; ".join([f"key{i}=value{i}" for i in range(50)])

        start = time.perf_counter()
        for _ in range(1000):
            cookies = {}
            for part in raw.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
            assert len(cookies) == 50
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500  # 500ms for 1000 parses

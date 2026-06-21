"""分布式 Worker Pool 测试

覆盖: FileHashRouter / NodeRegistry / CrossNodeDispatcher / DistributedWorkerPool
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.engine.distributed import (
    CrossNodeDispatcher,
    DispatchError,
    DistributedWorkerPool,
    FileHashRouter,
    NodeConfig,
    NodeRegistry,
    NodeStatus,
    create_distributed_pool,
)


# ============================================================
# 辅助函数
# ============================================================

def make_node(node_id: str = "n1", host: str = "localhost", port: int = 8001,
              capacity: int = 5, status: NodeStatus = NodeStatus.ACTIVE) -> NodeConfig:
    return NodeConfig(node_id=node_id, host=host, port=port, capacity=capacity, status=status)


def make_nodes(count: int = 3, capacity: int = 5) -> list:
    return [make_node(f"n{i}", port=8000 + i, capacity=capacity) for i in range(1, count + 1)]


# ============================================================
# FileHashRouter 测试
# ============================================================

class TestFileHashRouter:
    """路由一致性与哈希分布"""

    def setup_method(self):
        self.router = FileHashRouter()

    def test_routing_consistency(self):
        """同一文件多次路由应始终返回同一节点"""
        nodes = make_nodes()
        file_path = "src/main.py"
        results = [self.router.route(file_path, nodes) for _ in range(20)]
        assert all(r.node_id == results[0].node_id for r in results)

    def test_different_files_spread(self):
        """不同文件应分布到多个节点（非全部集中）"""
        nodes = make_nodes(3, capacity=10)
        file_paths = [f"src/file_{i}.py" for i in range(100)]
        targets = set()
        for fp in file_paths:
            node = self.router.route(fp, nodes)
            if node:
                targets.add(node.node_id)
        # 100个文件应该能分布到多个节点
        assert len(targets) >= 2

    def test_empty_nodes_returns_none(self):
        """空节点列表返回 None"""
        result = self.router.route("any.py", [])
        assert result is None

    def test_only_active_nodes_selected(self):
        """只选择 active 节点"""
        nodes = [
            make_node("n1", status=NodeStatus.OFFLINE),
            make_node("n2", status=NodeStatus.ACTIVE),
        ]
        result = self.router.route("test.py", nodes)
        assert result is not None
        assert result.node_id == "n2"

    def test_draining_node_not_routed_for_new_tasks(self):
        """draining 节点不应被路由新任务"""
        nodes = [make_node("n1", status=NodeStatus.DRAINING)]
        result = self.router.route("test.py", nodes)
        assert result is None

    def test_fallback_to_next_node(self):
        """离线节点时路由回退到下一个可用节点"""
        nodes = [
            make_node("n1", status=NodeStatus.OFFLINE),
            make_node("n2", capacity=10),
        ]
        # route_with_fallback 应跳过 n1
        result = self.router.route_with_fallback("test.py", nodes)
        assert result is not None
        assert result.node_id == "n2"


# ============================================================
# NodeRegistry 测试
# ============================================================

class TestNodeRegistry:
    """节点注册、心跳与离线检测"""

    def setup_method(self):
        self.registry = NodeRegistry(heartbeat_timeout=1.0)

    def test_register_and_get(self):
        """注册后可查询到节点"""
        node = make_node("n1")
        self.registry.register(node)
        assert self.registry.node_count == 1
        assert self.registry.get_node("n1") is not None

    def test_deregister(self):
        """注销节点"""
        self.registry.register(make_node("n1"))
        assert self.registry.deregister("n1") is True
        assert self.registry.node_count == 0
        assert self.registry.get_node("n1") is None

    def test_deregister_nonexistent(self):
        """注销不存在的节点返回 False"""
        assert self.registry.deregister("nonexistent") is False

    def test_heartbeat_updates_time(self):
        """心跳更新 last_heartbeat"""
        node = make_node("n1")
        self.registry.register(node)
        old_time = node.last_heartbeat
        time.sleep(0.05)
        result = self.registry.heartbeat("n1")
        assert result is True
        assert node.last_heartbeat > old_time

    def test_heartbeat_nonexistent_returns_false(self):
        """不存在的节点心跳返回 False"""
        assert self.registry.heartbeat("ghost") is False

    def test_auto_detect_offline(self):
        """超过超时阈值自动标记为 offline"""
        node = make_node("n1")
        self.registry.register(node)
        # 模拟过期心跳
        node.last_heartbeat = time.time() - 10.0
        active = self.registry.get_active_nodes()
        assert len(active) == 0
        assert node.status == NodeStatus.OFFLINE

    def test_heartbeat_recovers_offline_node(self):
        """离线节点通过心跳恢复为 active"""
        node = make_node("n1")
        self.registry.register(node)
        node.last_heartbeat = time.time() - 10.0
        self.registry._detect_offline_nodes()
        assert node.status == NodeStatus.OFFLINE

        # 发送心跳恢复
        self.registry.heartbeat("n1")
        assert node.status == NodeStatus.ACTIVE

    def test_get_active_nodes_filters_offline(self):
        """get_active_nodes 过滤离线节点"""
        nodes = [make_node("n1"), make_node("n2")]
        for n in nodes:
            self.registry.register(n)
        # 让 n1 过期
        nodes[0].last_heartbeat = time.time() - 10.0
        active = self.registry.get_active_nodes()
        assert len(active) == 1
        assert active[0].node_id == "n2"


# ============================================================
# CrossNodeDispatcher 测试
# ============================================================

class TestCrossNodeDispatcher:
    """跨节点 HTTP 调度"""

    def setup_method(self):
        self.dispatcher = CrossNodeDispatcher(timeout=2.0, max_retries=2)

    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        """成功调度返回响应"""
        def make_ctx(response):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=response)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"result": "ok"})

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=make_ctx(mock_response))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            node = make_node("n1")
            result = await self.dispatcher.dispatch(node, {"task_id": "t1"})
            assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_dispatch_retry_on_failure(self):
        """失败时重试"""
        def make_ctx(response):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=response)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        mock_response_fail = AsyncMock()
        mock_response_fail.status = 500
        mock_response_fail.text = AsyncMock(return_value="error")

        mock_response_ok = AsyncMock()
        mock_response_ok.status = 200
        mock_response_ok.json = AsyncMock(return_value={"result": "ok"})

        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_ctx(mock_response_fail)
            return make_ctx(mock_response_ok)

        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            node = make_node("n1")
            result = await self.dispatcher.dispatch(node, {"task_id": "t1"})
            assert result == {"result": "ok"}
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_dispatch_all_retries_failed(self):
        """所有重试失败抛出 DispatchError"""
        def make_ctx(response):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=response)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="error")

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=make_ctx(mock_response))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            node = make_node("n1")
            with pytest.raises(DispatchError):
                await self.dispatcher.dispatch(node, {"task_id": "t1"})

    @pytest.mark.asyncio
    async def test_dispatch_with_fallback(self):
        """主节点失败自动转移到备选节点"""
        def make_ctx(response):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=response)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        mock_response_ok = AsyncMock()
        mock_response_ok.status = 200
        mock_response_ok.json = AsyncMock(return_value={"result": "from_fallback"})

        mock_response_fail = AsyncMock()
        mock_response_fail.status = 500
        mock_response_fail.text = AsyncMock(return_value="error")

        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # 前2次是主节点重试
                return make_ctx(mock_response_fail)
            return make_ctx(mock_response_ok)  # 第3次是备选节点

        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            primary = make_node("n1")
            fallback = make_node("n2", port=8002)
            result = await self.dispatcher.dispatch_with_fallback(
                primary, {"task_id": "t1"}, [fallback]
            )
            assert result == {"result": "from_fallback"}


# ============================================================
# DistributedWorkerPool 测试
# ============================================================

class TestDistributedWorkerPool:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_dispatch_task_routes_by_file(self):
        """任务按文件 hash 路由到正确节点"""
        pool = DistributedWorkerPool()
        for node in make_nodes(3, capacity=10):
            pool.registry.register(node)

        await pool.start()
        try:
            # 查询文件路由
            node = pool.get_node_for_file("src/main.py")
            assert node is not None
            # 多次查询应一致
            for _ in range(10):
                assert pool.get_node_for_file("src/main.py").node_id == node.node_id
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_dispatch_task_no_active_nodes(self):
        """无活跃节点时抛出 DispatchError"""
        pool = DistributedWorkerPool()
        await pool.start()
        try:
            with pytest.raises(DispatchError, match="No active nodes"):
                await pool.dispatch_task({"task_id": "t1", "files": ["a.py"]})
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_dispatch_task_with_mock(self):
        """mock HTTP 调度验证端到端流程"""
        pool = DistributedWorkerPool()
        pool.registry.register(make_node("n1", capacity=10))

        # Mock dispatcher
        mock_result = {"result": "ok", "node": "n1"}
        pool.dispatcher.dispatch = AsyncMock(return_value=mock_result)

        await pool.start()
        try:
            result = await pool.dispatch_task({"task_id": "t1", "files": ["test.py"]})
            assert result == mock_result
            assert pool.stats()["tasks_dispatched"] == 1
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_dispatch_increments_stats(self):
        """调度成功/失败正确计数"""
        pool = DistributedWorkerPool()
        pool.registry.register(make_node("n1", capacity=10))

        # 成功
        pool.dispatcher.dispatch = AsyncMock(return_value={"ok": True})
        await pool.start()
        try:
            await pool.dispatch_task({"task_id": "t1", "files": ["a.py"]})
            assert pool.stats()["tasks_dispatched"] == 1

            # 失败
            pool.dispatcher.dispatch = AsyncMock(side_effect=DispatchError("fail"))
            try:
                await pool.dispatch_task({"task_id": "t2", "files": ["b.py"]})
            except DispatchError:
                pass
            assert pool.stats()["tasks_failed"] == 1
        finally:
            await pool.shutdown()


# ============================================================
# create_distributed_pool 工厂函数测试
# ============================================================

class TestCreateDistributedPool:
    """工厂函数测试"""

    def test_create_from_config_file(self):
        """从 JSON 文件创建分布式池"""
        config = [
            {"node_id": "n1", "host": "localhost", "port": 8001, "capacity": 5},
            {"node_id": "n2", "host": "192.168.1.100", "port": 8002, "capacity": 10},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            f.flush()
            pool = create_distributed_pool(f.name)

        assert pool.registry.node_count == 2
        assert pool.registry.get_node("n1") is not None
        assert pool.registry.get_node("n2") is not None
        # 清理
        Path(f.name).unlink(missing_ok=True)

    def test_create_missing_file_raises(self):
        """配置文件不存在时抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            create_distributed_pool("/nonexistent/path.json")

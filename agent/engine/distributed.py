"""分布式 Worker Pool -- 跨节点任务执行 (Phase 4)

支持按文件 hash 路由、节点注册/心跳、跨节点 HTTP 调度。
同文件的任务总是路由到同一节点，保证本地缓存一致性。

用法:
    from agent.engine.distributed import create_distributed_pool

    pool = create_distributed_pool("nodes_config.json")
    await pool.start()
    result = await pool.dispatch_task({"task_id": "t1", "files": ["src/main.py"]})
    await pool.shutdown()
"""

import asyncio
import bisect
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================

class NodeStatus(str, Enum):
    """节点状态"""
    ACTIVE = "active"
    DRAINING = "draining"  # 排空中：不再接受新任务，等待现有任务完成
    OFFLINE = "offline"


@dataclass
class NodeConfig:
    """节点配置"""
    node_id: str
    host: str
    port: int
    capacity: int = 5  # 最大并发任务数
    status: NodeStatus = NodeStatus.ACTIVE
    previous_status: Optional[NodeStatus] = None
    last_heartbeat: float = field(default_factory=time.time)

    @property
    def base_url(self) -> str:
        """节点 API 地址"""
        return f"http://{self.host}:{self.port}"

    @property
    def is_available(self) -> bool:
        """是否可接受新任务"""
        return self.status == NodeStatus.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "capacity": self.capacity,
            "status": self.status.value,
        }


# ============================================================
# 文件 Hash 路由器
# ============================================================

class FileHashRouter:
    """按文件路径 hash 路由任务到节点

    一致性哈希: 使用排序哈希环 + 虚拟节点。
    每个真实节点映射 K 个虚拟节点到环上，route() 通过 bisect_left 定位。
    添加/移除节点时只影响约 1/N 的键。
    """

    VIRTUAL_NODES_DEFAULT = 150  # 每个真实节点的虚拟节点数

    def __init__(self, virtual_nodes: int = VIRTUAL_NODES_DEFAULT):
        self._virtual_nodes = virtual_nodes
        self._ring: List[int] = []                           # 排序的哈希值列表
        self._ring_to_node: Dict[int, str] = {}              # hash_value -> node_id
        self._node_vnodes: Dict[str, List[int]] = {}         # node_id -> [hash_values]
        self._dirty = True                                   # ring needs rebuild
        self._cached_available: Optional[List[str]] = None   # cached node_id list

    @staticmethod
    def _hash_file(file_path: str) -> int:
        """计算文件路径的稳定哈希值（正整数）"""
        digest = hashlib.md5(file_path.encode("utf-8")).hexdigest()
        return int(digest, 16)

    def _hash_virtual(self, node_id: str, index: int) -> int:
        """计算虚拟节点的哈希值"""
        digest = hashlib.md5(f"{node_id}#{index}".encode("utf-8")).hexdigest()
        return int(digest, 16)

    def _add_node_to_ring(self, node_id: str) -> None:
        """向哈希环添加一个节点的所有虚拟节点"""
        vnodes = []
        for i in range(self._virtual_nodes):
            h = self._hash_virtual(node_id, i)
            if h not in self._ring_to_node:  # 避免哈希冲突覆盖
                self._ring_to_node[h] = node_id
                vnodes.append(h)
        self._node_vnodes[node_id] = vnodes
        self._ring.extend(vnodes)
        self._ring.sort()
        self._dirty = True

    def _remove_node_from_ring(self, node_id: str) -> None:
        """从哈希环移除一个节点的所有虚拟节点"""
        vnodes = self._node_vnodes.pop(node_id, [])
        for h in vnodes:
            self._ring_to_node.pop(h, None)
        self._ring = [h for h in self._ring if h in self._ring_to_node]
        self._dirty = True

    def _rebuild_ring(self, nodes: List[NodeConfig]) -> None:
        """完全重建哈希环（仅在首次或批量变更时）"""
        self._ring.clear()
        self._ring_to_node.clear()
        self._node_vnodes.clear()
        for node in nodes:
            self._add_node_to_ring(node.node_id)

    def _find_node(self, file_hash: int) -> Optional[str]:
        """在哈希环上查找文件对应的节点"""
        if not self._ring:
            return None
        idx = bisect.bisect_left(self._ring, file_hash)
        if idx >= len(self._ring):
            idx = 0  # 环形: 回到第一个节点
        return self._ring_to_node[self._ring[idx]]

    def route(self, file_path: str, nodes: List[NodeConfig]) -> Optional[NodeConfig]:
        """路由文件到目标节点

        Args:
            file_path: 文件路径
            nodes: 可用节点列表（至少一个 active 节点）

        Returns:
            目标节点，若无可用节点则返回 None
        """
        if not nodes:
            return None

        # 过滤可接受任务的节点
        available = [n for n in nodes if n.is_available]
        if not available:
            return None

        # 仅在节点列表变化时重建哈希环
        current_ids = [n.node_id for n in available]
        if self._dirty or self._cached_available != current_ids:
            self._rebuild_ring(available)
            self._cached_available = current_ids

        file_hash = self._hash_file(file_path)
        node_id = self._find_node(file_hash)
        if node_id is None:
            return None

        # node_id -> NodeConfig
        node_map = {n.node_id: n for n in available}
        return node_map.get(node_id)

    def route_with_fallback(
        self,
        file_path: str,
        nodes: List[NodeConfig],
        max_retries: int = 3,
    ) -> Optional[NodeConfig]:
        """路由并支持故障转移

        如果目标节点离线，依次尝试后续节点。
        """
        if not nodes:
            return None

        available = [n for n in nodes if n.is_available]
        if not available:
            return None

        # 重建哈希环
        self._rebuild_ring(available)

        file_hash = self._hash_file(file_path)
        node_id = self._find_node(file_hash)
        if node_id is None:
            return None

        # 构建有序列表 (从 target 开始顺时针)
        idx = bisect.bisect_left(self._ring, file_hash)
        if idx >= len(self._ring):
            idx = 0

        node_map = {n.node_id: n for n in available}
        seen = set()

        for attempt in range(min(max_retries, len(available))):
            ring_idx = (idx + attempt) % len(self._ring)
            nid = self._ring_to_node[self._ring[ring_idx]]
            if nid not in seen:
                seen.add(nid)
                node = node_map.get(nid)
                if node and node.is_available:
                    return node

        return None


# ============================================================
# 节点注册表
# ============================================================

class NodeRegistry:
    """节点注册与发现

    - register/deregister 管理节点生命周期
    - heartbeat 更新心跳时间
    - 自动检测离线节点（超过 30 秒无心跳）
    """

    HEARTBEAT_TIMEOUT = 30.0  # 心跳超时（秒）

    def __init__(self, heartbeat_timeout: float = HEARTBEAT_TIMEOUT):
        self._nodes: Dict[str, NodeConfig] = {}
        self._heartbeat_timeout = heartbeat_timeout

    def register(self, node: NodeConfig) -> None:
        """注册节点"""
        node.last_heartbeat = time.time()
        self._nodes[node.node_id] = node
        logger.info("Node registered: %s (%s:%d, cap=%d)",
                     node.node_id, node.host, node.port, node.capacity)

    def deregister(self, node_id: str) -> bool:
        """注销节点，返回是否成功"""
        removed = self._nodes.pop(node_id, None)
        if removed:
            logger.info("Node deregistered: %s", node_id)
            return True
        logger.warning("Deregister failed: node %s not found", node_id)
        return False

    def heartbeat(self, node_id: str) -> bool:
        """更新节点心跳

        Returns:
            True 表示成功更新，False 表示节点不存在
        """
        node = self._nodes.get(node_id)
        if node is None:
            return False
        node.last_heartbeat = time.time()
        # 如果节点之前是 offline，恢复为之前的活跃状态
        if node.status == NodeStatus.OFFLINE:
            if node.previous_status == NodeStatus.ACTIVE:
                node.status = NodeStatus.ACTIVE
                node.previous_status = None
                logger.info("Node recovered via heartbeat: %s", node_id)
            elif node.previous_status == NodeStatus.DRAINING:
                node.status = NodeStatus.DRAINING
                node.previous_status = None
                logger.info("Draining node recovered via heartbeat: %s", node_id)
        return True

    def get_active_nodes(self) -> List[NodeConfig]:
        """获取所有活跃节点（含 heartbeat 检测）"""
        self._detect_offline_nodes()
        return [n for n in self._nodes.values() if n.is_available]

    def get_node(self, node_id: str) -> Optional[NodeConfig]:
        """获取指定节点"""
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> List[NodeConfig]:
        """获取所有节点（含离线）"""
        self._detect_offline_nodes()
        return list(self._nodes.values())

    def _detect_offline_nodes(self) -> None:
        """自动检测离线节点"""
        now = time.time()
        for node in self._nodes.values():
            if node.status == NodeStatus.OFFLINE:
                continue
            elapsed = now - node.last_heartbeat
            if elapsed > self._heartbeat_timeout:
                node.previous_status = node.status
                node.status = NodeStatus.OFFLINE
                logger.warning("Node marked offline: %s (no heartbeat for %.1fs)",
                               node.node_id, elapsed)

    @property
    def node_count(self) -> int:
        return len(self._nodes)


# ============================================================
# 跨节点调度器
# ============================================================

class CrossNodeDispatcher:
    """通过 HTTP 将任务调度到远程节点

    - POST http://{host}:{port}/engine/submit
    - 超时、重试（3次）、失败时转移到其他节点
    """

    DEFAULT_TIMEOUT = 10.0  # 单次请求超时（秒）
    MAX_RETRIES = 3  # 最大重试次数

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, max_retries: int = MAX_RETRIES):
        self._timeout = timeout
        self._max_retries = max_retries

    async def dispatch(self, node: NodeConfig, task: Dict[str, Any]) -> Dict[str, Any]:
        """调度任务到指定节点

        Args:
            node: 目标节点
            task: 任务数据（会被 JSON 序列化后发送）

        Returns:
            远程节点返回的响应

        Raises:
            DispatchError: 调度失败（重试耗尽）
        """
        import aiohttp

        url = f"{node.base_url}/engine/submit"
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=task,
                        timeout=aiohttp.ClientTimeout(total=self._timeout),
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            logger.debug("Dispatch success: node=%s, attempt=%d",
                                         node.node_id, attempt)
                            return result
                        else:
                            body = await resp.text()
                            raise DispatchError(
                                f"Node {node.node_id} returned HTTP {resp.status}: {body}"
                            )
            except DispatchError as e:
                # HTTP 非 200 响应触发重试
                last_error = e
                logger.warning("Dispatch attempt %d failed for node %s: %s",
                               attempt, node.node_id, e)
                if attempt < self._max_retries:
                    await asyncio.sleep(0.5 * attempt)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                logger.warning("Dispatch attempt %d failed for node %s: %s",
                               attempt, node.node_id, e)
                # 等待短暂退避后重试
                if attempt < self._max_retries:
                    await asyncio.sleep(0.5 * attempt)

        raise DispatchError(
            f"All {self._max_retries} attempts failed for node {node.node_id}: {last_error}"
        )

    async def dispatch_with_fallback(
        self,
        primary_node: NodeConfig,
        task: Dict[str, Any],
        fallback_nodes: List[NodeConfig],
    ) -> Dict[str, Any]:
        """调度任务，主节点失败时自动转移到备选节点

        Args:
            primary_node: 首选节点
            task: 任务数据
            fallback_nodes: 备选节点列表（不含 primary_node）

        Returns:
            远程节点返回的响应

        Raises:
            DispatchError: 所有节点均失败
        """
        # 先尝试主节点
        try:
            return await self.dispatch(primary_node, task)
        except DispatchError as e:
            logger.warning("Primary node %s failed, trying fallbacks: %s",
                           primary_node.node_id, e)

        # 尝试备选节点
        available = [n for n in fallback_nodes if n.is_available and n.node_id != primary_node.node_id]
        for node in available:
            try:
                return await self.dispatch(node, task)
            except DispatchError:
                continue

        raise DispatchError(
            f"All nodes failed. Primary: {primary_node.node_id}, "
            f"fallbacks: {[n.node_id for n in available]}"
        )


class DispatchError(Exception):
    """跨节点调度失败"""
    pass


# ============================================================
# 分布式 Worker Pool
# ============================================================

class DistributedWorkerPool:
    """分布式 Worker Pool -- 跨节点任务调度

    集成 FileHashRouter + NodeRegistry + CrossNodeDispatcher，
    提供统一的任务调度接口。

    用法:
        pool = DistributedWorkerPool()
        pool.registry.register(NodeConfig("n1", "localhost", 8001, capacity=5))
        await pool.start()
        result = await pool.dispatch_task({"task_id": "t1", "files": ["src/main.py"]})
        await pool.shutdown()
    """

    def __init__(
        self,
        router: Optional[FileHashRouter] = None,
        registry: Optional[NodeRegistry] = None,
        dispatcher: Optional[CrossNodeDispatcher] = None,
        heartbeat_interval: float = 10.0,
    ):
        self.router = router or FileHashRouter()
        self.registry = registry or NodeRegistry()
        self.dispatcher = dispatcher or CrossNodeDispatcher()
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._started = False
        self._stats = {
            "tasks_dispatched": 0,
            "tasks_failed": 0,
            "heartbeat_cycles": 0,
        }

    async def start(self) -> None:
        """启动分布式池"""
        if self._started:
            return
        self._started = True
        # 启动后台心跳检测
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("DistributedWorkerPool started with %d nodes",
                     self.registry.node_count)

    async def shutdown(self) -> None:
        """关闭分布式池"""
        self._started = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        logger.info("DistributedWorkerPool shutdown")

    async def dispatch_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """调度任务到最合适的节点

        根据任务中的 files 字段进行 hash 路由。
        如果文件列表为空或路由失败，回退到最小负载节点。

        Args:
            task: 任务数据，应包含可选的 "files" 字段

        Returns:
            远程节点的响应数据
        """
        if not self._started:
            raise RuntimeError("DistributedWorkerPool not started. Call start() first.")

        nodes = self.registry.get_active_nodes()
        if not nodes:
            raise DispatchError("No active nodes available")

        # 提取文件列表进行路由
        files = task.get("files", [])
        target_node = None

        if files:
            # 按 hash 最小的文件路由，改善多文件任务的分布
            target_file = min(files, key=lambda f: self.router._hash_file(f))
            target_node = self.router.route_with_fallback(target_file, nodes)

        # 无文件或路由失败，回退到第一个可用节点
        if target_node is None:
            target_node = nodes[0] if nodes else None

        if target_node is None:
            raise DispatchError("No available node for routing")

        try:
            result = await self.dispatcher.dispatch_with_fallback(
                primary_node=target_node,
                task=task,
                fallback_nodes=nodes,
            )
            self._stats["tasks_dispatched"] += 1
            return result
        except DispatchError:
            self._stats["tasks_failed"] += 1
            raise

    def get_node_for_file(self, file_path: str) -> Optional[NodeConfig]:
        """查询文件会被路由到哪个节点（不实际执行）"""
        nodes = self.registry.get_active_nodes()
        return self.router.route_with_fallback(file_path, nodes)

    def stats(self) -> Dict[str, Any]:
        """返回统计信息"""
        nodes = self.registry.get_all_nodes()
        return {
            **self._stats,
            "total_nodes": len(nodes),
            "active_nodes": sum(1 for n in nodes if n.is_available),
            "offline_nodes": sum(1 for n in nodes if n.status == NodeStatus.OFFLINE),
        }

    async def _heartbeat_loop(self) -> None:
        """后台心跳检测循环"""
        while self._started:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                self._detect_offline()
                self._stats["heartbeat_cycles"] += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat loop error: %s", e)

    def _detect_offline(self) -> None:
        """触发节点离线检测"""
        self.registry._detect_offline_nodes()


# ============================================================
# 工厂函数
# ============================================================

def create_distributed_pool(
    nodes_config_path: str,
    heartbeat_interval: float = 10.0,
    heartbeat_timeout: float = 30.0,
) -> DistributedWorkerPool:
    """从 JSON 配置文件创建分布式池

    配置文件格式:
        [
            {"node_id": "n1", "host": "localhost", "port": 8001, "capacity": 5},
            {"node_id": "n2", "host": "192.168.1.100", "port": 8001, "capacity": 10}
        ]

    Args:
        nodes_config_path: 节点配置文件路径
        heartbeat_interval: 心跳检测间隔（秒）
        heartbeat_timeout: 心跳超时阈值（秒）

    Returns:
        配置好的 DistributedWorkerPool 实例
    """
    path = Path(nodes_config_path)
    if not path.exists():
        raise FileNotFoundError(f"Nodes config not found: {nodes_config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_nodes = json.load(f)

    registry = NodeRegistry(heartbeat_timeout=heartbeat_timeout)
    for item in raw_nodes:
        node = NodeConfig(
            node_id=item["node_id"],
            host=item["host"],
            port=item["port"],
            capacity=item.get("capacity", 5),
        )
        registry.register(node)

    pool = DistributedWorkerPool(
        registry=registry,
        heartbeat_interval=heartbeat_interval,
    )
    logger.info("Created distributed pool with %d nodes from %s",
                registry.node_count, nodes_config_path)
    return pool

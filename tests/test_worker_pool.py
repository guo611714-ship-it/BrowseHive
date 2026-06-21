"""Worker Pool 测试 -- 代理实例池管理"""

import asyncio
import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.engine.worker_pool import (
    WorkerPool, AgentInstance, InstanceStatus, PoolConfig,
    DEFAULT_POOL_CONFIGS,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AgentInstance 数据类测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAgentInstance:
    def test_create_instance(self):
        inst = AgentInstance(instance_id="t-0001", agent_type="neiguan_yingzao")
        assert inst.instance_id == "t-0001"
        assert inst.agent_type == "neiguan_yingzao"
        assert inst.status == InstanceStatus.IDLE
        assert inst.tasks_completed == 0
        assert inst.current_task is None

    def test_assign_and_release(self):
        inst = AgentInstance(instance_id="t-0002", agent_type="test")
        inst.assign("task-abc")
        assert inst.status == InstanceStatus.BUSY
        assert inst.current_task == "task-abc"
        assert inst.busy_since is not None

        inst.release()
        assert inst.status == InstanceStatus.IDLE
        assert inst.current_task is None
        assert inst.tasks_completed == 1

    def test_stuck_detection(self):
        inst = AgentInstance(instance_id="t-0003", agent_type="test")
        inst.assign("task-stuck")
        # 模拟超时: 手动设置 busy_since
        inst.busy_since = time.time() - 600
        assert inst.is_stuck(300.0) is True

    def test_not_stuck_when_idle(self):
        inst = AgentInstance(instance_id="t-0004", agent_type="test")
        assert inst.is_stuck(300.0) is False

    def test_not_stuck_within_timeout(self):
        inst = AgentInstance(instance_id="t-0005", agent_type="test")
        inst.assign("task-ok")
        assert inst.is_stuck(300.0) is False

    def test_busy_duration(self):
        inst = AgentInstance(instance_id="t-0006", agent_type="test")
        assert inst.busy_duration == 0.0

        inst.assign("task-dur")
        inst.busy_since = time.time() - 10
        dur = inst.busy_duration
        assert 9.0 < dur < 11.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WorkerPool 核心测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWorkerPool:
    @pytest.fixture
    def pool(self):
        return WorkerPool()

    @pytest.mark.asyncio
    async def test_start_and_stats(self, pool):
        """启动后应有预热实例"""
        await pool.start()
        s = pool.stats()
        assert s["total_instances"] == 3  # 3 种类型各 1 个
        assert s["idle_count"] == 3
        assert s["busy_count"] == 0
        assert s["tasks_completed"] == 0

    @pytest.mark.asyncio
    async def test_acquire_idle(self, pool):
        """acquire 应返回空闲实例并标记为 busy"""
        await pool.start()
        inst = await pool.acquire("neiguan_yingzao", task_id="t1")
        assert inst is not None
        assert inst.status == InstanceStatus.BUSY
        assert inst.current_task == "t1"

    @pytest.mark.asyncio
    async def test_release(self, pool):
        """release 后实例应回到 idle"""
        await pool.start()
        inst = await pool.acquire("neiguan_yingzao")
        pool.release(inst)
        assert inst.status == InstanceStatus.IDLE
        assert inst.tasks_completed == 1

    @pytest.mark.asyncio
    async def test_auto_scale(self, pool):
        """当所有实例 busy 时应自动扩容"""
        await pool.start()

        # 占满唯一的实例
        inst1 = await pool.acquire("dongchang_tanshi")
        assert inst1 is not None

        # 再获取应该自动创建新实例
        inst2 = await pool.acquire("dongchang_tanshi")
        assert inst2 is not None
        assert inst2 is not inst1

        s = pool.stats()
        assert s["busy_count"] == 2

    @pytest.mark.asyncio
    async def test_pool_exhausted(self):
        """达到 max_size 后 acquire 应返回 None"""
        config = {"test_agent": PoolConfig(min_size=0, max_size=2)}
        pool = WorkerPool(configs=config)
        await pool.start()

        i1 = await pool.acquire("test_agent")
        i2 = await pool.acquire("test_agent")
        i3 = await pool.acquire("test_agent")  # 超限

        assert i1 is not None
        assert i2 is not None
        assert i3 is None

    @pytest.mark.asyncio
    async def test_acquire_unknown_type(self):
        """获取未注册类型应自动创建"""
        config = {}
        pool = WorkerPool(configs=config)
        await pool.start()

        inst = await pool.acquire("new_type")
        assert inst is not None
        assert inst.agent_type == "new_type"

    @pytest.mark.asyncio
    async def test_health_check_stuck(self):
        """健康检查应检测并回收卡住的实例"""
        config = {"slow_agent": PoolConfig(min_size=1, max_size=3, warmup_timeout=1.0)}
        pool = WorkerPool(configs=config)
        await pool.start()

        inst = await pool.acquire("slow_agent", task_id="stuck-task")
        # 模拟卡住
        inst.busy_since = time.time() - 10

        result = await pool.health_check()
        assert result["recovered"] == 1
        assert len(result["stuck_instances"]) == 1
        assert result["stuck_instances"][0]["task"] == "stuck-task"

        # 回收后实例应空闲
        assert inst.status == InstanceStatus.IDLE

    @pytest.mark.asyncio
    async def test_health_check_no_stuck(self):
        """无卡住实例时健康检查应返回 0"""
        pool = WorkerPool()
        await pool.start()
        result = await pool.health_check(timeout=9999)
        assert result["recovered"] == 0

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """shutdown 后所有实例应停止"""
        pool = WorkerPool()
        await pool.start()
        await pool.shutdown()
        s = pool.stats()
        assert s["total_instances"] == 0

    @pytest.mark.asyncio
    async def test_double_start(self):
        """重复 start 不应创建多余实例"""
        pool = WorkerPool()
        await pool.start()
        await pool.start()
        s = pool.stats()
        assert s["total_instances"] == 3

    @pytest.mark.asyncio
    async def test_stats_by_type(self):
        """按类型统计应正确分组"""
        pool = WorkerPool()
        await pool.start()
        inst = await pool.acquire("neiguan_yingzao")
        by_type = pool.stats()["by_type"]
        assert by_type["neiguan_yingzao"]["busy"] == 1
        assert by_type["neiguan_yingzao"]["idle"] == 0

    @pytest.mark.asyncio
    async def test_summary(self):
        """summary 应返回可读字符串"""
        pool = WorkerPool()
        await pool.start()
        s = pool.summary()
        assert "Pool:" in s
        assert "idle" in s

    def test_register_type(self):
        """运行时注册新类型"""
        pool = WorkerPool()
        pool.register_type("custom_agent", PoolConfig(min_size=0, max_size=3))
        assert pool.get_config("custom_agent") is not None
        assert pool.get_config("custom_agent").max_size == 3

    def test_default_configs(self):
        """默认配置应包含三种常用类型"""
        assert "neiguan_yingzao" in DEFAULT_POOL_CONFIGS
        assert "xiaohuangmen" in DEFAULT_POOL_CONFIGS
        assert "dongchang_tanshi" in DEFAULT_POOL_CONFIGS

    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """并发获取不应产生竞态"""
        pool = WorkerPool(configs={
            "concurrent": PoolConfig(min_size=0, max_size=3)
        })
        await pool.start()

        async def do_acquire():
            return await pool.acquire("concurrent")

        results = await asyncio.gather(*[do_acquire() for _ in range(5)])
        acquired = [r for r in results if r is not None]
        # 最多获取 3 个（max_size=3）
        assert len(acquired) <= 3

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self):
        """多次 acquire/release 循环应正常"""
        pool = WorkerPool(configs={
            "cyclic": PoolConfig(min_size=1, max_size=2)
        })
        await pool.start()

        for i in range(10):
            inst = await pool.acquire("cyclic", task_id=f"cycle-{i}")
            assert inst is not None
            pool.release(inst)

        s = pool.stats()
        assert s["tasks_completed"] == 10
        # 池中实例数不应无限增长
        assert s["total_instances"] <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

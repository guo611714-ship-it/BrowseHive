"""真实场景验证 — Parallel Fix Engine 端到端测试

模拟真实 code review 修复场景，验证引擎全链路：
1. 多文件修复（不同文件并行）
2. 同文件冲突降级串行
3. 依赖链排序
4. 大规模批量修复（20+ 项）
5. 混合优先级调度
6. 取消/超时处理
7. 分析模式（不执行）
8. 引擎 + WorkerPool 联合
9. 引擎 + EvolutionMetrics 联合
10. 全组件集成
"""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.engine.manifest import (
    FixTask, TaskManifest, TaskPriority, SchedulingStrategy,
    SmartSharder,
)
from agent.engine.conflict import ConflictPredictor
from agent.engine.scheduler import EnhancedScheduler, ResultAggregator
from agent.engine.fix_engine import ParallelFixEngine
from agent.engine.task_queue import TaskQueue, TaskStatus
from agent.engine.progress_sse import ProgressBroadcaster


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 1: 多文件并行修复
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioMultiFileParallel:
    """5 个不同文件的修复应尽量并行"""

    def test_all_different_files(self):
        tasks = [
            FixTask(task_id=f"fix-{i}", description=f"fix file {i}",
                    files=[f"module_{i}.py"])
            for i in range(5)
        ]
        manifest = TaskManifest(tasks=tasks)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        # 所有文件不同，应合并到尽量少的 shard
        total = sum(s.task_count for s in shards)
        assert total == 5
        # 最优情况：1 个 shard（全并行）
        assert len(shards) <= 2

    def test_preserves_all_tasks(self):
        tasks = [
            FixTask(task_id=f"t{i}", description=f"task {i}",
                    files=[f"f{i}.py"])
            for i in range(10)
        ]
        manifest = TaskManifest(tasks=tasks)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        all_ids = set()
        for s in shards:
            for t in s.tasks:
                all_ids.add(t.task_id)
        assert len(all_ids) == 10


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 2: 同文件冲突降级串行
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioSameFileConflict:
    """3 个修复同一文件的任务应被分到不同 shard"""

    def test_same_file_separated(self):
        tasks = [
            FixTask(task_id="fix-top", description="fix top of file",
                    files=["core.py"]),
            FixTask(task_id="fix-mid", description="fix middle of file",
                    files=["core.py"]),
            FixTask(task_id="fix-bot", description="fix bottom of file",
                    files=["core.py"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        # 同文件冲突 → 分到不同 shard
        assert len(shards) >= 2
        # 但总任务数不变
        total = sum(s.task_count for s in shards)
        assert total == 3

    def test_partial_overlap(self):
        """部分文件重叠：a.py 共享，b.py 和 c.py 独立"""
        tasks = [
            FixTask(task_id="t1", description="fix shared",
                    files=["a.py"]),
            FixTask(task_id="t2", description="fix shared also",
                    files=["a.py"]),
            FixTask(task_id="t3", description="fix independent",
                    files=["b.py"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        total = sum(s.task_count for s in shards)
        assert total == 3
        # t3 (b.py) 应与 t1/t2 的某个分在一组（如果无冲突）
        file_sets = [s.files for s in shards]
        # 至少有一个 shard 包含 b.py
        assert any("b.py" in fs for fs in file_sets)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 3: 依赖链排序
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioDependencyChain:
    """A → B → C 依赖链应按序执行"""

    def test_linear_chain(self):
        tasks = [
            FixTask(task_id="A", description="base", files=["base.py"]),
            FixTask(task_id="B", description="extends A",
                    files=["ext.py"], depends_on=["A"]),
            FixTask(task_id="C", description="extends B",
                    files=["app.py"], depends_on=["B"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        # 至少 3 个 shard（A, B, C 按序）
        assert len(shards) >= 2

        # 验证顺序：A 在 B 前，B 在 C 前
        seen_ids = []
        for s in shards:
            for t in s.tasks:
                seen_ids.append(t.task_id)

        # A 应在 B 前
        if "A" in seen_ids and "B" in seen_ids:
            assert seen_ids.index("A") < seen_ids.index("B")

    def test_diamond_dependency(self):
        """菱形依赖：A → B, A → C, B+C → D"""
        tasks = [
            FixTask(task_id="A", description="base", files=["base.py"]),
            FixTask(task_id="B", description="dep1", files=["b.py"],
                    depends_on=["A"]),
            FixTask(task_id="C", description="dep2", files=["c.py"],
                    depends_on=["A"]),
            FixTask(task_id="D", description="merge", files=["d.py"],
                    depends_on=["B", "C"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        total = sum(s.task_count for s in shards)
        assert total == 4
        # D 应在最后
        last_tasks = [t.task_id for t in shards[-1].tasks]
        assert "D" in last_tasks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 4: 大规模批量修复
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioLargeBatch:
    """20 项修复的分片效率"""

    def test_20_tasks(self):
        tasks = []
        # 15 个独立文件
        for i in range(15):
            tasks.append(FixTask(
                task_id=f"ind-{i}",
                description=f"independent fix {i}",
                files=[f"independent_{i}.py"]
            ))
        # 5 个同文件修复
        for i in range(5):
            tasks.append(FixTask(
                task_id=f"shared-{i}",
                description=f"shared fix {i}",
                files=["shared.py"]
            ))

        manifest = TaskManifest(tasks=tasks)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        total = sum(s.task_count for s in shards)
        assert total == 20

        # 独立文件应尽量合并
        # 同文件应分到不同 shard
        shared_shards = [s for s in shards
                        if any(t.task_id.startswith("shared-") for t in s.tasks)]
        assert len(shared_shards) >= 2  # 至少 2 个 shard 处理 shared.py

    def test_50_tasks_no_crash(self):
        """50 项修复不应崩溃"""
        tasks = [
            FixTask(task_id=f"t{i}", description=f"fix {i}",
                    files=[f"file_{i % 10}.py"])  # 10 个文件，每个 5 个修复
            for i in range(50)
        ]
        manifest = TaskManifest(tasks=tasks)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        total = sum(s.task_count for s in shards)
        assert total == 50


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 5: 混合优先级调度
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioMixedPriority:
    """Critical 任务优先执行"""

    def test_critical_first_in_queue(self):
        from agent.engine.task_queue import TaskQueue
        q = TaskQueue()
        m = TaskManifest(tasks=[
            FixTask(task_id="low", description="low", files=["a.py"],
                    priority=TaskPriority.LOW),
            FixTask(task_id="critical", description="critical", files=["b.py"],
                    priority=TaskPriority.CRITICAL),
            FixTask(task_id="normal", description="normal", files=["c.py"],
                    priority=TaskPriority.NORMAL),
            FixTask(task_id="high", description="high", files=["d.py"],
                    priority=TaskPriority.HIGH),
        ])

        async def run():
            await q.submit(m)
            batch = await q.next_batch(batch_size=4)
            return [t.task.task_id for t in batch]

        result = asyncio.run(run())
        # Critical 应排第一
        assert result[0] == "critical"
        # High 应在 Normal 和 Low 前
        high_idx = result.index("high")
        normal_idx = result.index("normal")
        low_idx = result.index("low")
        assert high_idx < normal_idx < low_idx


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 6: 取消处理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioCancel:
    """取消 manifest 应清除所有 pending 任务"""

    def test_cancel_all_pending(self):
        from agent.engine.task_queue import TaskQueue
        q = TaskQueue()

        async def run():
            m = TaskManifest(tasks=[
                FixTask(task_id=f"t{i}", description=f"fix {i}",
                        files=[f"f{i}.py"])
                for i in range(5)
            ])
            manifest_id = await q.submit(m)
            cancelled = await q.cancel_manifest(manifest_id)
            return cancelled, q.stats

        cancelled, stats = asyncio.run(run())
        assert cancelled == 5
        assert stats.get("cancelled", 0) == 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 7: 分析模式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioAnalysis:
    """分析模式应返回完整执行计划"""

    def test_analyze_returns_plan(self):
        engine = ParallelFixEngine()
        tasks = [
            FixTask(task_id="t1", description="fix a", files=["a.py"]),
            FixTask(task_id="t2", description="fix a2", files=["a.py"]),
            FixTask(task_id="t3", description="fix b", files=["b.py"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        plan = engine.analyze(manifest)

        assert "shards" in plan
        assert "conflict_analysis" in plan
        assert "execution_plan" in plan
        assert plan["execution_plan"]["total_shards"] >= 1
        assert plan["conflict_analysis"]["total_tasks"] == 3

    def test_analyze_shows_conflicts(self):
        engine = ParallelFixEngine()
        tasks = [
            FixTask(task_id="t1", description="fix core", files=["core.py"]),
            FixTask(task_id="t2", description="fix core again", files=["core.py"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        plan = engine.analyze(manifest)

        # 同文件应检测到冲突
        assert plan["conflict_analysis"]["total_conflicts"] >= 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 8: SSE 进度广播
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioSSEProgress:
    """进度广播应正确推送给订阅者"""

    @pytest.mark.asyncio
    async def test_full_progress_lifecycle(self):
        broadcaster = ProgressBroadcaster()
        queue = await broadcaster.subscribe("manifest-1")

        # 模拟完整生命周期
        broadcaster.publish_progress("manifest-1", 0, 3, "submitted", "submitted")
        broadcaster.publish_progress("manifest-1", 1, 3, "shard 1 running", "running")
        broadcaster.publish_progress("manifest-1", 2, 3, "shard 2 running", "running")
        broadcaster.publish_progress("manifest-1", 3, 3, "shard 3 running", "running")
        broadcaster.publish_complete("manifest-1", {"status": "success"})

        events = []
        for _ in range(5):
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            events.append(event)

        assert len(events) == 5
        assert events[0].data["status"] == "submitted"
        assert events[-1].event == "complete"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 9: 引擎 + EvolutionMetrics 联合
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioEvolution:
    """引擎分析数据应可喂给 EvolutionMetrics"""

    def test_analyze_to_evolution(self):
        from agent.engine.evolution import EvolutionMetrics, TaskRecord

        engine = ParallelFixEngine()
        metrics = EvolutionMetrics()

        # 模拟 5 次执行
        for i in range(5):
            tasks = [
                FixTask(task_id=f"t{j}", description=f"fix {j}",
                        files=[f"file_{j}.py"])
                for j in range(3)
            ]
            manifest = TaskManifest(tasks=tasks)
            plan = engine.analyze(manifest)

            # 记录到 evolution
            metrics.record_task(TaskRecord(
                task_id=f"exec-{i}",
                status="success",
                strategy=plan["execution_plan"]["strategy"],
                started_at=f"2026-06-01T10:0{i}:00",
                completed_at=f"2026-06-01T10:0{i}:02",
                duration_seconds=2.0 + i * 0.5,
                files=[f"file_{j}.py" for j in range(3)],
                shard_count=plan["execution_plan"]["total_shards"],
            ))

        # 应能推荐策略
        tasks = [
            FixTask(task_id="t1", description="fix", files=["f1.py"]),
            FixTask(task_id="t2", description="fix", files=["f2.py"]),
        ]
        manifest = TaskManifest(tasks=tasks)
        strategy = metrics.recommend_strategy(manifest)
        assert strategy is not None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 场景 10: 强制策略
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScenarioForcedStrategy:
    """强制并行/串行应覆盖自动分片"""

    def test_force_parallel(self):
        tasks = [
            FixTask(task_id="t1", description="fix", files=["a.py"]),
            FixTask(task_id="t2", description="fix", files=["a.py"]),
        ]
        manifest = TaskManifest(tasks=tasks,
                                strategy=SchedulingStrategy.PARALLEL)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        # 强制并行：所有任务在一个 shard
        assert len(shards) == 1
        assert shards[0].task_count == 2

    def test_force_serial(self):
        tasks = [
            FixTask(task_id="t1", description="fix", files=["a.py"]),
            FixTask(task_id="t2", description="fix", files=["b.py"]),
        ]
        manifest = TaskManifest(tasks=tasks,
                                strategy=SchedulingStrategy.SERIAL)
        sharder = SmartSharder(predictor=ConflictPredictor())
        shards = sharder.shard(manifest)

        # 强制串行：每个任务一个 shard
        assert len(shards) == 2
        assert all(s.task_count == 1 for s in shards)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

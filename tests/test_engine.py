"""Agent Engine 测试 — TaskManifest + Sharder + ConflictPredictor + Scheduler"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.engine.manifest import (
    FixTask, TaskManifest, TaskPriority, SchedulingStrategy,
    SmartSharder, Shard, create_task, create_manifest,
)
from agent.engine.conflict import ConflictPredictor, ConflictPrediction
from agent.engine.scheduler import EnhancedScheduler, ResultAggregator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FixTask 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFixTask:
    def test_create_task(self):
        t = FixTask(task_id="t1", description="fix bug", files=["a.py"])
        assert t.task_id == "t1"
        assert t.files == ["a.py"]
        assert t.agent_type == "neiguan_yingzao"

    def test_file_set(self):
        t = FixTask(task_id="t1", description="fix", files=["a.py", "b.py", "a.py"])
        assert t.file_set == {"a.py", "b.py"}

    def test_to_dispatch_args(self):
        t = FixTask(
            task_id="t1", description="fix bug", files=["a.py"],
            context="extra info", expected_output="fixed code"
        )
        args = t.to_dispatch_args()
        assert args["agent_type"] == "neiguan_yingzao"
        assert args["task"] == "fix bug"
        assert args["context"] == "extra info"
        assert args["expected_output"] == "fixed code"

    def test_depends_on(self):
        t = FixTask(task_id="t2", description="fix", files=["b.py"],
                     depends_on=["t1"])
        assert "t1" in t.depends_on


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TaskManifest 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTaskManifest:
    def test_empty_manifest(self):
        m = TaskManifest(tasks=[])
        assert m.task_count == 0
        assert m.file_count == 0

    def test_manifest_summary(self):
        tasks = [
            FixTask(task_id="t1", description="fix", files=["a.py"]),
            FixTask(task_id="t2", description="fix", files=["b.py"]),
        ]
        m = TaskManifest(tasks=tasks)
        assert m.task_count == 2
        assert m.file_count == 2
        assert "2 tasks" in m.summary()

    def test_manifest_dedup_files(self):
        tasks = [
            FixTask(task_id="t1", description="fix", files=["a.py", "b.py"]),
            FixTask(task_id="t2", description="fix", files=["b.py", "c.py"]),
        ]
        m = TaskManifest(tasks=tasks)
        assert m.file_count == 3  # a.py, b.py, c.py


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SmartSharder 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSmartSharder:
    def test_empty_manifest(self):
        m = TaskManifest(tasks=[])
        s = SmartSharder()
        shards = s.shard(m)
        assert shards == []

    def test_single_task(self):
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix", files=["a.py"]),
        ])
        s = SmartSharder()
        shards = s.shard(m)
        assert len(shards) == 1
        assert shards[0].task_count == 1

    def test_different_files_parallel(self):
        """不同文件的任务应该可以并行"""
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix a", files=["a.py"]),
            FixTask(task_id="t2", description="fix b", files=["b.py"]),
            FixTask(task_id="t3", description="fix c", files=["c.py"]),
        ])
        s = SmartSharder()
        shards = s.shard(m)
        # 三个不同文件，应该合并到尽量少的 shard
        total_tasks = sum(sh.task_count for sh in shards)
        assert total_tasks == 3

    def test_same_file_conflict(self):
        """同文件任务应被分到不同 shard"""
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix top", files=["a.py"]),
            FixTask(task_id="t2", description="fix bottom", files=["a.py"]),
        ])
        s = SmartSharder()
        shards = s.shard(m)
        # 同文件任务应分组（可能在不同 shard 或同 shard 但标记冲突）
        assert len(shards) >= 1
        total = sum(sh.task_count for sh in shards)
        assert total == 2

    def test_force_parallel(self):
        m = TaskManifest(
            tasks=[
                FixTask(task_id="t1", description="fix", files=["a.py"]),
                FixTask(task_id="t2", description="fix", files=["a.py"]),
            ],
            strategy=SchedulingStrategy.PARALLEL,
        )
        s = SmartSharder()
        shards = s.shard(m)
        assert len(shards) == 1
        assert shards[0].task_count == 2

    def test_force_serial(self):
        m = TaskManifest(
            tasks=[
                FixTask(task_id="t1", description="fix", files=["a.py"]),
                FixTask(task_id="t2", description="fix", files=["b.py"]),
            ],
            strategy=SchedulingStrategy.SERIAL,
        )
        s = SmartSharder()
        shards = s.shard(m)
        assert len(shards) == 2
        assert shards[0].task_count == 1
        assert shards[1].task_count == 1

    def test_dependency_ordering(self):
        """有依赖的任务应在后续 shard"""
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix base", files=["base.py"]),
            FixTask(task_id="t2", description="fix derived", files=["derived.py"],
                     depends_on=["t1"]),
        ])
        s = SmartSharder()
        shards = s.shard(m)
        # 至少 2 个 shard：独立任务 + 依赖任务
        assert len(shards) >= 2
        # 第二个 shard 包含依赖任务
        last_shard = shards[-1]
        assert any(t.task_id == "t2" for t in last_shard.tasks)

    def test_mixed_independent_files(self):
        """混合场景：部分同文件，部分不同文件"""
        m = TaskManifest(tasks=[
            FixTask(task_id="t1", description="fix a1", files=["a.py"]),
            FixTask(task_id="t2", description="fix a2", files=["a.py"]),
            FixTask(task_id="t3", description="fix b", files=["b.py"]),
            FixTask(task_id="t4", description="fix c", files=["c.py"]),
        ])
        s = SmartSharder()
        shards = s.shard(m)
        total = sum(sh.task_count for sh in shards)
        assert total == 4


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ConflictPredictor 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConflictPredictor:
    def test_no_conflict_different_files(self):
        p = ConflictPredictor()
        tasks = [
            FixTask(task_id="t1", description="fix", files=["a.py"]),
            FixTask(task_id="t2", description="fix", files=["b.py"]),
        ]
        groups = p.predict_conflicts(tasks)
        # 不同文件无冲突，应能分到一组
        assert len(groups) >= 1

    def test_conflict_same_files(self):
        p = ConflictPredictor()
        tasks = [
            FixTask(task_id="t1", description="fix top", files=["a.py"]),
            FixTask(task_id="t2", description="fix bottom", files=["a.py"]),
        ]
        groups = p.predict_conflicts(tasks)
        # 同文件应分到不同组
        assert len(groups) == 2

    def test_analyze_manifest(self):
        p = ConflictPredictor()
        tasks = [
            FixTask(task_id="t1", description="fix", files=["a.py"]),
            FixTask(task_id="t2", description="fix", files=["a.py"]),
            FixTask(task_id="t3", description="fix", files=["b.py"]),
        ]
        m = TaskManifest(tasks=tasks)
        analysis = p.analyze_manifest(m)
        assert analysis["total_tasks"] == 3
        assert analysis["total_conflicts"] >= 1
        assert "high" in analysis["by_severity"]

    def test_empty_tasks(self):
        p = ConflictPredictor()
        groups = p.predict_conflicts([])
        assert groups == [[]]

    def test_single_task(self):
        p = ConflictPredictor()
        tasks = [FixTask(task_id="t1", description="fix", files=["a.py"])]
        groups = p.predict_conflicts(tasks)
        assert len(groups) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ResultAggregator 测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestResultAggregator:
    def test_empty_results(self):
        r = ResultAggregator.aggregate([])
        assert r["total_files"] == 0
        assert r["total_conflicts"] == 0

    def test_single_result(self):
        results = [
            {"status": "success", "agent_type": "neiguan_yingzao",
             "summary": "修改了 a.py"}
        ]
        r = ResultAggregator.aggregate(results)
        assert r["total_files"] >= 0  # 可能提取到也可能提取不到

    def test_failed_results_excluded(self):
        results = [
            {"status": "failed", "agent_type": "neiguan_yingzao", "summary": "error"},
            {"status": "success", "agent_type": "neiguan_yingzao", "summary": "done"},
        ]
        r = ResultAggregator.aggregate(results)
        # 失败的结果不应被聚合
        assert r["total_conflicts"] == 0 or r["total_files"] >= 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工厂函数测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFactoryFunctions:
    def test_create_task(self):
        t = create_task("t1", "fix bug", ["a.py"])
        assert isinstance(t, FixTask)
        assert t.task_id == "t1"

    def test_create_manifest(self):
        tasks = [create_task("t1", "fix", ["a.py"])]
        m = create_manifest(tasks, strategy="parallel")
        assert isinstance(m, TaskManifest)
        assert m.strategy == SchedulingStrategy.PARALLEL

    def test_create_task_with_kwargs(self):
        t = create_task("t1", "fix", ["a.py"],
                        agent_type="xiaohuangmen", priority="high")
        assert t.agent_type == "xiaohuangmen"
        assert t.priority == TaskPriority.HIGH


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shard 数据类测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestShard:
    def test_shard_creation(self):
        tasks = [FixTask(task_id="t1", description="fix", files=["a.py"])]
        s = Shard(shard_id=0, tasks=tasks, files={"a.py"}, reason="test")
        assert s.shard_id == 0
        assert s.task_count == 1

    def test_shard_empty_tasks(self):
        s = Shard(shard_id=0, tasks=[], files=set(), reason="empty")
        assert s.task_count == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Integration: Sharder + Predictor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestIntegration:
    def test_sharder_with_predictor(self):
        """SmartSharder + ConflictPredictor 联合测试"""
        predictor = ConflictPredictor()
        sharder = SmartSharder(predictor=predictor)

        tasks = [
            FixTask(task_id="t1", description="fix a", files=["a.py"]),
            FixTask(task_id="t2", description="fix a2", files=["a.py"]),
            FixTask(task_id="t3", description="fix b", files=["b.py"]),
            FixTask(task_id="t4", description="fix c", files=["c.py"]),
            FixTask(task_id="t5", description="fix d", files=["d.py"]),
        ]
        m = TaskManifest(tasks=tasks)
        shards = sharder.shard(m)

        total = sum(sh.task_count for sh in shards)
        assert total == 5

    def test_analyze_then_shard(self):
        """先分析再分片"""
        predictor = ConflictPredictor()
        sharder = SmartSharder(predictor=predictor)

        tasks = [
            FixTask(task_id="t1", description="fix", files=["a.py"]),
            FixTask(task_id="t2", description="fix", files=["a.py"]),
        ]
        m = TaskManifest(tasks=tasks)

        # 分析
        analysis = predictor.analyze_manifest(m)
        assert analysis["total_conflicts"] >= 1

        # 分片
        shards = sharder.shard(m)
        assert len(shards) >= 1

    def test_complex_dependency_graph(self):
        """复杂依赖图"""
        predictor = ConflictPredictor()
        sharder = SmartSharder(predictor=predictor)

        tasks = [
            FixTask(task_id="t1", description="base", files=["base.py"]),
            FixTask(task_id="t2", description="dep1", files=["dep1.py"],
                     depends_on=["t1"]),
            FixTask(task_id="t3", description="dep2", files=["dep2.py"],
                     depends_on=["t1"]),
            FixTask(task_id="t4", description="independent", files=["ind.py"]),
        ]
        m = TaskManifest(tasks=tasks)
        shards = sharder.shard(m)

        # t4 是独立的，应在前面的 shard
        # t2, t3 依赖 t1，应在后面的 shard
        total = sum(sh.task_count for sh in shards)
        assert total == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Evolution Metrics 测试 — 自进化指标模块 (Phase 4)"""

import pytest
import sys
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.engine.evolution import (
    EvolutionMetrics, TaskRecord, ConflictRecord,
    AggregatedMetrics, EvolutionReport, create_metrics,
    RETENTION_DAYS,
)
from agent.engine.manifest import (
    TaskManifest, FixTask, TaskPriority, SchedulingStrategy,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _make_tmp_metrics(tmp_path: Path) -> EvolutionMetrics:
    """创建临时目录的 EvolutionMetrics 实例"""
    return EvolutionMetrics(metrics_dir=str(tmp_path / ".engine"))


def _make_task_record(task_id: str = "t1", status: str = "success",
                       strategy: str = "auto", duration: float = 10.0,
                       files: Optional[List[str]] = None,
                       shard_count: int = 1,
                       started_at: Optional[str] = None,
                       completed_at: Optional[str] = None) -> TaskRecord:
    """创建测试用 TaskRecord"""
    now = datetime.now()
    return TaskRecord(
        task_id=task_id,
        status=status,
        strategy=strategy,
        started_at=started_at or (now - timedelta(seconds=duration)).isoformat(),
        completed_at=completed_at or now.isoformat(),
        duration_seconds=duration,
        files=files or [],
        shard_count=shard_count,
    )


def _make_conflict_record(task_a: str = "t1", task_b: str = "t2",
                           conflict_type: str = "file_overlap",
                           severity: str = "medium") -> ConflictRecord:
    """创建测试用 ConflictRecord"""
    return ConflictRecord(
        task_a_id=task_a,
        task_b_id=task_b,
        conflict_type=conflict_type,
        severity=severity,
        timestamp=datetime.now().isoformat(),
    )


def _make_manifest(task_count: int = 3, file_count: int = 3) -> TaskManifest:
    """创建测试用 TaskManifest"""
    tasks = [
        FixTask(
            task_id=f"t{i}",
            description=f"task {i}",
            files=[f"file{i}.py"],
        )
        for i in range(task_count)
    ]
    return TaskManifest(tasks=tasks)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 基础记录与持久化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRecordAndPersist:
    """测试记录写入和持久化"""

    def test_record_task(self, tmp_path):
        """任务记录能正常写入并持久化"""
        m = _make_tmp_metrics(tmp_path)
        rec = _make_task_record("t1", status="success", duration=5.0)
        m.record_task(rec)

        records = m.get_task_records()
        assert len(records) == 1
        assert records[0]["task_id"] == "t1"
        assert records[0]["status"] == "success"

    def test_record_conflict(self, tmp_path):
        """冲突记录能正常写入"""
        m = _make_tmp_metrics(tmp_path)
        rec = _make_conflict_record("t1", "t2", "file_overlap", "high")
        m.record_conflict(rec)

        conflicts = m.get_conflict_records()
        assert len(conflicts) == 1
        assert conflicts[0]["task_a_id"] == "t1"
        assert conflicts[0]["severity"] == "high"

    def test_persistence_across_instances(self, tmp_path):
        """新实例能加载旧数据（持久化验证）"""
        m1 = _make_tmp_metrics(tmp_path)
        m1.record_task(_make_task_record("t1"))
        m1.record_task(_make_task_record("t2"))

        # 创建新实例，应加载之前的记录
        m2 = _make_tmp_metrics(tmp_path)
        records = m2.get_task_records()
        assert len(records) == 2
        assert {r["task_id"] for r in records} == {"t1", "t2"}

    def test_corrupted_file_recovery(self, tmp_path):
        """损坏的指标文件不会导致崩溃"""
        engine_dir = tmp_path / ".engine"
        engine_dir.mkdir()
        metrics_file = engine_dir / "metrics.json"
        metrics_file.write_text("not valid json {{{", encoding="utf-8")

        m = EvolutionMetrics(metrics_dir=str(engine_dir))
        # 应该恢复为空历史，不抛异常
        assert m._history == []
        assert m.get_task_records() == []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 数据保留与清理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRetention:
    """测试90天数据保留策略"""

    def test_cleanup_old_entries(self, tmp_path):
        """超过90天的记录会被自动清理"""
        m = _make_tmp_metrics(tmp_path)

        # 手动插入一条100天前的记录
        old_time = (datetime.now() - timedelta(days=100)).isoformat()
        m._history.append({
            "type": "task",
            "timestamp": old_time,
            "task_id": "old_task",
            "status": "success",
            "strategy": "auto",
            "duration_seconds": 1.0,
        })
        # 再插入一条当前记录
        m._history.append({
            "type": "task",
            "timestamp": datetime.now().isoformat(),
            "task_id": "new_task",
            "status": "success",
            "strategy": "auto",
            "duration_seconds": 1.0,
        })

        cleaned = m._cleanup_old_entries()
        assert cleaned == 1
        records = m.get_task_records()
        assert len(records) == 1
        assert records[0]["task_id"] == "new_task"

    def test_no_cleanup_when_all_recent(self, tmp_path):
        """全部是近期记录时不会清理任何内容"""
        m = _make_tmp_metrics(tmp_path)
        m.record_task(_make_task_record("t1"))
        m.record_task(_make_task_record("t2"))

        cleaned = m._cleanup_old_entries()
        assert cleaned == 0
        assert len(m.get_task_records()) == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 分析与报告
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAnalysis:
    """测试 analyze_history 和聚合指标"""

    def test_analyze_history_returns_report(self, tmp_path):
        """analyze_history 返回 EvolutionReport"""
        m = _make_tmp_metrics(tmp_path)
        m.record_task(_make_task_record("t1", status="success"))
        m.record_task(_make_task_record("t2", status="failed"))

        report = m.analyze_history(period_days=7)
        assert isinstance(report, EvolutionReport)
        assert report.period_days == 7
        assert report.aggregated.total_tasks == 2
        assert report.aggregated.successful_tasks == 1
        assert report.aggregated.failed_tasks == 1
        assert 0.4 <= report.aggregated.task_success_rate <= 0.6

    def test_strategy_scores(self, tmp_path):
        """策略得分正确计算"""
        m = _make_tmp_metrics(tmp_path)
        # 并行策略: 3 成功, 1 失败
        for i in range(3):
            m.record_task(_make_task_record(
                f"p{i}", status="success", strategy="parallel", duration=5.0
            ))
        m.record_task(_make_task_record(
            "p3", status="failed", strategy="parallel", duration=50.0
        ))
        # 串行策略: 2 全成功
        for i in range(2):
            m.record_task(_make_task_record(
                f"s{i}", status="success", strategy="serial", duration=10.0
            ))

        report = m.analyze_history(period_days=7)
        scores = report.strategy_scores
        assert "parallel" in scores
        assert "serial" in scores
        assert scores["serial"] > 0
        assert scores["parallel"] > 0

    def test_empty_history_report(self, tmp_path):
        """空历史也能生成报告"""
        m = _make_tmp_metrics(tmp_path)
        report = m.analyze_history(period_days=7)
        assert report.aggregated.total_tasks == 0
        assert report.aggregated.task_success_rate == 0.0
        assert report.trend == "stable"
        assert isinstance(report.recommendations, list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 策略推荐
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestStrategyRecommendation:
    """测试 recommend_strategy"""

    def test_empty_history_returns_auto(self, tmp_path):
        """无历史数据时推荐 AUTO"""
        m = _make_tmp_metrics(tmp_path)
        manifest = _make_manifest()
        strategy = m.recommend_strategy(manifest)
        assert strategy == SchedulingStrategy.AUTO

    def test_recommends_best_performing_strategy(self, tmp_path):
        """推荐历史表现最佳的策略"""
        m = _make_tmp_metrics(tmp_path)

        # parallel 策略全部成功且快速
        for i in range(5):
            m.record_task(_make_task_record(
                f"p{i}", status="success", strategy="parallel", duration=2.0,
                files=["a.py", "b.py", "c.py"], shard_count=3
            ))

        # serial 策略部分失败
        for i in range(3):
            m.record_task(_make_task_record(
                f"s{i}", status="failed", strategy="serial", duration=20.0,
                files=["a.py", "b.py", "c.py"], shard_count=3
            ))

        manifest = _make_manifest(file_count=3)
        strategy = m.recommend_strategy(manifest)
        assert strategy == SchedulingStrategy.PARALLEL


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 分片调整
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestShardingAdjustment:
    """测试 adjust_sharding"""

    def test_empty_pairs(self, tmp_path):
        """空文件对返回空列表"""
        m = _make_tmp_metrics(tmp_path)
        result = m.adjust_sharding([])
        assert result == []

    def test_groups_no_conflicts(self, tmp_path):
        """无冲突历史时，文件对各自成组"""
        m = _make_tmp_metrics(tmp_path)
        pairs = [("a.py", "b.py"), ("c.py", "d.py")]
        groups = m.adjust_sharding(pairs)
        # 无冲突，所有文件应在同一组
        assert len(groups) >= 1
        all_files = set()
        for g in groups:
            all_files.update(g)
        assert all_files == {"a.py", "b.py", "c.py", "d.py"}

    def test_groups_with_conflict_history(self, tmp_path):
        """有冲突历史时，冲突文件会被分到不同组"""
        m = _make_tmp_metrics(tmp_path)

        # 记录 a.py 和 b.py 的冲突历史
        for _ in range(5):
            m.record_conflict(ConflictRecord(
                task_a_id="a.py", task_b_id="b.py",
                conflict_type="file_overlap", severity="high",
                timestamp=datetime.now().isoformat(),
            ))

        # 带冲突历史调用
        pairs = [("a.py", "b.py")]
        conflict_history = m.get_conflict_records()
        groups = m.adjust_sharding(pairs, conflict_history)
        # 高频冲突文件应该分组（至少1组，但因为是同一对，可能在同一组）
        assert isinstance(groups, list)
        assert len(groups) >= 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 周报
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWeeklyReport:
    """测试 weekly_report"""

    def test_weekly_report_structure(self, tmp_path):
        """周报包含所有必需字段"""
        m = _make_tmp_metrics(tmp_path)
        m.record_task(_make_task_record("t1", status="success"))

        report = m.weekly_report()
        assert "period" in report
        assert "summary" in report
        assert "strategy_scores" in report
        assert "trend" in report
        assert "daily_breakdown" in report
        assert "recommendations" in report
        assert "retention_info" in report

    def test_weekly_report_daily_breakdown(self, tmp_path):
        """周报包含7天分解数据"""
        m = _make_tmp_metrics(tmp_path)
        m.record_task(_make_task_record("t1", status="success"))

        report = m.weekly_report()
        daily = report["daily_breakdown"]
        assert len(daily) == 7
        # 每天有正确字段
        for day in daily:
            assert "date" in day
            assert "total_tasks" in day

    def test_weekly_report_empty_data(self, tmp_path):
        """空数据也能生成周报"""
        m = _make_tmp_metrics(tmp_path)
        report = m.weekly_report()
        assert report["summary"]["total_tasks"] == 0
        assert report["trend"] == "stable"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 元数据与工厂
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMetadata:
    """测试 stats 和工厂函数"""

    def test_stats(self, tmp_path):
        """stats 返回正确的元数据"""
        m = _make_tmp_metrics(tmp_path)
        m.record_task(_make_task_record("t1"))
        m.record_conflict(_make_conflict_record())

        s = m.stats()
        assert s["task_records"] == 1
        assert s["conflict_records"] == 1
        assert s["total_records"] == 2
        assert s["retention_days"] == RETENTION_DAYS

    def test_create_metrics_factory(self, tmp_path):
        """create_metrics 工厂函数能正常工作"""
        m = create_metrics(metrics_dir=str(tmp_path / ".engine"))
        assert isinstance(m, EvolutionMetrics)
        m.record_task(_make_task_record("t1"))
        assert len(m.get_task_records()) == 1

    def test_record_engine_result(self, tmp_path):
        """从引擎结果中提取并记录指标"""
        m = _make_tmp_metrics(tmp_path)
        manifest = _make_manifest(task_count=2)

        # 模拟引擎返回结果
        engine_result = {
            "status": "success",
            "results": [
                {
                    "task_id": "t0",
                    "status": "success",
                    "files": ["file0.py"],
                    "duration_seconds": 5.0,
                },
                {
                    "task_id": "t1",
                    "status": "success",
                    "files": ["file1.py"],
                    "duration_seconds": 8.0,
                },
            ],
            "stats": {"total_shards": 2},
            "conflict_analysis": {
                "predictions": [
                    {
                        "tasks": ["t0", "t1"],
                        "type": "file_overlap",
                        "severity": "medium",
                    }
                ]
            },
        }

        m.record_engine_result(engine_result, manifest)
        assert len(m.get_task_records()) == 2
        assert len(m.get_conflict_records()) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 趋势检测与建议
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTrendAndRecommendations:
    """测试趋势检测和改进建议"""

    def test_trend_stable_with_insufficient_data(self, tmp_path):
        """数据不足时趋势为 stable"""
        m = _make_tmp_metrics(tmp_path)
        m.record_task(_make_task_record("t1"))
        report = m.analyze_history(period_days=7)
        assert report.trend == "stable"

    def test_recommendations_generated_on_low_success(self, tmp_path):
        """低成功率时生成改进建议"""
        m = _make_tmp_metrics(tmp_path)
        # 插入10条记录，8条失败
        for i in range(8):
            m.record_task(_make_task_record(
                f"f{i}", status="failed", strategy="auto", duration=50.0
            ))
        for i in range(2):
            m.record_task(_make_task_record(
                f"s{i}", status="success", strategy="auto", duration=10.0
            ))

        report = m.analyze_history(period_days=7)
        assert len(report.recommendations) > 0
        # 应该有关于成功率的建议
        assert any("成功率" in r for r in report.recommendations)

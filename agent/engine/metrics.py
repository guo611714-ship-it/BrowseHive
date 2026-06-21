"""Evolution Metrics — 数据结构定义

TaskRecord, ConflictRecord, AggregatedMetrics, EvolutionReport, create_metrics
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class TaskRecord:
    """单次任务执行记录"""
    task_id: str
    status: str                       # "success" | "failed" | "timeout"
    strategy: str                     # "auto" | "parallel" | "serial"
    started_at: str                   # ISO 格式时间戳
    completed_at: str
    duration_seconds: float           # 耗时（秒）
    files: List[str] = field(default_factory=list)
    conflict_count: int = 0
    shard_count: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictRecord:
    """冲突发生记录"""
    task_a_id: str
    task_b_id: str
    conflict_type: str
    severity: str
    resolved: bool = True
    resolution_strategy: str = ""     # "serial" | "retry" | "manual"
    timestamp: str = ""


@dataclass
class AggregatedMetrics:
    """聚合后的指标快照"""
    period_start: str
    period_end: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    task_success_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    median_duration_seconds: float = 0.0
    p95_duration_seconds: float = 0.0
    parallel_efficiency: float = 0.0
    conflict_rate: float = 0.0
    total_conflicts: int = 0
    strategy_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class EvolutionReport:
    """进化分析报告"""
    period_days: int
    period_start: str
    period_end: str
    aggregated: AggregatedMetrics
    trend: str                        # "improving" | "stable" | "degrading"
    recommendations: List[str] = field(default_factory=list)
    strategy_scores: Dict[str, float] = field(default_factory=dict)


# 常量
DEFAULT_METRICS_DIR = ".engine"
METRICS_FILE = "metrics.json"
RETENTION_DAYS = 90


# 延迟导入避免循环
def create_metrics(metrics_dir: Optional[str] = None):
    """创建 EvolutionMetrics 实例"""
    from .collector import EvolutionMetrics
    return EvolutionMetrics(metrics_dir=metrics_dir)


__all__ = [
    "TaskRecord",
    "ConflictRecord",
    "AggregatedMetrics",
    "EvolutionReport",
    "create_metrics",
    "DEFAULT_METRICS_DIR",
    "METRICS_FILE",
    "RETENTION_DAYS",
]

"""Self-Evolution Metrics — Phase 4 自进化指标模块

跟踪引擎性能，学习历史数据，推荐最优策略。
Phase 4 of Autonomous Parallel Fix Mesh.

功能:
- EvolutionMetrics: 追踪引擎运行指标
- analyze_history: 按时间窗口聚合分析
- recommend_strategy: 基于历史数据推荐调度策略
- adjust_sharding: 从冲突历史学习改进分片
- weekly_report: 近7天性能摘要
- 90天自动清理旧数据
"""

from .metrics import (
    TaskRecord, ConflictRecord, AggregatedMetrics, EvolutionReport,
    create_metrics, RETENTION_DAYS,
)
from .collector import EvolutionMetrics
from .reporter import weekly_report

__all__ = [
    "EvolutionMetrics",
    "TaskRecord",
    "ConflictRecord",
    "AggregatedMetrics",
    "EvolutionReport",
    "create_metrics",
    "RETENTION_DAYS",
]

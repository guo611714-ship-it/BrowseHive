"""Evolution Metrics — 周报与策略工具函数

weekly_report, recommend_strategy, adjust_sharding, save/load history
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import statistics

from .metrics import RETENTION_DAYS


def weekly_report(metrics: "EvolutionMetrics") -> Dict[str, Any]:
    """生成近7天的性能周报

    Args:
        metrics: EvolutionMetrics 实例

    Returns:
        周报字典，包含指标、趋势、建议
    """
    report = metrics.analyze_history(period_days=7)
    agg = report.aggregated
    daily_breakdown = metrics._daily_breakdown(days=7)

    return {
        "period": {
            "start": report.period_start,
            "end": report.period_end,
            "days": 7,
        },
        "summary": {
            "total_tasks": agg.total_tasks,
            "success_rate": round(agg.task_success_rate, 4),
            "avg_duration_seconds": round(agg.avg_duration_seconds, 2),
            "median_duration_seconds": round(agg.median_duration_seconds, 2),
            "p95_duration_seconds": round(agg.p95_duration_seconds, 2),
            "parallel_efficiency": round(agg.parallel_efficiency, 4),
            "conflict_rate": round(agg.conflict_rate, 4),
            "total_conflicts": agg.total_conflicts,
        },
        "strategy_scores": {
            k: round(v, 4) for k, v in report.strategy_scores.items()
        },
        "trend": report.trend,
        "daily_breakdown": daily_breakdown,
        "recommendations": report.recommendations,
        "retention_info": {
            "retention_days": RETENTION_DAYS,
            "total_records": len(metrics._history),
        },
    }


__all__ = ["weekly_report"]

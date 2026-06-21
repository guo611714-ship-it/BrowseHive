"""路由仪表盘 — 聚合命中率、平台健康、响应时间、质量趋势"""

import time
import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from collections import defaultdict

from .platform_router import (
    RouteResult, TaskRouter, get_router,
)

logger = logging.getLogger(__name__)

# ─── 路由仪表盘 ────────────────────────────────────────────────

@dataclass
class DashboardStats:
    """仪表盘统计数据"""
    total_routes: int
    l1_hits: int
    l2_hits: int
    l3_fallbacks: int
    platform_stats: Dict[str, Dict]
    circuit_breaker_status: Dict[str, Dict]
    timestamp: str


class RouterDashboard:
    """路由仪表盘：聚合L1/L2/L3命中率、平台响应时间、质量趋势、熔断状态"""

    def __init__(self, router: TaskRouter = None):
        self._router = router or get_router()
        self._lock = threading.Lock()
        self._total_routes: int = 0
        self._l1_hits: int = 0
        self._l2_hits: int = 0
        self._l3_fallbacks: int = 0
        # 每平台累计统计
        self._platform_route_count: Dict[str, int] = defaultdict(int)
        self._platform_success_count: Dict[str, int] = defaultdict(int)
        self._platform_latencies: Dict[str, List[float]] = defaultdict(list)

    def record_route(self, result: RouteResult):
        """每次路由调用时记录命中层级和平台"""
        with self._lock:
            self._total_routes += 1
            level = result.level
            if level == "L1":
                self._l1_hits += 1
            elif level == "L2":
                self._l2_hits += 1
            else:
                self._l3_fallbacks += 1
            for p in result.platforms:
                self._platform_route_count[p] += 1

    def record_latency(self, platform: str, latency_ms: float):
        """记录平台响应时间"""
        with self._lock:
            buf = self._platform_latencies[platform]
            buf.append(latency_ms)
            if len(buf) > 200:
                self._platform_latencies[platform] = buf[-200:]

    def record_platform_success(self, platform: str, success: bool):
        """记录平台调用成功/失败"""
        with self._lock:
            if success:
                self._platform_success_count[platform] += 1

    def get_summary(self) -> DashboardStats:
        """返回完整统计摘要"""
        # 锁内快照自身数据，锁外访问 feedback_store（避免嵌套锁）
        with self._lock:
            total = self._total_routes
            l1 = self._l1_hits
            l2 = self._l2_hits
            l3 = self._l3_fallbacks
            route_counts = dict(self._platform_route_count)
            success_counts = dict(self._platform_success_count)
            latencies_snapshot = {p: list(v[-50:]) for p, v in self._platform_latencies.items()}

        # 锁外访问 feedback_store
        fb_stats = self._router.feedback_store.get_stats()
        fb_platforms = fb_stats.get("platforms", {}).keys()

        platform_stats: Dict[str, Dict] = {}
        for p in set(list(route_counts.keys()) + list(fb_platforms)):
            route_cnt = route_counts.get(p, 0)
            succ_cnt = success_counts.get(p, 0)
            lats = latencies_snapshot.get(p, [])
            avg_latency = round(sum(lats) / len(lats), 1) if lats else 0
            avg_quality = self._router.feedback_store.get_platform_avg_quality(p)
            platform_stats[p] = {
                "route_count": route_cnt,
                "success_count": succ_cnt,
                "success_rate": round(succ_cnt / max(route_cnt, 1), 3),
                "avg_latency_ms": avg_latency,
                "avg_quality": round(avg_quality, 3),
            }

        cb_status = self._router.circuit_breaker.get_status()

        return DashboardStats(
            total_routes=total,
            l1_hits=l1,
            l2_hits=l2,
            l3_fallbacks=l3,
            platform_stats=platform_stats,
            circuit_breaker_status=cb_status,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    def get_route_distribution(self) -> Dict[str, float]:
        """返回命中率分布 (L1/L2/L3 百分比)"""
        with self._lock:
            total = self._total_routes
            if total == 0:
                return {"L1": 0.0, "L2": 0.0, "L3": 0.0}
            return {
                "L1": round(self._l1_hits / total, 4),
                "L2": round(self._l2_hits / total, 4),
                "L3": round(self._l3_fallbacks / total, 4),
            }

    def get_platform_health(self) -> Dict[str, Dict]:
        """返回平台健康状态（综合熔断+成功率+响应时间+质量）"""
        # 锁内快照，避免数据竞争
        with self._lock:
            route_counts = dict(self._platform_route_count)
            success_counts = dict(self._platform_success_count)
            latencies_snapshot = {p: list(v[-50:]) for p, v in self._platform_latencies.items()}

        cb_status = self._router.circuit_breaker.get_status()
        health: Dict[str, Dict] = {}
        for p, cb in cb_status.items():
            route_cnt = route_counts.get(p, 0)
            succ_cnt = success_counts.get(p, 0)
            lats = latencies_snapshot.get(p, [])
            avg_latency = round(sum(lats) / len(lats), 1) if lats else 0
            quality = self._router.feedback_store.get_platform_avg_quality(p)

            # 综合健康评分 0-1
            score = 1.0
            if cb.get("circuit_open"):
                score *= 0.2
            success_rate = succ_cnt / max(route_cnt, 1)
            score *= (0.3 + 0.7 * success_rate)
            if avg_latency > 0:
                latency_factor = max(0.0, 1.0 - (avg_latency - 200) / 1800)
                score *= max(latency_factor, 0.1)
            score *= (0.5 + 0.5 * quality)

            if score >= 0.8:
                status_label = "healthy"
            elif score >= 0.5:
                status_label = "degraded"
            else:
                status_label = "unhealthy"

            health[p] = {
                "status": status_label,
                "score": round(score, 3),
                "circuit_open": cb.get("circuit_open", False),
                "success_rate": round(success_rate, 3),
                "avg_latency_ms": avg_latency,
                "avg_quality": round(quality, 3),
            }
        return health


# ─── 全局仪表盘（线程安全单例）───────────────────────────────────

_dashboard: Optional[RouterDashboard] = None
_dashboard_lock = threading.Lock()


def get_dashboard() -> RouterDashboard:
    """获取全局路由仪表盘实例"""
    global _dashboard
    if _dashboard is not None:
        return _dashboard
    with _dashboard_lock:
        if _dashboard is not None:
            return _dashboard
        _dashboard = RouterDashboard()
        return _dashboard

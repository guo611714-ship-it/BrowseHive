"""AB 测试框架 — 对比新旧路由策略效果"""

import json
import time
import random
import logging
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any
from collections import defaultdict

from .platform_router import (
    RouteResult, TaskRouter, l1_route, _l3_fallback, get_router,
)

logger = logging.getLogger(__name__)

# ─── AB 测试框架 ───────────────────────────────────────────────

AB_TEST_PERSIST_PATH = Path(".team/ab_test.json")


@dataclass
class ABTestResult:
    """单次 AB 测试路由结果"""
    strategy: str   # "control" | "treatment"
    platform: str
    category: str
    latency_ms: float
    quality: float
    timestamp: str


class ABTestFramework:
    """AB 测试框架 — 对比新旧路由策略的效果

    control (旧策略): L1 -> L3  直接跳过 L2
    treatment (新策略): L1 -> L2 -> L3  完整三级漏斗

    线程安全，结果持久化到 .team/ab_test.json
    """

    def __init__(self, control_ratio: float = 0.5, persist_path: Optional[Path] = None):
        self._control_ratio = control_ratio
        self._persist_path = persist_path or AB_TEST_PERSIST_PATH
        self._lock = threading.Lock()
        self._results: List[ABTestResult] = []
        self._load()

    # ── 持久化 ──────────────────────────────────────────────────

    def _load(self) -> None:
        """从磁盘加载历史结果"""
        if self._persist_path.exists():
            try:
                raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
                self._results = [ABTestResult(**r) for r in raw.get("results", [])]
                saved_ratio = raw.get("control_ratio")
                if saved_ratio is not None:
                    self._control_ratio = float(saved_ratio)
            except Exception as e:
                logger.debug("AB test data corrupt: %s", e)
                logger.warning("AB test data corrupt, starting fresh")

    def _save(self) -> None:
        """将结果持久化到磁盘"""
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "control_ratio": self._control_ratio,
            "results": [asdict(r) for r in self._results],
        }
        self._persist_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 分组 ────────────────────────────────────────────────────

    def assign_group(self) -> str:
        """随机分配到 control 或 treatment 组"""
        return "control" if random.random() < self._control_ratio else "treatment"

    # ── 路由执行 ────────────────────────────────────────────────

    def route(self, query: str, category: str = "general") -> ABTestResult:
        """执行一次路由，自动分组并记录结果

        control: 直接 L1 -> _l3_fallback (跳过 L2)
        treatment: 完整 L1 -> L2 -> L3 (via TaskRouter.route)
        """
        strategy = self.assign_group()
        router = get_router()
        start = time.time()

        if strategy == "control":
            # 旧策略: L1 -> L3 (跳过 L2)
            l1_result = l1_route(query)
            if l1_result:
                result = l1_result
            else:
                result = _l3_fallback(query)
        else:
            # 新策略: L1 -> L2 -> L3
            result = router.route(query)

        latency_ms = (time.time() - start) * 1000
        quality = result.confidence if result else 0.0
        platform = result.platforms[0] if (result and result.platforms) else "unknown"

        ab_result = ABTestResult(
            strategy=strategy,
            platform=platform,
            category=category,
            latency_ms=round(latency_ms, 2),
            quality=round(quality, 4),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        with self._lock:
            self._results.append(ab_result)
        self._save()  # 锁外执行磁盘I/O

        return ab_result

    # ── 结果查询 ────────────────────────────────────────────────

    def get_results(self) -> Dict[str, Any]:
        """返回 control / treatment 的对比统计"""
        with self._lock:
            groups: Dict[str, List[ABTestResult]] = defaultdict(list)
            for r in self._results:
                groups[r.strategy].append(r)

        summary: Dict[str, Any] = {}

        for group_name in ("control", "treatment"):
            items = groups.get(group_name, [])
            if not items:
                summary[group_name] = {
                    "count": 0,
                    "avg_latency": 0.0,
                    "avg_quality": 0.0,
                    "platforms": {},
                }
                continue

            count = len(items)
            avg_latency = sum(r.latency_ms for r in items) / count
            avg_quality = sum(r.quality for r in items) / count
            platforms: Dict[str, int] = defaultdict(int)
            for r in items:
                platforms[r.platform] += 1

            summary[group_name] = {
                "count": count,
                "avg_latency": round(avg_latency, 2),
                "avg_quality": round(avg_quality, 4),
                "platforms": dict(platforms),
            }

        summary["winner"] = self.get_winner()
        return summary

    def get_winner(self) -> str:
        """返回当前表现更好的策略名称

        评判标准: 质量分更高 且 延迟更低 (加权综合分)
        每组至少 5 条数据才判定，否则返回 insufficient_data
        """
        with self._lock:
            groups: Dict[str, List[ABTestResult]] = defaultdict(list)
            for r in self._results:
                groups[r.strategy].append(r)

        control = groups.get("control", [])
        treatment = groups.get("treatment", [])

        if len(control) < 5 or len(treatment) < 5:
            return "insufficient_data"

        def _score(items: List[ABTestResult]) -> float:
            n = len(items)
            avg_q = sum(r.quality for r in items) / n
            avg_lat = sum(r.latency_ms for r in items) / n
            # 质量权重 0.7, 延迟权重 0.3 (归一化, 延迟越低越好)
            latency_score = max(0.0, 1.0 - avg_lat / 5000)
            return avg_q * 0.7 + latency_score * 0.3

        ctrl_score = _score(control)
        treat_score = _score(treatment)

        if abs(ctrl_score - treat_score) < 0.01:
            return "insufficient_data"
        return "control" if ctrl_score > treat_score else "treatment"

    # ── 配置 ────────────────────────────────────────────────────

    def set_control_ratio(self, ratio: float) -> None:
        """设置 control 组流量比例 (0.0 ~ 1.0)"""
        if not 0.0 <= ratio <= 1.0:
            raise ValueError(f"control_ratio must be in [0.0, 1.0], got {ratio}")
        with self._lock:
            self._control_ratio = ratio
            self._save()

    def reset(self) -> None:
        """清空所有结果"""
        with self._lock:
            self._results.clear()
        self._save()  # 锁外执行磁盘I/O


# ─── 全局 AB 测试实例 ──────────────────────────────────────────

_ab_test: Optional[ABTestFramework] = None
_ab_test_lock = threading.Lock()


def get_ab_test(control_ratio: float = 0.5) -> ABTestFramework:
    """获取全局 AB 测试框架实例"""
    global _ab_test
    if _ab_test is not None:
        # 更新 control_ratio（如果不同）
        if abs(_ab_test._control_ratio - control_ratio) > 0.001:
            _ab_test.set_control_ratio(control_ratio)
        return _ab_test
    with _ab_test_lock:
        if _ab_test is not None:
            if abs(_ab_test._control_ratio - control_ratio) > 0.001:
                _ab_test.set_control_ratio(control_ratio)
            return _ab_test
        _ab_test = ABTestFramework(control_ratio=control_ratio)
        return _ab_test


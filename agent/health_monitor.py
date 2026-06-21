"""agent/health_monitor.py - Model health tracking (extracted from ModelOrchestrator)

Handles health scoring, persistence, and healthy-model ranking.
Decoupled from ModelOrchestrator for testability and single responsibility.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Model health tracking with persistence and automatic recovery."""

    # Model stability ranking (lower = more stable)
    STABILITY_RANK = {
        "nvidia-mistral-nemotron": 1,
        "nvidia-step-3.5-flash": 2,
        "nvidia-step-3.7-flash": 3,
        "nvidia-llama-maverick": 4,
        "nvidia-minimax-m2.7": 5,
        "nvidia-qwen3-coder": 6,
        "nvidia-mistral-large-3": 7,
        "nvidia-glm-5.1": 8,
        "nvidia-gemma-e2b": 9,
        "nvidia-gemma-e4b": 10,
    }

    def __init__(self, health_json_path: Path = Path(".team/health.json")):
        self._health_status: Dict[str, bool] = {}
        self._health_scores: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._json_path = health_json_path
        self._load()

    def is_healthy(self, model_name: str) -> bool:
        """Check if a model is healthy (defaults to True)."""
        return self._health_status.get(model_name, True)

    def record_result(self, model_name: str, success: bool, latency_ms: int = 0):
        """Record a model call result and update health scores."""
        with self._lock:
            if model_name not in self._health_scores:
                self._health_scores[model_name] = {
                    "success": 0, "fail": 0, "total": 0,
                    "avg_latency": 0, "last_fail_time": 0,
                    "consecutive_fail": 0, "consecutive_success": 0,
                }
            scores = self._health_scores[model_name]
            scores["total"] += 1

            if success:
                scores["success"] += 1
                scores["consecutive_success"] = scores.get("consecutive_success", 0) + 1
                scores["consecutive_fail"] = 0
                if scores["consecutive_success"] >= 3:
                    self._health_status[model_name] = True
            else:
                scores["fail"] += 1
                scores["last_fail_time"] = time.time()
                scores["consecutive_fail"] = scores.get("consecutive_fail", 0) + 1
                scores["consecutive_success"] = 0
                if scores["consecutive_fail"] >= 2:
                    self._health_status[model_name] = False
                    logger.warning(
                        f"模型 {model_name} 连续失败{scores['consecutive_fail']}次，标记为不健康"
                    )

            if latency_ms > 0:
                old_avg = scores["avg_latency"]
                n = scores["total"]
                scores["avg_latency"] = int((old_avg * (n - 1) + latency_ms) / n)

            self._save()

    def mark_unhealthy(self, model_name: str):
        with self._lock:
            self._health_status[model_name] = False
        logger.warning(f"模型 {model_name} 标记为不健康")

    def mark_healthy(self, model_name: str):
        with self._lock:
            self._health_status[model_name] = True

    def get_healthy_models(self) -> List[str]:
        """Get healthy models sorted by success rate + stability."""
        all_models = list(self.STABILITY_RANK.keys())
        healthy = [m for m in all_models if self._health_status.get(m, True)]

        def _sort_key(model_name: str):
            scores = self._health_scores.get(model_name, {})
            total = scores.get("total", 0)
            success_rate = scores.get("success", 0) / max(total, 1)
            stability = self.STABILITY_RANK.get(model_name, 99)
            if total > 0:
                return (-success_rate, stability)
            return (1, stability)

        return sorted(healthy, key=_sort_key)

    def get_report(self) -> Dict[str, Any]:
        """Get health report for all models."""
        report = {}
        for model_name in self.STABILITY_RANK:
            scores = self._health_scores.get(model_name, {})
            healthy = self._health_status.get(model_name, True)
            report[model_name] = {
                "healthy": healthy,
                "success": scores.get("success", 0),
                "fail": scores.get("fail", 0),
                "total": scores.get("total", 0),
                "success_rate": round(
                    scores.get("success", 0) / max(scores.get("total", 1), 1), 2
                ),
                "avg_latency_ms": scores.get("avg_latency", 0),
                "stability_rank": self.STABILITY_RANK.get(model_name, 99),
            }
        return report

    def get_trend_report(self) -> Dict[str, Any]:
        """Predictive analysis: detect degrading models before they fail.

        Returns models with negative trends (increasing failure rate,
        rising latency, or consecutive failures approaching threshold).
        """
        trends = {}
        for model_name in self.STABILITY_RANK:
            scores = self._health_scores.get(model_name, {})
            total = scores.get("total", 0)
            if total < 5:
                continue  # Not enough data

            consec_fail = scores.get("consecutive_fail", 0)
            fail = scores.get("fail", 0)
            success = scores.get("success", 0)
            fail_rate = fail / max(total, 1)
            avg_latency = scores.get("avg_latency", 0)

            warnings = []

            # Trend 1: Consecutive failures approaching threshold (2)
            if consec_fail >= 1:
                warnings.append(f"consecutive_fail={consec_fail} (threshold=2)")

            # Trend 2: High failure rate (>30%)
            if fail_rate > 0.3 and total >= 10:
                warnings.append(f"fail_rate={fail_rate:.0%}")

            # Trend 3: Rising latency (above 90s for fast models, 180s for slow)
            speed_tier = self.STABILITY_RANK.get(model_name, 5)
            latency_threshold = 90000 if speed_tier <= 4 else 180000
            if avg_latency > latency_threshold:
                warnings.append(f"avg_latency={avg_latency}ms (threshold={latency_threshold}ms)")

            # Trend 4: Declining success rate in recent calls
            # (if consecutive_success is 0 after many calls, recent calls are failing)
            consec_success = scores.get("consecutive_success", 0)
            if total >= 10 and consec_success == 0 and fail > success:
                warnings.append("declining_trend")

            if warnings:
                trends[model_name] = {
                    "healthy": self._health_status.get(model_name, True),
                    "warnings": warnings,
                    "fail_rate": round(fail_rate, 2),
                    "consecutive_fail": consec_fail,
                    "avg_latency_ms": avg_latency,
                }

        return {
            "degrading_models": trends,
            "total_models": len(self.STABILITY_RANK),
            "models_with_warnings": len(trends),
        }

    def _save(self):
        try:
            self._json_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "health_status": self._health_status,
                "health_scores": {
                    model: {k: v for k, v in scores.items() if k != "last_fail_time"}
                    for model, scores in self._health_scores.items()
                },
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            with open(self._json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"保存健康状态失败（非致命）: {e}")

    def _load(self):
        try:
            if not self._json_path.exists():
                return
            with open(self._json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for model, healthy in data.get("health_status", {}).items():
                if isinstance(healthy, bool):
                    self._health_status[model] = healthy
            for model, scores in data.get("health_scores", {}).items():
                if isinstance(scores, dict):
                    scores.setdefault("last_fail_time", 0)
                    scores.setdefault("consecutive_fail", 0)
                    scores.setdefault("consecutive_success", 0)
                    self._health_scores[model] = scores
            logger.info(f"从 {self._json_path} 恢复 {len(self._health_status)} 个模型健康状态")
        except Exception as e:
            logger.debug(f"加载健康状态失败（非致命）: {e}")

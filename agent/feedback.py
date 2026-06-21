import logging
"""学习反馈闭环 — 自动收集任务执行数据，优化模型路由策略"""

import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict


@dataclass
class TaskFeedback:
    """单次任务反馈"""
    task_id: str
    model: str
    complexity: int  # 1-5
    scenario: str
    success: bool
    duration_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""
    timestamp: float = field(default_factory=time.time)


class FeedbackLoop:
    """反馈数据收集、分析和路由策略更新"""

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path(".team/feedback")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._feedback_file = self.data_dir / "feedback.jsonl"
        self._lock = threading.Lock()
        self._cache: List[Dict] = []
        self._load_cache()

    def _load_cache(self):
        """加载历史反馈到内存缓存"""
        if self._feedback_file.exists():
            try:
                with open(self._feedback_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            self._cache.append(json.loads(line.strip()))
            except Exception as e:
                logger.debug("反馈操作失败: %s", e)

    def record(self, feedback: TaskFeedback):
        """记录一次任务反馈"""
        with self._lock:
            entry = asdict(feedback)
            self._cache.append(entry)
            # 追加写入文件
            try:
                with open(self._feedback_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.debug("反馈操作失败: %s", e)

    def get_model_stats(self, model: str, days: int = 7) -> Dict[str, Any]:
        """获取指定模型的统计数据"""
        cutoff = time.time() - days * 86400
        relevant = [f for f in self._cache
                    if f["model"] == model and f["timestamp"] > cutoff]

        if not relevant:
            return {"model": model, "total": 0, "success_rate": 0, "avg_duration_ms": 0}

        total = len(relevant)
        successes = sum(1 for f in relevant if f["success"])
        avg_duration = sum(f["duration_ms"] for f in relevant) / total

        return {
            "model": model,
            "total": total,
            "success_rate": round(successes / total, 3),
            "avg_duration_ms": round(avg_duration, 1),
            "avg_input_tokens": round(sum(f["input_tokens"] for f in relevant) / total),
            "avg_output_tokens": round(sum(f["output_tokens"] for f in relevant) / total),
        }

    def get_scenario_stats(self, scenario: str, days: int = 7) -> Dict[str, Any]:
        """获取指定场景的统计数据"""
        cutoff = time.time() - days * 86400
        relevant = [f for f in self._cache
                    if f["scenario"] == scenario and f["timestamp"] > cutoff]

        if not relevant:
            return {"scenario": scenario, "total": 0, "best_model": None}

        # 按模型分组统计
        by_model: Dict[str, List] = {}
        for f in relevant:
            by_model.setdefault(f["model"], []).append(f)

        # 计算每个模型的综合得分（成功率×0.7 + 速度得分×0.3）
        scores = {}
        for model, feedbacks in by_model.items():
            success_rate = sum(1 for f in feedbacks if f["success"]) / len(feedbacks)
            avg_duration = sum(f["duration_ms"] for f in feedbacks) / len(feedbacks)
            speed_score = max(0, 1 - avg_duration / 30000)  # 30秒为基准
            scores[model] = round(success_rate * 0.7 + speed_score * 0.3, 3)

        best_model = max(scores, key=scores.get) if scores else None

        return {
            "scenario": scenario,
            "total": len(relevant),
            "best_model": best_model,
            "model_scores": scores,
        }

    def suggest_model(self, scenario: str, complexity: int) -> Optional[str]:
        """根据历史数据推荐最优模型"""
        # 查场景统计
        scenario_stats = self.get_scenario_stats(scenario)
        if scenario_stats["best_model"]:
            return scenario_stats["best_model"]

        # 无场景数据时，按复杂度推荐
        complexity_models = {
            1: "nvidia-gemma-e2b",
            2: "nvidia-step-3.7-flash",
            3: "nvidia-minimax-m2.7",
            4: "nvidia-mistral-large-3",
            5: "nvidia-glm-5.1",
        }
        return complexity_models.get(complexity, "nvidia-step-3.7-flash")

    def get_all_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取全局统计"""
        cutoff = time.time() - days * 86400
        recent = [f for f in self._cache if f["timestamp"] > cutoff]

        if not recent:
            return {"total": 0, "success_rate": 0}

        total = len(recent)
        successes = sum(1 for f in recent if f["success"])

        # 按模型统计
        models = set(f["model"] for f in recent)
        by_model = {m: self.get_model_stats(m, days) for m in models}

        return {
            "total": total,
            "success_rate": round(successes / total, 3),
            "by_model": by_model,
            "period_days": days,
        }

    def cleanup_old(self, retention_days: int = 90):
        """清理旧反馈数据"""
        cutoff = time.time() - retention_days * 86400
        with self._lock:
            self._cache = [f for f in self._cache if f["timestamp"] > cutoff]
            # 重写文件
            try:
                with open(self._feedback_file, "w", encoding="utf-8") as f:
                    for entry in self._cache:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.debug("反馈操作失败: %s", e)


# 全局实例
_feedback_loop: Optional[FeedbackLoop] = None


def get_feedback_loop() -> FeedbackLoop:
    global _feedback_loop
    if _feedback_loop is None:
        _feedback_loop = FeedbackLoop()
    return _feedback_loop

"""Conflict Predictor -- rule-based + ML-enhanced conflict prediction + evolution metrics

Merged from conflict.py, ml_predictor.py, and collector.py.

Modules:
- ConflictPredictor: rule-based conflict prediction (Phase 1)
- MLConflictPredictor: ML-enhanced conflict prediction with online learning (Phase 4)
- EvolutionMetrics: engine self-evolution metrics tracking (Phase 4)
"""

import hashlib
import json
import logging
import math
import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .manifest import TaskManifest, SchedulingStrategy

logger = logging.getLogger(__name__)


# ============================================================
# Part 1: Rule-Based Conflict Prediction (was conflict.py)
# ============================================================

@dataclass
class ConflictPrediction:
    """冲突预测结果"""
    task_a_id: str
    task_b_id: str
    conflict_type: str   # "file_overlap" | "import_cycle" | "dependency_chain"
    severity: str        # "high" | "medium" | "low"
    reason: str
    confidence: float    # 0.0 ~ 1.0


class ConflictPredictor:
    """规则驱动的冲突预测器

    规则优先级：
    1. 同文件同行号区间 -> high
    2. 同文件不同区间 -> medium（可能有隐式依赖）
    3. import 关系 -> low（通常安全但需注意）
    4. 跨文件无关系 -> 无冲突
    """

    def __init__(self):
        self._file_cache: Dict[str, str] = {}  # filepath -> content[:50000]

    def predict_conflicts(self, tasks: List) -> List[List]:
        """预测任务间冲突，返回分组后的任务列表"""
        if len(tasks) <= 1:
            return [tasks]

        n = len(tasks)
        conflict_matrix = [[0] * n for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                prediction = self._predict_pair(tasks[i], tasks[j])
                if prediction:
                    score = self._severity_to_score(prediction.severity)
                    conflict_matrix[i][j] = score
                    conflict_matrix[j][i] = score

        return self._greedy_group(tasks, conflict_matrix)

    def _predict_pair(self, task_a, task_b) -> Optional[ConflictPrediction]:
        """预测两个任务间的冲突"""
        files_a = set(task_a.files)
        files_b = set(task_b.files)

        if files_a == files_b:
            return ConflictPrediction(
                task_a_id=task_a.task_id,
                task_b_id=task_b.task_id,
                conflict_type="file_overlap",
                severity="high",
                reason=f"identical file sets: {files_a}",
                confidence=0.95
            )

        overlap = files_a & files_b
        if overlap:
            return ConflictPrediction(
                task_a_id=task_a.task_id,
                task_b_id=task_b.task_id,
                conflict_type="file_overlap",
                severity="medium",
                reason=f"overlapping files: {overlap}",
                confidence=0.7
            )

        import_conflict = self._check_import_dependency(task_a, task_b)
        if import_conflict:
            return import_conflict

        return None

    def _check_import_dependency(self, task_a, task_b) -> Optional[ConflictPrediction]:
        """检查两个任务的文件间是否有 import 关系"""
        for f_a in task_a.files:
            for f_b in task_b.files:
                if self._files_import_each_other(f_a, f_b):
                    return ConflictPrediction(
                        task_a_id=task_a.task_id,
                        task_b_id=task_b.task_id,
                        conflict_type="import_cycle",
                        severity="low",
                        reason=f"import relationship: {f_a} <-> {f_b}",
                        confidence=0.4
                    )
        return None

    def _files_import_each_other(self, file_a: str, file_b: str) -> bool:
        """检查两个 Python 文件是否有 import 关系"""
        try:
            path_a = Path(file_a)
            path_b = Path(file_b)

            if not path_a.exists() or not path_b.exists():
                return False

            if file_a not in self._file_cache:
                self._file_cache[file_a] = path_a.read_text(
                    encoding="utf-8", errors="ignore")[:50000]
            if file_b not in self._file_cache:
                self._file_cache[file_b] = path_b.read_text(
                    encoding="utf-8", errors="ignore")[:50000]

            content_a = self._file_cache[file_a]
            content_b = self._file_cache[file_b]

            name_a = path_a.stem
            name_b = path_b.stem

            a_imports_b = f"import {name_b}" in content_a or f"from {name_b}" in content_a
            b_imports_a = f"import {name_a}" in content_b or f"from {name_a}" in content_b

            return a_imports_b or b_imports_a
        except Exception as e:
            logger.debug("Import analysis failed: %s", e)
            return False

    def _severity_to_score(self, severity: str) -> int:
        return {"high": 3, "medium": 2, "low": 1}.get(severity, 0)

    def _greedy_group(self, tasks: List, conflict_matrix: List[List[int]]) -> List[List]:
        """贪心分组：冲突分数高的优先分到不同组"""
        n = len(tasks)
        groups: List[List[int]] = []
        task_groups = [-1] * n

        for i in range(n):
            if task_groups[i] != -1:
                continue

            group_idx = len(groups)
            group = [i]
            task_groups[i] = group_idx

            for j in range(i + 1, n):
                if task_groups[j] != -1:
                    continue
                max_conflict = max(
                    conflict_matrix[j][k] for k in group
                ) if group else 0
                if max_conflict == 0:
                    group.append(j)
                    task_groups[j] = group_idx

            groups.append([tasks[idx] for idx in group])

        return groups

    def analyze_manifest(self, manifest) -> Dict:
        """分析整个 manifest 的冲突概况"""
        tasks = manifest.tasks
        predictions = []

        for i in range(len(tasks)):
            for j in range(i + 1, len(tasks)):
                pred = self._predict_pair(tasks[i], tasks[j])
                if pred:
                    predictions.append(pred)

        return {
            "total_tasks": len(tasks),
            "total_conflicts": len(predictions),
            "by_severity": {
                "high": sum(1 for p in predictions if p.severity == "high"),
                "medium": sum(1 for p in predictions if p.severity == "medium"),
                "low": sum(1 for p in predictions if p.severity == "low"),
            },
            "predictions": [
                {
                    "tasks": [p.task_a_id, p.task_b_id],
                    "type": p.conflict_type,
                    "severity": p.severity,
                    "reason": p.reason,
                }
                for p in predictions
            ],
            "estimated_parallel_ratio": self._estimate_parallel_ratio(predictions, len(tasks)),
        }

    def _estimate_parallel_ratio(self, predictions: List[ConflictPrediction],
                                  total_tasks: int) -> float:
        """估算可并行比例"""
        if total_tasks <= 1:
            return 1.0
        high_conflict_tasks = set()
        for p in predictions:
            if p.severity == "high":
                high_conflict_tasks.add(p.task_a_id)
                high_conflict_tasks.add(p.task_b_id)
        serial_count = len(high_conflict_tasks)
        return max(0, (total_tasks - serial_count) / total_tasks)


# ============================================================
# Part 2: ML-Enhanced Conflict Predictor (was ml_predictor.py)
# ============================================================

@dataclass
class MLConflictRecord:
    """冲突记录 -- 用于 ML 训练的历史数据"""
    task_a_files: List[str]
    task_b_files: List[str]
    actual_conflict: bool
    conflict_type: str       # "file_overlap" | "import_cycle" | "dependency_chain" | "none"
    resolution: str          # "merged" | "serial" | "manual"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ConflictFeatures:
    """从任务对提取的特征向量"""
    file_overlap_ratio: float
    same_directory: float
    import_dependency: float
    file_size_ratio: float
    historical_conflict_rate: float

    def to_list(self) -> List[float]:
        return [
            self.file_overlap_ratio,
            self.same_directory,
            self.import_dependency,
            self.file_size_ratio,
            self.historical_conflict_rate,
        ]

    @staticmethod
    def feature_names() -> List[str]:
        return [
            "file_overlap_ratio",
            "same_directory",
            "import_dependency",
            "file_size_ratio",
            "historical_conflict_rate",
        ]


@dataclass
class ConflictPredictionResult:
    """ML 冲突预测结果"""
    task_a_id: str
    task_b_id: str
    conflict_prob: float
    confidence: float
    features: ConflictFeatures
    method: str                # "ml" | "rule" | "hybrid"
    rule_prediction: Optional[ConflictPrediction] = None


@dataclass
class MLModel:
    """简单线性模型参数"""
    weights: List[float] = field(default_factory=lambda: [0.0] * 5)
    bias: float = 0.0
    learning_rate: float = 0.01
    update_count: int = 0
    feature_means: List[float] = field(default_factory=lambda: [0.0] * 5)
    feature_vars: List[float] = field(default_factory=lambda: [1.0] * 5)
    total_samples: int = 0


class FeatureExtractor:
    """从任务文件列表提取特征 (纯规则，无外部依赖)"""

    def __init__(self):
        self._pattern_stats: Dict[str, Tuple[int, int]] = {}
        self._size_cache: Dict[str, int] = {}

    def extract(
        self,
        files_a: List[str],
        files_b: List[str],
        import_checker: Optional[Any] = None,
    ) -> ConflictFeatures:
        """提取特征向量"""
        set_a = set(files_a)
        set_b = set(files_b)

        union = set_a | set_b
        intersection = set_a & set_b
        overlap_ratio = len(intersection) / len(union) if union else 0.0

        same_dir = self._check_same_directory(set_a, set_b)
        import_dep = self._check_import_dependency(files_a, files_b, import_checker)
        size_ratio = self._compute_size_ratio(set_a, set_b)
        hist_rate = self._historical_conflict_rate(set_a, set_b)

        return ConflictFeatures(
            file_overlap_ratio=overlap_ratio,
            same_directory=same_dir,
            import_dependency=import_dep,
            file_size_ratio=size_ratio,
            historical_conflict_rate=hist_rate,
        )

    def _check_same_directory(self, set_a: Set[str], set_b: Set[str]) -> float:
        if not set_a or not set_b:
            return 0.0
        dirs_a = {Path(f).parent for f in set_a}
        dirs_b = {Path(f).parent for f in set_b}
        return 1.0 if (dirs_a & dirs_b) else 0.0

    def _check_import_dependency(
        self,
        files_a: List[str],
        files_b: List[str],
        import_checker: Optional[Any] = None,
    ) -> float:
        if import_checker is not None:
            try:
                for f_a in files_a:
                    for f_b in files_b:
                        if import_checker._files_import_each_other(f_a, f_b):
                            return 1.0
            except Exception as e:
                logger.debug("Import check failed: %s", e)

        try:
            for f_a in files_a:
                for f_b in files_b:
                    if self._simple_import_check(f_a, f_b):
                        return 1.0
        except Exception as e:
            logger.debug("Simple import check failed: %s", e)
        return 0.0

    def _simple_import_check(self, file_a: str, file_b: str) -> bool:
        try:
            path_a = Path(file_a)
            path_b = Path(file_b)
            if not path_a.exists() or not path_b.exists():
                return False
            if path_a.suffix != ".py" or path_b.suffix != ".py":
                return False
            name_a = path_a.stem
            name_b = path_b.stem
            content_a = path_a.read_text(encoding="utf-8", errors="ignore")[:50000]
            content_b = path_b.read_text(encoding="utf-8", errors="ignore")[:50000]
            a_imports_b = f"import {name_b}" in content_a or f"from {name_b}" in content_a
            b_imports_a = f"import {name_a}" in content_b or f"from {name_a}" in content_b
            return a_imports_b or b_imports_a
        except Exception as e:
            logger.debug("Simple import check failed: %s", e)
            return False

    def _compute_size_ratio(self, set_a: Set[str], set_b: Set[str]) -> float:
        size_a = self._total_size(set_a)
        size_b = self._total_size(set_b)
        total = size_a + size_b
        if total == 0:
            return 0.5
        return min(size_a, size_b) / max(size_a, size_b)

    def _total_size(self, files: Set[str]) -> int:
        total = 0
        for f in files:
            if f in self._size_cache:
                total += self._size_cache[f]
                continue
            try:
                size = Path(f).stat().st_size
                self._size_cache[f] = size
                total += size
            except (OSError, FileNotFoundError):
                self._size_cache[f] = 0
        return total

    def _historical_conflict_rate(
        self, set_a: Set[str], set_b: Set[str]
    ) -> float:
        pattern = self._make_pattern(set_a, set_b)
        if pattern in self._pattern_stats:
            conflicts, total = self._pattern_stats[pattern]
            return conflicts / total if total > 0 else 0.0
        for other_pattern, (conflicts, total) in self._pattern_stats.items():
            if self._pattern_overlap(pattern, other_pattern):
                return conflicts / total if total > 0 else 0.0
        return 0.0

    def update_pattern_stats(
        self, set_a: Set[str], set_b: Set[str], had_conflict: bool
    ):
        pattern = self._make_pattern(set_a, set_b)
        if pattern not in self._pattern_stats:
            self._pattern_stats[pattern] = (0, 0)
        conflicts, total = self._pattern_stats[pattern]
        new_conflicts = conflicts + (1 if had_conflict else 0)
        self._pattern_stats[pattern] = (new_conflicts, total + 1)

    def _make_pattern(self, set_a: Set[str], set_b: Set[str]) -> str:
        def _file_pattern(f: str) -> str:
            p = Path(f)
            return f"{p.parent}/{p.suffix}"
        patterns = sorted(
            [_file_pattern(f) for f in (set_a | set_b)]
        )
        return hashlib.md5(
            "|".join(patterns).encode()
        ).hexdigest()[:12]

    def _pattern_overlap(self, p1: str, p2: str) -> bool:
        return p1[:6] == p2[:6]


class LinearModel:
    """纯 Python 线性模型 + 在线梯度更新"""

    def __init__(self, n_features: int = 5, learning_rate: float = 0.01):
        self.model = MLModel(
            weights=[0.0] * n_features,
            bias=0.0,
            learning_rate=learning_rate,
        )
        self._n_features = n_features

    def predict(self, features: List[float]) -> float:
        assert len(features) == self._n_features, \
            f"特征维度不匹配: 期望 {self._n_features}, 实际 {len(features)}"
        normalized = self._normalize_readonly(features)
        logit = self.model.bias
        for i in range(self._n_features):
            logit += self.model.weights[i] * normalized[i]
        return self._sigmoid(logit)

    def update(self, features: List[float], actual: float, update_stats: bool = True):
        normalized = self._normalize(features, update_stats=update_stats)
        pred = self.predict(features)
        error = pred - actual
        for i in range(self._n_features):
            gradient = error * normalized[i]
            self.model.weights[i] -= self.model.learning_rate * gradient
        self.model.bias -= self.model.learning_rate * error
        self.model.update_count += 1

    def _normalize(self, features: List[float], update_stats: bool = True) -> List[float]:
        if update_stats:
            self.model.total_samples += 1
        result = []
        for i in range(self._n_features):
            val = features[i]
            if update_stats:
                n = self.model.total_samples
                old_mean = self.model.feature_means[i]
                new_mean = old_mean + (val - old_mean) / n
                self.model.feature_vars[i] = (
                    self.model.feature_vars[i] * (n - 1) / n
                    + (val - old_mean) * (val - new_mean) / n
                )
                self.model.feature_means[i] = new_mean
            else:
                new_mean = self.model.feature_means[i]
            std = math.sqrt(self.model.feature_vars[i]) + 1e-8
            result.append((val - new_mean) / std)
        return result

    def _normalize_readonly(self, features: List[float]) -> List[float]:
        result = []
        for i in range(self._n_features):
            val = features[i]
            mean = self.model.feature_means[i]
            std = math.sqrt(self.model.feature_vars[i]) + 1e-8
            result.append((val - mean) / std)
        return result

    @staticmethod
    def _sigmoid(x: float) -> float:
        if x >= 0:
            return 1.0 / (1.0 + math.exp(-x))
        else:
            exp_x = math.exp(x)
            return exp_x / (1.0 + exp_x)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weights": self.model.weights,
            "bias": self.model.bias,
            "learning_rate": self.model.learning_rate,
            "update_count": self.model.update_count,
            "feature_means": self.model.feature_means,
            "feature_vars": self.model.feature_vars,
            "total_samples": self.model.total_samples,
        }

    def load_dict(self, data: Dict[str, Any]):
        self.model.weights = data.get("weights", [0.0] * self._n_features)
        self.model.bias = data.get("bias", 0.0)
        self.model.learning_rate = data.get("learning_rate", 0.01)
        self.model.update_count = data.get("update_count", 0)
        self.model.feature_means = data.get(
            "feature_means", [0.0] * self._n_features
        )
        self.model.feature_vars = data.get(
            "feature_vars", [1.0] * self._n_features
        )
        self.model.total_samples = data.get("total_samples", 0)


class MLConflictPredictor:
    """ML 增强冲突预测器

    策略:
    - 历史记录 < 10: 使用规则引擎
    - 历史记录 >= 10: 使用 ML 模型，低置信度时回退到规则引擎
    - 支持在线增量更新
    - 模型持久化到 .engine/conflict_model.json
    """

    MIN_ML_SAMPLES = 10
    LOW_CONFIDENCE_THRESHOLD = 0.3

    def __init__(self, model_dir: Optional[str] = None, warmup_samples: int = 50):
        self.rule_predictor = ConflictPredictor()
        self.feature_extractor = FeatureExtractor()
        self.linear_model = LinearModel(n_features=5, learning_rate=0.01)
        self._history: List[MLConflictRecord] = []
        self._model_dir = model_dir or ".engine"
        self._model_path = Path(self._model_dir) / "conflict_model.json"
        self._warmup_samples = warmup_samples
        self._sample_count = 0

        self._load_model()

    def train(self, history: List[MLConflictRecord]):
        """用历史数据训练模型"""
        self._history = list(history)
        self._sample_count = len(self._history)
        self._rebuild_pattern_stats()

        if len(self._history) < self.MIN_ML_SAMPLES:
            return

        for epoch in range(min(10, len(self._history))):
            for record in self._history:
                features = self._extract_features_from_record(record)
                self.linear_model.update(
                    features.to_list(),
                    1.0 if record.actual_conflict else 0.0,
                    update_stats=(epoch == 0),
                )

    def predict(
        self,
        task_a: Any,
        task_b: Any,
    ) -> ConflictPredictionResult:
        """预测两个任务间的冲突"""
        files_a = set(task_a.files) if hasattr(task_a, "files") else set()
        files_b = set(task_b.files) if hasattr(task_b, "files") else set()

        features = self.feature_extractor.extract(
            list(files_a), list(files_b), self.rule_predictor
        )

        rule_pred = self.rule_predictor._predict_pair(task_a, task_b)

        if self._sample_count < max(self._warmup_samples, self.MIN_ML_SAMPLES):
            rule_prob = self._rule_to_prob(rule_pred)
            return ConflictPredictionResult(
                task_a_id=task_a.task_id,
                task_b_id=task_b.task_id,
                conflict_prob=rule_prob,
                confidence=0.5 if rule_pred else 0.1,
                features=features,
                method="rule",
                rule_prediction=rule_pred,
            )

        use_ml = len(self._history) >= self.MIN_ML_SAMPLES

        if use_ml:
            ml_prob = self.linear_model.predict(features.to_list())
            confidence = self._compute_confidence(ml_prob)

            if confidence >= self.LOW_CONFIDENCE_THRESHOLD:
                return ConflictPredictionResult(
                    task_a_id=task_a.task_id,
                    task_b_id=task_b.task_id,
                    conflict_prob=ml_prob,
                    confidence=confidence,
                    features=features,
                    method="ml",
                    rule_prediction=rule_pred,
                )
            else:
                return ConflictPredictionResult(
                    task_a_id=task_a.task_id,
                    task_b_id=task_b.task_id,
                    conflict_prob=ml_prob,
                    confidence=confidence,
                    features=features,
                    method="hybrid",
                    rule_prediction=rule_pred,
                )
        else:
            rule_prob = self._rule_to_prob(rule_pred)
            return ConflictPredictionResult(
                task_a_id=task_a.task_id,
                task_b_id=task_b.task_id,
                conflict_prob=rule_prob,
                confidence=0.5 if rule_pred else 0.1,
                features=features,
                method="rule",
                rule_prediction=rule_pred,
            )

    def online_update(self, record: MLConflictRecord):
        """增量更新模型"""
        self._history.append(record)
        self._sample_count = len(self._history)

        set_a = set(record.task_a_files)
        set_b = set(record.task_b_files)
        self.feature_extractor.update_pattern_stats(
            set_a, set_b, record.actual_conflict
        )

        if len(self._history) >= self.MIN_ML_SAMPLES:
            features = self._extract_features_from_record(record)
            self.linear_model.update(
                features.to_list(),
                1.0 if record.actual_conflict else 0.0,
            )

    def save(self):
        """保存模型到文件"""
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "model": self.linear_model.to_dict(),
            "pattern_stats": {
                k: list(v) for k, v in self.feature_extractor._pattern_stats.items()
            },
            "history_count": len(self._history),
            "history": [asdict(r) for r in self._history[-100:]],
        }
        self._model_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self):
        """从文件加载模型"""
        self._load_model()

    def _load_model(self):
        if not self._model_path.exists():
            return
        try:
            data = json.loads(
                self._model_path.read_text(encoding="utf-8")
            )
            self.linear_model.load_dict(data.get("model", {}))
            raw_stats = data.get("pattern_stats", {})
            self.feature_extractor._pattern_stats = {
                k: tuple(v) for k, v in raw_stats.items()
            }
            raw_history = data.get("history", [])
            self._history = [MLConflictRecord(**r) for r in raw_history]
            self._sample_count = len(self._history)
        except Exception as e:
            logger.debug("Model load failed, starting fresh: %s", e)

    def _rebuild_pattern_stats(self):
        self.feature_extractor._pattern_stats.clear()
        for record in self._history:
            set_a = set(record.task_a_files)
            set_b = set(record.task_b_files)
            self.feature_extractor.update_pattern_stats(
                set_a, set_b, record.actual_conflict
            )

    def _extract_features_from_record(
        self, record: MLConflictRecord
    ) -> ConflictFeatures:
        return self.feature_extractor.extract(
            record.task_a_files,
            record.task_b_files,
            self.rule_predictor,
        )

    def _compute_confidence(self, prob: float) -> float:
        sample_factor = min(1.0, len(self._history) / 50)
        distance_factor = abs(prob - 0.5) * 2
        return sample_factor * 0.6 + distance_factor * 0.4

    @staticmethod
    def _rule_to_prob(rule_pred: Optional[ConflictPrediction]) -> float:
        if rule_pred is None:
            return 0.0
        severity_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        return severity_map.get(rule_pred.severity, 0.1)

    @property
    def history_size(self) -> int:
        return len(self._history)

    @property
    def model_update_count(self) -> int:
        return self.linear_model.model.update_count

    @property
    def uses_ml(self) -> bool:
        return len(self._history) >= self.MIN_ML_SAMPLES


# ============================================================
# Part 3: Evolution Metrics (was collector.py)
# ============================================================

# Import data classes from metrics module (avoids circular import)
from .metrics import (
    TaskRecord,
    ConflictRecord,
    AggregatedMetrics,
    EvolutionReport,
    DEFAULT_METRICS_DIR,
    METRICS_FILE,
    RETENTION_DAYS,
)


class EvolutionMetrics:
    """自进化指标管理器

    追踪引擎每次执行的指标，支持:
    - 追加写入历史记录（append-only）
    - 按时间窗口聚合分析
    - 基于历史推荐最优策略
    - 自动清理过期数据（90天）
    """

    def __init__(self, metrics_dir: Optional[str] = None):
        self.metrics_dir = Path(metrics_dir or DEFAULT_METRICS_DIR)
        self.metrics_file = self.metrics_dir / METRICS_FILE
        self._history: List[Dict[str, Any]] = []
        self._load_history()

    def _load_history(self) -> None:
        if not self.metrics_file.exists():
            self._history = []
            return
        try:
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._history = data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("指标文件损坏，使用空历史: %s", e)
            self._history = []

    def _save_history(self) -> None:
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = self.metrics_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
            tmp_file.replace(self.metrics_file)
        except IOError as e:
            logger.error("保存指标失败: %s", e)

    def _cleanup_old_entries(self) -> int:
        if not self._history:
            return 0
        cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
        cutoff_iso = cutoff.isoformat()
        original_count = len(self._history)
        self._history = [
            entry for entry in self._history
            if entry.get("timestamp", "") >= cutoff_iso
        ]
        cleaned = original_count - len(self._history)
        if cleaned > 0:
            logger.info("清理了 %d 条过期指标记录", cleaned)
            self._save_history()
        return cleaned

    def record_task(self, record: TaskRecord) -> None:
        entry = {
            "type": "task",
            "timestamp": record.completed_at,
            "task_id": record.task_id,
            "status": record.status,
            "strategy": record.strategy,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "duration_seconds": record.duration_seconds,
            "files": record.files,
            "conflict_count": record.conflict_count,
            "shard_count": record.shard_count,
            "metadata": record.metadata,
        }
        self._history.append(entry)
        self._save_history()
        self._cleanup_old_entries()

    def record_conflict(self, record: ConflictRecord) -> None:
        entry = {
            "type": "conflict",
            "timestamp": record.timestamp or datetime.now().isoformat(),
            "task_a_id": record.task_a_id,
            "task_b_id": record.task_b_id,
            "conflict_type": record.conflict_type,
            "severity": record.severity,
            "resolved": record.resolved,
            "resolution_strategy": record.resolution_strategy,
        }
        self._history.append(entry)
        self._save_history()

    def record_engine_result(self, result: Dict[str, Any],
                              manifest: Optional[TaskManifest] = None) -> None:
        now = datetime.now().isoformat()
        stats = result.get("stats", {})
        status = result.get("status", "unknown")
        strategy = manifest.strategy.value if manifest else "unknown"

        for item in result.get("results", []):
            record = TaskRecord(
                task_id=item.get("task_id", "unknown"),
                status=item.get("status", status),
                strategy=strategy,
                started_at=item.get("started_at", now),
                completed_at=item.get("completed_at", now),
                duration_seconds=item.get("duration_seconds", 0.0),
                files=item.get("files", []),
                conflict_count=item.get("conflict_count", 0),
                shard_count=stats.get("total_shards", 1),
            )
            self.record_task(record)

        conflict_analysis = result.get("conflict_analysis", {})
        for pred in conflict_analysis.get("predictions", []):
            tasks = pred.get("tasks", [])
            if len(tasks) >= 2:
                self.record_conflict(ConflictRecord(
                    task_a_id=tasks[0],
                    task_b_id=tasks[1],
                    conflict_type=pred.get("type", "unknown"),
                    severity=pred.get("severity", "low"),
                    timestamp=now,
                ))

    def get_task_records(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        records = [e for e in self._history if e.get("type") == "task"]
        if since:
            records = [r for r in records if r.get("timestamp", "") >= since]
        return records

    def get_conflict_records(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        records = [e for e in self._history if e.get("type") == "conflict"]
        if since:
            records = [r for r in records if r.get("timestamp", "") >= since]
        return records

    def get_strategy_stats(self) -> Dict[str, Dict[str, Any]]:
        task_records = self.get_task_records()
        stats: Dict[str, Dict[str, Any]] = {}
        for r in task_records:
            s = r.get("strategy", "unknown")
            if s not in stats:
                stats[s] = {"total": 0, "success": 0, "fail": 0, "durations": []}
            stats[s]["total"] += 1
            if r.get("status") == "success":
                stats[s]["success"] += 1
            else:
                stats[s]["fail"] += 1
            stats[s]["durations"].append(r.get("duration_seconds", 0.0))
        for s, data in stats.items():
            durations = data.pop("durations")
            data["avg_duration"] = statistics.mean(durations) if durations else 0.0
            data["success_rate"] = data["success"] / data["total"] if data["total"] > 0 else 0.0
        return stats

    def analyze_history(self, period_days: int = 7) -> EvolutionReport:
        cutoff = datetime.now() - timedelta(days=period_days)
        cutoff_iso = cutoff.isoformat()
        now_iso = datetime.now().isoformat()
        task_records = [
            r for r in self.get_task_records(since=cutoff_iso)
            if r.get("timestamp", "") <= now_iso
        ]
        conflict_records = self.get_conflict_records(since=cutoff_iso)
        aggregated = self._aggregate_metrics(
            task_records, conflict_records, period_days, cutoff_iso, now_iso
        )
        trend = self._detect_trend(period_days)
        strategy_scores = self._compute_strategy_scores(task_records)
        recommendations = self._generate_recommendations(aggregated, strategy_scores)
        return EvolutionReport(
            period_days=period_days,
            period_start=cutoff_iso,
            period_end=now_iso,
            aggregated=aggregated,
            trend=trend,
            recommendations=recommendations,
            strategy_scores=strategy_scores,
        )

    def _aggregate_metrics(self, tasks: List[Dict], conflicts: List[Dict],
                           period_days: int, start: str, end: str) -> AggregatedMetrics:
        total = len(tasks)
        successful = sum(1 for t in tasks if t.get("status") == "success")
        failed = total - successful
        success_rate = successful / total if total > 0 else 0.0
        durations = [t.get("duration_seconds", 0.0) for t in tasks]
        avg_dur = statistics.mean(durations) if durations else 0.0
        med_dur = statistics.median(durations) if durations else 0.0
        p95_dur = (sorted(durations)[int(len(durations) * 0.95)]
                   if len(durations) >= 2 else avg_dur)
        parallel_eff = self._compute_parallel_efficiency(tasks)
        conflict_rate = len(conflicts) / total if total > 0 else 0.0
        strategy_breakdown = self._compute_strategy_breakdown(tasks)
        return AggregatedMetrics(
            period_start=start,
            period_end=end,
            total_tasks=total,
            successful_tasks=successful,
            failed_tasks=failed,
            task_success_rate=success_rate,
            avg_duration_seconds=avg_dur,
            median_duration_seconds=med_dur,
            p95_duration_seconds=p95_dur,
            parallel_efficiency=parallel_eff,
            conflict_rate=conflict_rate,
            total_conflicts=len(conflicts),
            strategy_breakdown=strategy_breakdown,
        )

    def _compute_parallel_efficiency(self, tasks: List[Dict]) -> float:
        if not tasks:
            return 0.0
        total_shards = sum(t.get("shard_count", 1) for t in tasks)
        if total_shards > 0:
            return min(1.0, len(tasks) / total_shards)
        return 0.0

    def _compute_strategy_breakdown(self, tasks: List[Dict]) -> Dict[str, Dict[str, Any]]:
        breakdown: Dict[str, Dict[str, Any]] = {}
        for t in tasks:
            s = t.get("strategy", "unknown")
            if s not in breakdown:
                breakdown[s] = {
                    "count": 0, "success": 0, "avg_duration": 0.0,
                    "durations": []
                }
            breakdown[s]["count"] += 1
            if t.get("status") == "success":
                breakdown[s]["success"] += 1
            breakdown[s]["durations"].append(t.get("duration_seconds", 0.0))
        for s, data in breakdown.items():
            data["avg_duration"] = statistics.mean(data["durations"]) if data["durations"] else 0.0
            data["success_rate"] = data["success"] / data["count"] if data["count"] > 0 else 0.0
            del data["durations"]
        return breakdown

    def _detect_trend(self, period_days: int) -> str:
        half = period_days // 2
        if half < 1:
            half = 1
        now = datetime.now()
        mid = now - timedelta(days=half)
        start = now - timedelta(days=period_days)
        early = [
            r for r in self.get_task_records(since=start.isoformat())
            if r.get("timestamp", "") < mid.isoformat()
        ]
        late = [
            r for r in self.get_task_records(since=mid.isoformat())
            if r.get("timestamp", "") <= now.isoformat()
        ]
        if not early or not late:
            return "stable"
        early_rate = sum(1 for r in early if r.get("status") == "success") / len(early)
        late_rate = sum(1 for r in late if r.get("status") == "success") / len(late)
        diff = late_rate - early_rate
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "degrading"
        return "stable"

    def _compute_strategy_scores(self, tasks: List[Dict]) -> Dict[str, float]:
        if not tasks:
            return {}
        strategy_map: Dict[str, List[Dict]] = {}
        for t in tasks:
            s = t.get("strategy", "unknown")
            strategy_map.setdefault(s, []).append(t)
        scores: Dict[str, float] = {}
        all_durations = [t.get("duration_seconds", 0.0) for t in tasks]
        max_duration = max(all_durations) if all_durations else 1.0
        for s, records in strategy_map.items():
            success_count = sum(1 for r in records if r.get("status") == "success")
            success_rate = success_count / len(records) if records else 0.0
            durations = [r.get("duration_seconds", 0.0) for r in records]
            avg_dur = statistics.mean(durations) if durations else max_duration
            speed_score = 1.0 - (avg_dur / max_duration) if max_duration > 0 else 1.0
            scores[s] = success_rate * 0.6 + speed_score * 0.4
        return scores

    def _generate_recommendations(self, aggregated: AggregatedMetrics,
                                  strategy_scores: Dict[str, float]) -> List[str]:
        recs: List[str] = []
        if aggregated.task_success_rate < 0.8:
            recs.append(
                f"成功率偏低 ({aggregated.task_success_rate:.1%})，"
                "建议检查失败任务的共性原因"
            )
        if aggregated.conflict_rate > 0.3:
            recs.append(
                f"冲突率偏高 ({aggregated.conflict_rate:.1%})，"
                "建议增加文件级锁或优化分片策略"
            )
        if aggregated.parallel_efficiency < 0.5 and aggregated.total_tasks > 3:
            recs.append(
                f"并行效率偏低 ({aggregated.parallel_efficiency:.1%})，"
                "考虑调整 max_concurrent 或减少文件依赖"
            )
        if strategy_scores:
            best = max(strategy_scores, key=strategy_scores.get)
            worst = min(strategy_scores, key=strategy_scores.get)
            if strategy_scores[best] - strategy_scores[worst] > 0.2:
                recs.append(
                    f"策略 '{best}' 表现显著优于 '{worst}'，"
                    f"建议在 AUTO 模式下优先使用 '{best}'"
                )
        if aggregated.p95_duration_seconds > 120:
            recs.append(
                f"P95 耗时 {aggregated.p95_duration_seconds:.0f}s 偏高，"
                "建议拆分大任务或设置更严格的超时"
            )
        return recs

    def recommend_strategy(self, manifest: TaskManifest) -> SchedulingStrategy:
        task_records = self.get_task_records()
        if not task_records:
            return SchedulingStrategy.AUTO
        task_count = manifest.task_count
        file_count = manifest.file_count
        similar = [
            r for r in task_records
            if self._is_similar_manifest(r, task_count, file_count)
        ]
        if not similar:
            return SchedulingStrategy.AUTO
        strategy_stats: Dict[str, List[Dict]] = {}
        for r in similar:
            s = r.get("strategy", "unknown")
            strategy_stats.setdefault(s, []).append(r)
        best_strategy = SchedulingStrategy.AUTO
        best_score = -1.0
        for s_name, records in strategy_stats.items():
            success_rate = (
                sum(1 for r in records if r.get("status") == "success") / len(records)
                if records else 0.0
            )
            avg_dur = statistics.mean(
                [r.get("duration_seconds", 0.0) for r in records]
            ) if records else 0.0
            score = success_rate * 0.7 + (1.0 / (1.0 + avg_dur)) * 0.3
            if score > best_score:
                best_score = score
                try:
                    best_strategy = SchedulingStrategy(s_name)
                except ValueError:
                    pass
        return best_strategy

    def _is_similar_manifest(self, record: Dict, task_count: int,
                              file_count: int) -> bool:
        record_files = len(record.get("files", []))
        if record_files > 0 and file_count > 0:
            file_ratio = abs(record_files - file_count) / max(record_files, file_count)
            if file_ratio <= 0.5:
                return True
        return False

    def adjust_sharding(self, file_pairs: List[Tuple[str, str]],
                         conflict_history: Optional[List[Dict]] = None) -> List[List[str]]:
        if not file_pairs:
            return []
        if conflict_history is None:
            conflict_history = self.get_conflict_records()
        conflict_freq: Dict[Tuple[str, str], int] = {}
        for c in conflict_history:
            key = self._conflict_key(c.get("task_a_id", ""), c.get("task_b_id", ""))
            conflict_freq[key] = conflict_freq.get(key, 0) + 1
        return self._group_by_conflict_frequency(file_pairs, conflict_freq)

    def _conflict_key(self, a: str, b: str) -> Tuple[str, str]:
        return tuple(sorted([a, b]))

    def _group_by_conflict_frequency(
        self, file_pairs: List[Tuple[str, str]],
        conflict_freq: Dict[Tuple[str, str], int]
    ) -> List[List[str]]:
        all_files: set = set()
        for a, b in file_pairs:
            all_files.add(a)
            all_files.add(b)
        file_conflicts: Dict[str, set] = {f: set() for f in all_files}
        groups: List[List[str]] = []
        assigned: Dict[str, int] = {}
        for f_a, f_b in file_pairs:
            a_group = assigned.get(f_a)
            b_group = assigned.get(f_b)
            if a_group is not None and b_group is not None:
                continue
            elif a_group is not None:
                if not self._would_conflict(f_b, groups[a_group], file_conflicts):
                    groups[a_group].append(f_b)
                    assigned[f_b] = a_group
                else:
                    new_idx = len(groups)
                    groups.append([f_b])
                    assigned[f_b] = new_idx
            elif b_group is not None:
                if not self._would_conflict(f_a, groups[b_group], file_conflicts):
                    groups[b_group].append(f_a)
                    assigned[f_a] = b_group
                else:
                    new_idx = len(groups)
                    groups.append([f_a])
                    assigned[f_a] = new_idx
            else:
                new_idx = len(groups)
                groups.append([f_a, f_b])
                assigned[f_a] = new_idx
                assigned[f_b] = new_idx
        return groups

    def _would_conflict(self, file: str, group: List[str],
                         file_conflicts: Dict[str, set]) -> bool:
        for g_file in group:
            if file in file_conflicts.get(g_file, set()):
                return True
        return False

    def weekly_report(self) -> Dict[str, Any]:
        from .reporter import weekly_report
        return weekly_report(self)

    def _daily_breakdown(self, days: int = 7) -> List[Dict[str, Any]]:
        now = datetime.now()
        daily: List[Dict[str, Any]] = []
        for i in range(days - 1, -1, -1):
            day = now - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            day_tasks = [
                r for r in self.get_task_records()
                if day_start.isoformat() <= r.get("timestamp", "") < day_end.isoformat()
            ]
            day_conflicts = [
                r for r in self.get_conflict_records()
                if day_start.isoformat() <= r.get("timestamp", "") < day_end.isoformat()
            ]
            total = len(day_tasks)
            success = sum(1 for t in day_tasks if t.get("status") == "success")
            daily.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "total_tasks": total,
                "success_rate": round(success / total, 4) if total > 0 else None,
                "conflicts": len(day_conflicts),
                "avg_duration": round(
                    statistics.mean([t.get("duration_seconds", 0) for t in day_tasks]), 2
                ) if day_tasks else None,
            })
        return daily

    def stats(self) -> Dict[str, Any]:
        return {
            "total_records": len(self._history),
            "task_records": sum(1 for e in self._history if e.get("type") == "task"),
            "conflict_records": sum(1 for e in self._history if e.get("type") == "conflict"),
            "metrics_file": str(self.metrics_file),
            "retention_days": RETENTION_DAYS,
        }


__all__ = [
    # Rule-based
    "ConflictPredictor",
    "ConflictPrediction",
    # ML-enhanced
    "MLConflictRecord",
    "ConflictFeatures",
    "ConflictPredictionResult",
    "FeatureExtractor",
    "LinearModel",
    "MLModel",
    "MLConflictPredictor",
    # Evolution
    "EvolutionMetrics",
]

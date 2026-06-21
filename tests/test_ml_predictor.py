"""ML 增强冲突预测器测试

覆盖: 特征提取、模型训练、在线更新、保存/加载、回退行为、预测置信度。
"""

import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pytest

# 被测模块
from agent.engine.ml_predictor import (
    ConflictRecord,
    ConflictFeatures,
    ConflictPredictionResult,
    FeatureExtractor,
    LinearModel,
    MLConflictPredictor,
)
from agent.engine.conflict import ConflictPrediction


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试辅助
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class FakeTask:
    """模拟 FixTask"""
    task_id: str
    files: List[str]


def _make_record(
    files_a: List[str],
    files_b: List[str],
    conflict: bool = True,
    conflict_type: str = "file_overlap",
    resolution: str = "serial",
) -> ConflictRecord:
    return ConflictRecord(
        task_a_files=files_a,
        task_b_files=files_b,
        actual_conflict=conflict,
        conflict_type=conflict_type,
        resolution=resolution,
    )


def _make_history(n: int, conflict_ratio: float = 0.5) -> List[ConflictRecord]:
    """生成 n 条训练记录"""
    records = []
    for i in range(n):
        is_conflict = (i % max(1, int(1 / conflict_ratio))) == 0 if conflict_ratio > 0 else False
        records.append(_make_record(
            files_a=[f"src/module_{i}.py"],
            files_b=[f"src/module_{i + 1}.py"] if is_conflict else [f"lib/other_{i}.py"],
            conflict=is_conflict,
        ))
    return records


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 特征提取测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFeatureExtractor:
    """FeatureExtractor 测试"""

    def test_file_overlap_ratio_identical(self):
        """相同文件集 -> 重叠率 1.0"""
        ext = FeatureExtractor()
        features = ext.extract(["a.py", "b.py"], ["a.py", "b.py"])
        assert features.file_overlap_ratio == 1.0

    def test_file_overlap_ratio_partial(self):
        """部分重叠"""
        ext = FeatureExtractor()
        features = ext.extract(["a.py", "b.py"], ["b.py", "c.py"])
        assert abs(features.file_overlap_ratio - 1 / 3) < 1e-6

    def test_file_overlap_ratio_empty(self):
        """空文件集 -> 0.0"""
        ext = FeatureExtractor()
        features = ext.extract([], ["a.py"])
        assert features.file_overlap_ratio == 0.0

    def test_same_directory_detection(self):
        """同目录检测"""
        ext = FeatureExtractor()
        # 同目录
        f1 = ext.extract(["src/a.py"], ["src/b.py"])
        assert f1.same_directory == 1.0
        # 不同目录
        f2 = ext.extract(["src/a.py"], ["lib/b.py"])
        assert f2.same_directory == 0.0

    def test_to_list_conversion(self):
        """特征向量转换"""
        f = ConflictFeatures(0.5, 1.0, 0.0, 0.3, 0.2)
        vec = f.to_list()
        assert len(vec) == 5
        assert vec[0] == 0.5
        assert vec[1] == 1.0

    def test_feature_names(self):
        """特征名列表长度 == 5"""
        assert len(ConflictFeatures.feature_names()) == 5

    def test_pattern_stats_update(self):
        """模式统计更新"""
        ext = FeatureExtractor()
        ext.update_pattern_stats({"a.py"}, {"b.py"}, had_conflict=True)
        ext.update_pattern_stats({"a.py"}, {"b.py"}, had_conflict=False)
        ext.update_pattern_stats({"a.py"}, {"b.py"}, had_conflict=True)
        # 2/3 冲突
        rate = ext._historical_conflict_rate({"a.py"}, {"b.py"})
        assert abs(rate - 2 / 3) < 1e-6


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 线性模型测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLinearModel:
    """LinearModel 测试"""

    def test_initial_prediction_near_0_5(self):
        """初始模型预测应接近 0.5 (未训练)"""
        model = LinearModel(n_features=5)
        features = [0.0, 0.0, 0.0, 0.5, 0.0]
        pred = model.predict(features)
        assert 0.3 < pred < 0.7

    def test_sigmoid_bounds(self):
        """预测值始终在 [0, 1]"""
        model = LinearModel(n_features=5)
        for _ in range(20):
            features = [float(i) for i in range(5)]
            pred = model.predict(features)
            assert 0.0 <= pred <= 1.0

    def test_online_update_moves_weights(self):
        """在线更新后权重应改变"""
        model = LinearModel(n_features=5, learning_rate=0.1)
        old_weights = list(model.model.weights)
        # 用不同的特征更新以确保梯度非零
        for i in range(10):
            features = [float(i % 5) / 5, float((i + 1) % 3) / 3,
                        float(i % 2), float((i + 2) % 4) / 4,
                        float(i % 7) / 7]
            model.update(features, 1.0)
        # 权重应变化
        assert model.model.weights != old_weights
        assert model.model.update_count == 10

    def test_save_load_roundtrip(self):
        """保存/加载后预测一致"""
        model = LinearModel(n_features=5, learning_rate=0.05)
        # 训练几步
        features = [0.5, 1.0, 0.0, 0.3, 0.1]
        for _ in range(5):
            model.update(features, 1.0)
        pred_before = model.predict(features)

        # 保存/加载
        data = model.to_dict()
        model2 = LinearModel(n_features=5)
        model2.load_dict(data)
        pred_after = model2.predict(features)

        assert abs(pred_before - pred_after) < 1e-3

    def test_prediction_converges(self):
        """连续用同一标签训练后，预测应收敛"""
        model = LinearModel(n_features=5, learning_rate=0.1)
        features = [0.8, 1.0, 0.0, 0.5, 0.3]
        # 用 "冲突" 标签训练 50 次
        for _ in range(50):
            model.update(features, 1.0)
        pred = model.predict(features)
        assert pred > 0.6  # 应该偏向冲突


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MLConflictPredictor 集成测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMLConflictPredictor:
    """MLConflictPredictor 集成测试"""

    def test_fallback_to_rule_with_no_history(self):
        """无历史时回退到规则引擎"""
        with tempfile.TemporaryDirectory() as tmpdir:
            predictor = MLConflictPredictor(model_dir=tmpdir)
            task_a = FakeTask("t1", ["same.py"])
            task_b = FakeTask("t2", ["same.py"])
            result = predictor.predict(task_a, task_b)
            assert result.method == "rule"
            assert result.conflict_prob > 0.0  # 同文件应有冲突

    def test_ml_activation_with_sufficient_history(self):
        """10+ 条历史后启用 ML (warmup=0 时)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            predictor = MLConflictPredictor(model_dir=tmpdir, warmup_samples=0)
            history = _make_history(15, conflict_ratio=0.5)
            predictor.train(history)
            assert predictor.uses_ml

            task_a = FakeTask("t1", ["src/a.py"])
            task_b = FakeTask("t2", ["src/b.py"])
            result = predictor.predict(task_a, task_b)
            assert result.method in ("ml", "hybrid")

    def test_online_update_increases_history(self):
        """在线更新增加历史记录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            predictor = MLConflictPredictor(model_dir=tmpdir)
            assert predictor.history_size == 0

            record = _make_record(["a.py"], ["b.py"], conflict=True)
            predictor.online_update(record)
            assert predictor.history_size == 1

            # 10 次后应该启用 ML
            for i in range(9):
                predictor.online_update(_make_record(
                    [f"x{i}.py"], [f"y{i}.py"], conflict=(i % 2 == 0)
                ))
            assert predictor.uses_ml

    def test_model_save_load(self):
        """模型保存/加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 训练并保存
            predictor = MLConflictPredictor(model_dir=tmpdir)
            history = _make_history(20, conflict_ratio=0.5)
            predictor.train(history)
            predictor.save()

            # 加载验证
            predictor2 = MLConflictPredictor(model_dir=tmpdir)
            assert predictor2.history_size == 20
            assert predictor2.uses_ml

            # 两个模型对相同输入预测应一致
            task_a = FakeTask("t1", ["a.py", "b.py"])
            task_b = FakeTask("t2", ["b.py", "c.py"])
            r1 = predictor.predict(task_a, task_b)
            r2 = predictor2.predict(task_a, task_b)
            assert abs(r1.conflict_prob - r2.conflict_prob) < 1e-3

    def test_confidence_increases_with_samples(self):
        """置信度随样本量增加而增加"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = MLConflictPredictor(model_dir=tmpdir)
            history = _make_history(12)
            p.train(history)

            task_a = FakeTask("t1", ["a.py"])
            task_b = FakeTask("t2", ["b.py"])
            r1 = p.predict(task_a, task_b)

            # 加更多数据
            for i in range(30):
                p.online_update(_make_record(
                    [f"z{i}.py"], [f"w{i}.py"], conflict=(i % 3 == 0)
                ))
            r2 = p.predict(task_a, task_b)
            assert r2.confidence >= r1.confidence

    def test_same_file_prediction_high_conflict(self):
        """相同文件应该高冲突概率"""
        with tempfile.TemporaryDirectory() as tmpdir:
            predictor = MLConflictPredictor(model_dir=tmpdir)
            task_a = FakeTask("t1", ["core.py"])
            task_b = FakeTask("t2", ["core.py"])
            result = predictor.predict(task_a, task_b)
            assert result.conflict_prob > 0.5

    def test_different_directories_low_conflict(self):
        """完全不同的文件/目录应该低冲突"""
        with tempfile.TemporaryDirectory() as tmpdir:
            predictor = MLConflictPredictor(model_dir=tmpdir)
            task_a = FakeTask("t1", ["src/a.py"])
            task_b = FakeTask("t2", ["lib/b.py"])
            result = predictor.predict(task_a, task_b)
            # 规则引擎下不同文件无冲突
            assert result.method == "rule"
            assert result.conflict_prob == 0.0

    def test_training_with_mixed_labels(self):
        """混合标签训练后模型不崩溃"""
        with tempfile.TemporaryDirectory() as tmpdir:
            predictor = MLConflictPredictor(model_dir=tmpdir)
            history = []
            for i in range(20):
                history.append(_make_record(
                    files_a=[f"f{i}.py"],
                    files_b=[f"g{i}.py"],
                    conflict=(i % 2 == 0),
                ))
            predictor.train(history)
            assert predictor.model_update_count > 0

            task_a = FakeTask("t1", ["x.py"])
            task_b = FakeTask("t2", ["y.py"])
            result = predictor.predict(task_a, task_b)
            assert 0.0 <= result.conflict_prob <= 1.0
            assert 0.0 <= result.confidence <= 1.0

    def test_corrupted_model_file_fallback(self):
        """损坏的模型文件不影响启动"""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "conflict_model.json"
            model_path.write_text("not valid json {{{", encoding="utf-8")

            # 不应抛异常
            predictor = MLConflictPredictor(model_dir=tmpdir)
            assert predictor.history_size == 0

            task_a = FakeTask("t1", ["a.py"])
            task_b = FakeTask("t2", ["b.py"])
            result = predictor.predict(task_a, task_b)
            assert result.method == "rule"

    def test_features_extracted_in_prediction(self):
        """预测结果包含特征"""
        with tempfile.TemporaryDirectory() as tmpdir:
            predictor = MLConflictPredictor(model_dir=tmpdir)
            task_a = FakeTask("t1", ["src/a.py", "src/b.py"])
            task_b = FakeTask("t2", ["src/b.py", "src/c.py"])
            result = predictor.predict(task_a, task_b)
            assert isinstance(result.features, ConflictFeatures)
            assert result.features.file_overlap_ratio > 0.0

    def test_no_conflict_record_fields(self):
        """ConflictRecord 默认字段"""
        r = ConflictRecord(
            task_a_files=["a.py"],
            task_b_files=["b.py"],
            actual_conflict=False,
            conflict_type="none",
            resolution="merged",
        )
        assert r.timestamp  # 自动生成
        assert r.actual_conflict is False

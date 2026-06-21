"""ML Conflict Predictor -- backward-compatible re-export from predictor module."""

from .predictor import (
    MLConflictRecord as ConflictRecord,
    ConflictFeatures,
    ConflictPredictionResult,
    FeatureExtractor,
    LinearModel,
    MLModel,
    MLConflictPredictor,
)

# Backward compat: ConflictRecord alias (original was in ml_predictor.py)
ConflictRecord = ConflictRecord

__all__ = [
    "ConflictRecord",
    "ConflictFeatures",
    "ConflictPredictionResult",
    "FeatureExtractor",
    "LinearModel",
    "MLModel",
    "MLConflictPredictor",
]

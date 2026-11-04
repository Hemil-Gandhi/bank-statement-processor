"""Load and query the persisted classical classifier (no external AI calls)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.classification.preprocess_text import build_feature_text
from app.config import settings

logger = logging.getLogger(__name__)

_cache: dict[str, Any] = {"path": None, "mtime": None, "bundle": None}


@dataclass(slots=True)
class ModelPrediction:
    category: str
    confidence: float
    probabilities: dict[str, float] | None = None


def invalidate_cache() -> None:
    _cache["bundle"] = None
    _cache["path"] = None
    _cache["mtime"] = None


def model_available(path: str | Path | None = None) -> bool:
    return Path(path or settings.model_path).exists()


def load_model(path: str | Path | None = None) -> dict[str, Any] | None:
    model_path = Path(path or settings.model_path)
    if not model_path.exists():
        return None
    mtime = model_path.stat().st_mtime
    if _cache["bundle"] is not None and _cache["path"] == str(model_path) and _cache["mtime"] == mtime:
        return _cache["bundle"]
    try:
        bundle = joblib.load(model_path)
        if isinstance(bundle, dict) and "pipeline" in bundle:
            _cache.update({"path": str(model_path), "mtime": mtime, "bundle": bundle})
            return bundle
        logger.warning("model file has unexpected structure: %s", model_path)
    except Exception as exc:
        logger.warning("could not load classifier model %s: %s", model_path, exc)
    return None


def predict(
    description: str,
    direction: str,
    amount: Decimal | None,
    channel: str | None = None,
    *,
    path: str | Path | None = None,
) -> ModelPrediction | None:
    bundle = load_model(path)
    if bundle is None:
        return None
    pipeline = bundle["pipeline"]
    text = build_feature_text(description, direction, amount, channel)
    try:
        if hasattr(pipeline, "predict_proba"):
            probabilities = pipeline.predict_proba([text])[0]
            classes = list(pipeline.classes_)
        else:  # pragma: no cover - calibrated/softmax fallback
            decision = pipeline.decision_function([text])
            decision = np.atleast_2d(decision)[0]
            exp = np.exp(decision - np.max(decision))
            probabilities = exp / exp.sum()
            classes = list(pipeline.classes_)
        index = int(np.argmax(probabilities))
        category = str(classes[index])
        confidence = float(probabilities[index])
        top = sorted(
            (
                (str(label), float(prob))
                for label, prob in zip(classes, probabilities)
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        return ModelPrediction(
            category=category,
            confidence=round(confidence, 4),
            probabilities=dict(top),
        )
    except Exception as exc:
        logger.warning("ML prediction failed: %s", exc)
        return None

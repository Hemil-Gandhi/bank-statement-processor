"""Health, taxonomy, model info and retraining endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.classification.classifier import get_engine, reset_engine
from app.classification.ml_model import model_available
from app.classification.taxonomy import CATEGORIES, category_type
from app.classification.train import train_model
from app.config import settings
from app.core.ocr_extractor import ocr_available
from app.db import get_db
from app.models.db_models import UserOverride
from app.models.schemas import CategoryOut, HealthOut, RetrainOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        version=settings.version,
        timestamp=datetime.now(timezone.utc),
        ocr_available=ocr_available(),
        model_available=model_available(),
        database=database,
    )


@router.get("/categories", response_model=list[CategoryOut])
def categories() -> list[CategoryOut]:
    return [CategoryOut(name=name, type=category_type(name)) for name in CATEGORIES]


@router.get("/rules")
def rules() -> list[dict]:
    engine = get_engine()
    return [
        {
            "id": rule.id,
            "category": rule.category,
            "priority": rule.priority,
            "direction": rule.direction,
            "keywords": list(rule.keywords),
            "regex": list(rule.regex),
        }
        for rule in engine.rules.rules
    ]


@router.post("/classify/retrain", response_model=RetrainOut)
def retrain(db: Session = Depends(get_db)) -> RetrainOut:
    overrides = db.query(UserOverride).count()
    try:
        result = train_model(with_overrides=True, quick=True)
    except Exception as exc:
        logger.exception("retraining failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "RETRAIN_FAILED", "message": str(exc)},
        ) from exc
    reset_engine()
    return RetrainOut(
        status=result["status"],
        samples=result["samples"],
        overrides_used=overrides,
        accuracy=result.get("accuracy"),
        model_path=result["model_path"],
    )

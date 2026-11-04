"""Classification orchestrator: user overrides -> rules -> classical ML -> fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from rapidfuzz import fuzz

from app.classification.ml_model import predict as ml_predict
from app.classification.preprocess_text import normalize_for_override
from app.classification.rules import RuleEngine
from app.classification.taxonomy import CATEGORIES
from app.classification.upi_parser import parse_upi
from app.core.normalizer import detect_channel
from app.core.types import TransactionDraft

logger = logging.getLogger(__name__)

ML_CONFIDENCE_THRESHOLD = 0.45
OVERRIDE_FUZZY_THRESHOLD = 88


@dataclass(slots=True)
class OverrideEntry:
    normalized: str
    category: str
    pattern: str


@dataclass(slots=True)
class ClassificationOutcome:
    category: str
    source: str
    confidence: float
    reason: str


def load_overrides(session) -> list[OverrideEntry]:  # type: ignore[no-untyped-def]
    if session is None:
        return []
    try:
        from app.models.db_models import UserOverride

        rows = session.query(UserOverride).all()
        return [
            OverrideEntry(
                normalized=row.normalized_pattern,
                category=row.category,
                pattern=row.description_pattern,
            )
            for row in rows
            if row.category in CATEGORIES
        ]
    except Exception as exc:
        logger.warning("could not load user overrides: %s", exc)
        return []


def similarity(left: str, right: str) -> float:
    a = normalize_for_override(left)
    b = normalize_for_override(right)
    if not a or not b:
        return 0.0
    return max(
        fuzz.token_set_ratio(a, b),
        fuzz.partial_ratio(a, b) if min(len(a), len(b)) >= 6 else 0.0,
    )


def match_override(
    description: str, overrides: Iterable[OverrideEntry]
) -> OverrideEntry | None:
    normalized = normalize_for_override(description)
    if not normalized:
        return None
    best: tuple[float, OverrideEntry] | None = None
    for override in overrides:
        if override.normalized == normalized:
            return override
        if len(override.normalized) < 4 or len(normalized) < 4:
            continue
        score = fuzz.token_set_ratio(normalized, override.normalized)
        if score >= OVERRIDE_FUZZY_THRESHOLD and (best is None or score > best[0]):
            best = (score, override)
    return best[1] if best else None


class ClassificationEngine:
    def __init__(self, rules: RuleEngine | None = None):
        self.rules = rules or RuleEngine.from_yaml()
        self.warnings = list(self.rules.warnings)

    def classify(
        self,
        description: str,
        direction: str,
        amount: Decimal | None,
        *,
        channel: str | None = None,
        overrides: Iterable[OverrideEntry] | None = None,
    ) -> ClassificationOutcome:
        overrides = overrides or []
        override = match_override(description, overrides)
        if override is not None:
            return ClassificationOutcome(
                category=override.category,
                source="user",
                confidence=0.99,
                reason=f"user override matched '{override.pattern[:80]}'",
            )

        channel = channel or detect_channel(description)
        upi = parse_upi(description)
        rule_match = self.rules.match(description, direction, amount, upi=upi)
        if rule_match is not None and rule_match.confidence >= 0.75:
            return ClassificationOutcome(
                category=rule_match.category,
                source="rule",
                confidence=rule_match.confidence,
                reason=rule_match.reason,
            )

        prediction = ml_predict(description, direction, amount, channel)
        if prediction is not None:
            if prediction.confidence >= ML_CONFIDENCE_THRESHOLD:
                if rule_match is not None and rule_match.confidence >= prediction.confidence:
                    return ClassificationOutcome(
                        category=rule_match.category,
                        source="rule",
                        confidence=rule_match.confidence,
                        reason=rule_match.reason,
                    )
                return ClassificationOutcome(
                    category=prediction.category,
                    source="ml",
                    confidence=prediction.confidence,
                    reason=(
                        f"TF-IDF + Logistic/SVM fallback (p={prediction.confidence:.2f})"
                    ),
                )
            if rule_match is not None:
                return ClassificationOutcome(
                    category=rule_match.category,
                    source="rule",
                    confidence=rule_match.confidence,
                    reason=rule_match.reason,
                )
            return ClassificationOutcome(
                category="Uncategorized",
                source="fallback",
                confidence=prediction.confidence,
                reason=(
                    f"ML confidence {prediction.confidence:.2f} is below "
                    f"{ML_CONFIDENCE_THRESHOLD:.2f}; left for review"
                ),
            )

        if rule_match is not None:
            return ClassificationOutcome(
                category=rule_match.category,
                source="rule",
                confidence=rule_match.confidence,
                reason=rule_match.reason,
            )
        return ClassificationOutcome(
            category="Uncategorized",
            source="fallback",
            confidence=0.0,
            reason="no rule matched and the ML model is unavailable",
        )

    def classify_transactions(
        self,
        transactions: list[TransactionDraft],
        overrides: Iterable[OverrideEntry] | None = None,
    ) -> None:
        overrides = list(overrides or [])
        for transaction in transactions:
            outcome = self.classify(
                transaction.description,
                transaction.direction,
                transaction.amount,
                overrides=overrides,
            )
            transaction.category = outcome.category
            transaction.category_source = outcome.source
            transaction.category_confidence = outcome.confidence
            transaction.reason = outcome.reason
            if outcome.source == "fallback":
                if "uncategorized" not in transaction.flags:
                    transaction.flags.append("uncategorized")
            elif outcome.source == "ml" and outcome.confidence < 0.55:
                if "low_confidence_category" not in transaction.flags:
                    transaction.flags.append("low_confidence_category")


_engine: ClassificationEngine | None = None


def get_engine() -> ClassificationEngine:
    global _engine
    if _engine is None:
        _engine = ClassificationEngine()
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None

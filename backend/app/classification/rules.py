"""YAML-driven heuristic rule engine with priority/specificity conflict resolution."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

from app.classification.taxonomy import CATEGORIES, is_valid_category
from app.classification.upi_parser import UPIDetails, parse_upi

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = Path(__file__).with_name("rules_config.yaml")


def _normalize(text: str) -> str:
    text = (text or "").upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    category: str
    priority: int
    direction: str = "any"
    keywords: tuple[str, ...] = ()
    regex: tuple[str, ...] = ()
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    reason: str = ""


@dataclass(slots=True)
class RuleMatch:
    category: str
    confidence: float
    reason: str
    rule_id: str
    matched_text: str
    score: int


@dataclass(slots=True)
class RuleEngine:
    rules: list[Rule] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> "RuleEngine":
        config_path = Path(path) if path else DEFAULT_CONFIG
        warnings: list[str] = []
        rules: list[Rule] = []
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            for item in data.get("rules", []):
                category = str(item.get("category", "")).strip()
                if not is_valid_category(category):
                    warnings.append(f"unknown_category_in_rules: {category}")
                    continue
                min_amount = item.get("min_amount")
                max_amount = item.get("max_amount")
                rules.append(
                    Rule(
                        id=str(item.get("id") or f"rule_{len(rules)}"),
                        category=category,
                        priority=int(item.get("priority", 50)),
                        direction=str(item.get("direction", "any")).lower(),
                        keywords=tuple(str(value).upper() for value in item.get("keywords", []) or []),
                        regex=tuple(str(value) for value in item.get("regex", []) or []),
                        min_amount=Decimal(str(min_amount)) if min_amount is not None else None,
                        max_amount=Decimal(str(max_amount)) if max_amount is not None else None,
                        reason=str(item.get("reason", "")),
                    )
                )
        except Exception as exc:
            logger.error("failed to load rules config %s: %s", config_path, exc)
            warnings.append(f"rules_config_error: {exc}")
        if not rules:
            warnings.append("rules_config_empty: falling back to ML/Uncategorized only.")
        logger.info("loaded %s classification rules", len(rules))
        return cls(rules=rules, warnings=warnings)

    def match(
        self,
        description: str,
        direction: str,
        amount: Decimal | None,
        upi: UPIDetails | None = None,
    ) -> RuleMatch | None:
        raw = (description or "").upper()
        normalized = _normalize(description)
        upi = upi or parse_upi(description)
        extra = " ".join(
            value for value in (upi.payee, upi.remark, upi.vpa) if value
        )
        search_text = _normalize(f"{normalized} {extra}")
        direction = (direction or "unknown").lower()
        matches: list[RuleMatch] = []

        for rule in self.rules:
            if rule.direction not in {"any", direction}:
                if direction == "unknown" and rule.direction in {"debit", "credit"}:
                    pass  # allow with reduced confidence when direction is unknown
                else:
                    continue
            if amount is not None:
                value = abs(amount)
                if rule.min_amount is not None and value < rule.min_amount:
                    continue
                if rule.max_amount is not None and value > rule.max_amount:
                    continue

            best_text = ""
            best_confidence = 0.0
            for keyword in rule.keywords:
                needle = _normalize(keyword)
                if not needle:
                    continue
                if re.search(
                    rf"(?<![A-Z0-9]){re.escape(needle)}(?![A-Z0-9])", search_text
                ):
                    if len(needle) > len(best_text):
                        best_text = needle
                        best_confidence = 0.90 if len(needle) > 3 else 0.84
            for pattern in rule.regex:
                try:
                    found = re.search(pattern, raw, re.IGNORECASE)
                except re.error:
                    logger.warning("invalid regex in rule %s: %s", rule.id, pattern)
                    continue
                if found:
                    text = found.group(0)
                    if len(text) > len(best_text):
                        best_text = text.upper()
                        best_confidence = 0.94
            if not best_text:
                continue
            if direction == "unknown" and rule.direction in {"debit", "credit"}:
                best_confidence = min(best_confidence, 0.72)
            score = (
                rule.priority * 100
                + len(best_text)
                + (25 if rule.direction == direction else 0)
                + (15 if best_confidence >= 0.93 else 0)
            )
            reason = rule.reason or f"matched {rule.category}"
            matches.append(
                RuleMatch(
                    category=rule.category,
                    confidence=best_confidence,
                    reason=f"{reason}: matched '{best_text}'",
                    rule_id=rule.id,
                    matched_text=best_text,
                    score=score,
                )
            )

        if not matches:
            return None
        matches.sort(key=lambda item: (-item.score, -len(item.matched_text)))
        return matches[0]

    def categories(self) -> set[str]:
        return {rule.category for rule in self.rules}

    def coverage_warnings(self) -> list[str]:
        missing = sorted(set(CATEGORIES) - self.categories() - {"Uncategorized"})
        return [f"category_without_rules: {category}" for category in missing]

"""CLI and library entry point for training the classical classifier.

Usage (from backend/):
    python -m app.classification.train
    python -m app.classification.train --with-overrides --quick
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

from app.classification.features import make_pipeline
from app.classification.preprocess_text import build_feature_text
from app.classification.taxonomy import CATEGORIES, is_valid_category
from app.config import settings

logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal | None:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        text = str(value).strip()
        return Decimal(text) if text else None
    except (InvalidOperation, ValueError):
        return None


def _load_training_rows(csv_path: Path, with_overrides: bool) -> list[dict]:
    if not csv_path.exists():
        raise FileNotFoundError(f"training CSV not found: {csv_path}")
    frame = pd.read_csv(csv_path)
    required = {"description", "category"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"training CSV missing columns: {sorted(missing)}")
    rows: list[dict] = []
    for record in frame.to_dict(orient="records"):
        category = str(record.get("category", "")).strip()
        description = str(record.get("description", "")).strip()
        if not description or not is_valid_category(category) or category == "Uncategorized":
            continue
        rows.append(
            {
                "description": description,
                "category": category,
                "direction": str(record.get("direction") or "unknown").lower(),
                "amount": _to_decimal(record.get("amount")),
                "channel": str(record.get("channel") or "") or None,
            }
        )
    if with_overrides:
        try:
            from app.db import SessionLocal
            from app.models.db_models import UserOverride

            session = SessionLocal()
            try:
                overrides = session.query(UserOverride).all()
                for override in overrides:
                    if not is_valid_category(override.category):
                        continue
                    for _ in range(3):
                        rows.append(
                            {
                                "description": override.description_pattern,
                                "category": override.category,
                                "direction": "unknown",
                                "amount": None,
                                "channel": None,
                            }
                        )
            finally:
                session.close()
        except Exception as exc:
            logger.warning("could not load user overrides: %s", exc)
    return rows


def _confusion_svg(matrix: np.ndarray, labels: list[str], path: Path) -> None:
    size = 26
    margin_left = 210
    margin_top = 180
    width = margin_left + size * len(labels) + 30
    height = margin_top + size * len(labels) + 30
    maximum = max(1, int(matrix.max()))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Arial, sans-serif">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="20" y="30" font-size="18" font-weight="bold">Confusion Matrix</text>',
    ]
    for index, label in enumerate(labels):
        y = margin_top + index * size + size * 0.7
        parts.append(
            f'<text x="{margin_left - 8}" y="{y:.0f}" font-size="9" text-anchor="end">{label[:34]}</text>'
        )
        x = margin_left + index * size + size * 0.5
        parts.append(
            f'<text x="{x:.0f}" y="{margin_top - 8}" font-size="9" text-anchor="start" '
            f'transform="rotate(-55 {x:.0f},{margin_top - 8})">{label[:34]}</text>'
        )
    for row_index in range(len(labels)):
        for col_index in range(len(labels)):
            value = int(matrix[row_index, col_index])
            intensity = value / maximum
            red = 255 - int(200 * intensity)
            green = 255 - int(80 * intensity)
            blue = 255 - int(80 * intensity)
            x = margin_left + col_index * size
            y = margin_top + row_index * size
            parts.append(
                f'<rect x="{x}" y="{y}" width="{size}" height="{size}" '
                f'fill="rgb({red},{green},{blue})" stroke="#dddddd" stroke-width="0.5"/>'
            )
            if value:
                parts.append(
                    f'<text x="{x + size / 2:.1f}" y="{y + size * 0.66:.1f}" font-size="8" '
                    f'text-anchor="middle" fill="{"#ffffff" if intensity > 0.55 else "#222222"}">{value}</text>'
                )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_metrics(
    docs_dir: Path,
    *,
    accuracy: float,
    macro_f1: float,
    report: dict,
    matrix: np.ndarray,
    labels: list[str],
    candidates: dict[str, float],
    samples: int,
    test_samples: int,
) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Classifier Metrics",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "Model: TF-IDF (char_wb 2-5 + word 1-2) with a classical scikit-learn estimator.",
        "No LLM or external AI API is used.",
        "",
        f"- Training samples: **{samples}**",
        f"- Held-out test samples: **{test_samples}**",
        f"- Accuracy: **{accuracy:.4f}**",
        f"- Macro F1: **{macro_f1:.4f}**",
        "",
        "## Candidate cross-validation accuracy",
        "",
        "| Candidate | CV accuracy |",
        "|---|---:|",
    ]
    for name, score in sorted(candidates.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"| {name} | {score:.4f} |")
    lines += [
        "",
        "## Per-class report",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in labels:
        metrics = report.get(label)
        if not isinstance(metrics, dict):
            continue
        lines.append(
            f"| {label} | {metrics.get('precision', 0):.3f} | {metrics.get('recall', 0):.3f} | "
            f"{metrics.get('f1-score', 0):.3f} | {int(metrics.get('support', 0))} |"
        )
    lines += [
        "",
        "## Confusion matrix",
        "",
        "Full matrix: `docs/confusion_matrix.csv`. Visual: `docs/confusion_matrix.svg`.",
        "",
        "| Actual \\ Predicted | " + " | ".join(label[:18] for label in labels) + " |",
        "|---|" + "---:|" * len(labels),
    ]
    for index, label in enumerate(labels):
        lines.append(
            f"| {label} | " + " | ".join(str(int(value)) for value in matrix[index]) + " |"
        )
    (docs_dir / "classifier_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(docs_dir / "confusion_matrix.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual\\predicted", *labels])
        for index, label in enumerate(labels):
            writer.writerow([label, *[int(value) for value in matrix[index]]])
    _confusion_svg(matrix, labels, docs_dir / "confusion_matrix.svg")


def train_model(
    csv_path: str | Path | None = None,
    model_path: str | Path | None = None,
    docs_dir: str | Path | None = None,
    *,
    with_overrides: bool = False,
    quick: bool = False,
) -> dict:
    csv_path = Path(csv_path or settings.training_csv)
    model_path = Path(model_path or settings.model_path)
    docs_dir = Path(docs_dir or settings.docs_dir)
    rows = _load_training_rows(csv_path, with_overrides)
    if len(rows) < 20:
        raise ValueError("not enough training rows (minimum 20)")

    texts = [
        build_feature_text(row["description"], row["direction"], row["amount"], row["channel"])
        for row in rows
    ]
    labels = [row["category"] for row in rows]
    counts = pd.Series(labels).value_counts()
    stratify = labels if counts.min() >= 2 else None
    test_size = 0.2 if len(rows) >= 100 else 0.25
    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=test_size, random_state=42, stratify=stratify
    )

    candidates_to_try = ["logreg"] if quick else ["logreg", "svm", "nb"]
    cv_scores: dict[str, float] = {}
    fitted: dict[str, object] = {}
    min_class_count = int(pd.Series(y_train).value_counts().min())
    cv_splits = min(3, min_class_count)
    if cv_splits >= 2:
        for name in candidates_to_try:
            pipeline = make_pipeline(name)
            try:
                scores = cross_val_score(
                    pipeline,
                    x_train,
                    y_train,
                    cv=StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42),
                    scoring="accuracy",
                    n_jobs=1,
                )
                cv_scores[name] = float(scores.mean())
                fitted[name] = pipeline.fit(x_train, y_train)
            except Exception as exc:
                logger.warning("candidate %s failed: %s", name, exc)
    if not cv_scores:
        pipeline = make_pipeline("logreg").fit(x_train, y_train)
        best_name = "logreg"
        cv_scores["logreg"] = 0.0
    else:
        best_name = max(cv_scores, key=cv_scores.get)
        pipeline = fitted[best_name]

    predictions = pipeline.predict(x_test)
    accuracy = float(accuracy_score(y_test, predictions))
    macro_f1 = float(f1_score(y_test, predictions, average="macro", zero_division=0))
    report = classification_report(y_test, predictions, output_dict=True, zero_division=0)
    all_labels = sorted(set(y_test) | set(predictions))
    matrix = confusion_matrix(y_test, predictions, labels=all_labels)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "pipeline": pipeline,
        "labels": list(pipeline.classes_),
        "metadata": {
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "samples": len(rows),
            "test_samples": len(y_test),
            "accuracy": round(accuracy, 4),
            "macro_f1": round(macro_f1, 4),
            "best_candidate": best_name,
            "candidates": {name: round(score, 4) for name, score in cv_scores.items()},
            "with_overrides": with_overrides,
            "features": "tfidf char_wb(2,5) + word(1,2) + channel/direction/amount tokens",
        },
    }
    joblib.dump(bundle, model_path)
    _write_metrics(
        docs_dir,
        accuracy=accuracy,
        macro_f1=macro_f1,
        report=report,
        matrix=matrix,
        labels=all_labels,
        candidates=cv_scores,
        samples=len(rows),
        test_samples=len(y_test),
    )

    # Persist an augmented training file when overrides were used.
    if with_overrides:
        augmented = csv_path.with_name("transactions_labeled_augmented.csv")
        pd.DataFrame(
            [
                {
                    "description": row["description"],
                    "category": row["category"],
                    "direction": row["direction"],
                    "amount": str(row["amount"]) if row["amount"] is not None else "",
                    "channel": row["channel"] or "",
                }
                for row in rows
            ]
        ).to_csv(augmented, index=False)

    from app.classification.ml_model import invalidate_cache

    invalidate_cache()
    result = {
        "status": "trained",
        "samples": len(rows),
        "test_samples": len(y_test),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "best_candidate": best_name,
        "candidates": {name: round(score, 4) for name, score in cv_scores.items()},
        "model_path": str(model_path),
        "metrics_path": str(docs_dir / "classifier_metrics.md"),
    }
    logger.info("trained classifier: %s", json.dumps(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the bank-statement classifier (classical ML only).")
    parser.add_argument("--csv", default=None, help="Training CSV path")
    parser.add_argument("--model", default=None, help="Output joblib path")
    parser.add_argument("--docs", default=None, help="Metrics output directory")
    parser.add_argument("--with-overrides", action="store_true", help="Include user overrides from SQLite")
    parser.add_argument("--quick", action="store_true", help="Train only Logistic Regression (fast)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    result = train_model(
        args.csv,
        args.model,
        args.docs,
        with_overrides=args.with_overrides,
        quick=args.quick,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

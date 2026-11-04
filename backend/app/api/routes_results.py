"""Results, transaction editing, summary and learning-loop endpoints."""
from __future__ import annotations

import logging
import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.serializers import (
    build_summary,
    filter_transactions,
    job_to_out,
    transaction_to_out,
)
from app.classification.classifier import load_overrides, similarity
from app.classification.preprocess_text import normalize_for_override
from app.classification.taxonomy import is_valid_category
from app.db import get_db
from app.models.db_models import StatementJob, TransactionRecord, UserOverride
from app.models.schemas import (
    CategoryPatchIn,
    CategoryPatchOut,
    StatementOut,
    StatementSummary,
    TransactionPage,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["results"])


def _get_job(db: Session, statement_id: str) -> StatementJob:
    job = db.get(StatementJob, statement_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "STATEMENT_NOT_FOUND", "message": "Statement not found."},
        )
    return job


def _all_transactions(db: Session, statement_id: str) -> list[TransactionRecord]:
    return (
        db.query(TransactionRecord)
        .filter(TransactionRecord.statement_id == statement_id)
        .order_by(TransactionRecord.txn_date, TransactionRecord.sort_index)
        .all()
    )


@router.get("/statements/{statement_id}", response_model=StatementOut)
def get_statement(statement_id: str, db: Session = Depends(get_db)) -> StatementOut:
    return job_to_out(_get_job(db, statement_id))


@router.get("/statements/{statement_id}/transactions", response_model=TransactionPage)
def get_transactions(
    statement_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    txn_type: str | None = Query(None, alias="type"),
    search: str | None = None,
    flagged_only: bool = False,
    sort: str = Query("date_asc", pattern="^(date_asc|date_desc|amount_asc|amount_desc)$"),
    db: Session = Depends(get_db),
) -> TransactionPage:
    _get_job(db, statement_id)
    transactions = filter_transactions(
        _all_transactions(db, statement_id),
        date_from=date_from,
        date_to=date_to,
        category=category,
        txn_type=txn_type,
        search=search,
        flagged_only=flagged_only,
        sort=sort,
    )
    total = len(transactions)
    pages = max(1, math.ceil(total / page_size))
    start = (page - 1) * page_size
    items = transactions[start : start + page_size]
    total_debit = sum((txn.debit or 0 for txn in transactions), start=0)
    total_credit = sum((txn.credit or 0 for txn in transactions), start=0)
    return TransactionPage(
        items=[transaction_to_out(txn) for txn in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        total_debit=float(total_debit),
        total_credit=float(total_credit),
    )


@router.patch("/transactions/{transaction_id}", response_model=CategoryPatchOut)
def patch_transaction(
    transaction_id: int,
    payload: CategoryPatchIn,
    db: Session = Depends(get_db),
) -> CategoryPatchOut:
    transaction = db.get(TransactionRecord, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "TRANSACTION_NOT_FOUND", "message": "Transaction not found."},
        )
    if not is_valid_category(payload.category):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_CATEGORY",
                "message": f"Unknown category: {payload.category}",
            },
        )

    normalized = normalize_for_override(transaction.description) or transaction.description.upper()[:500]
    override = (
        db.query(UserOverride)
        .filter(UserOverride.normalized_pattern == normalized)
        .first()
    )
    if override is None:
        override = UserOverride(
            statement_id=transaction.statement_id,
            description_pattern=transaction.description,
            normalized_pattern=normalized,
            category=payload.category,
            hits=1,
        )
        db.add(override)
    else:
        override.category = payload.category
        override.description_pattern = transaction.description
        override.hits = (override.hits or 0) + 1

    updated = 1
    transaction.category = payload.category
    transaction.category_source = "user"
    transaction.category_confidence = 0.99
    transaction.reason = "user corrected category"
    transaction.flags = [flag for flag in (transaction.flags or []) if flag != "uncategorized"]

    if payload.apply_to_similar:
        siblings = (
            db.query(TransactionRecord)
            .filter(
                TransactionRecord.statement_id == transaction.statement_id,
                TransactionRecord.id != transaction.id,
            )
            .all()
        )
        for sibling in siblings:
            sibling_normalized = normalize_for_override(sibling.description)
            if sibling_normalized == normalized or similarity(sibling.description, transaction.description) >= 85:
                sibling.category = payload.category
                sibling.category_source = "user"
                sibling.category_confidence = 0.99
                sibling.reason = "user corrected a similar transaction"
                sibling.flags = [flag for flag in (sibling.flags or []) if flag != "uncategorized"]
                updated += 1

    db.commit()
    db.refresh(transaction)
    return CategoryPatchOut(
        transaction=transaction_to_out(transaction),
        updated_count=updated,
        override_saved=True,
    )


@router.get("/statements/{statement_id}/summary", response_model=StatementSummary)
def get_summary(statement_id: str, db: Session = Depends(get_db)) -> StatementSummary:
    job = _get_job(db, statement_id)
    return build_summary(job, _all_transactions(db, statement_id))


@router.get("/statements/{statement_id}/overrides")
def get_statement_overrides(statement_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_job(db, statement_id)
    overrides = load_overrides(db)
    return [
        {"pattern": item.pattern, "normalized": item.normalized, "category": item.category}
        for item in overrides
    ]

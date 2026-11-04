"""CSV/XLSX download endpoints, including merged multi-statement exports."""
from __future__ import annotations

import logging
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.serializers import filter_transactions
from app.config import settings
from app.db import get_db
from app.export.csv_exporter import write_csv
from app.export.xlsx_exporter import export_xlsx
from app.models.db_models import StatementJob, TransactionRecord

logger = logging.getLogger(__name__)
router = APIRouter(tags=["export"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MEDIA = "text/csv; charset=utf-8"


def _cleanup(path: Path) -> None:
    path.unlink(missing_ok=True)


def _statement_transactions(
    db: Session,
    statement_id: str,
    *,
    date_from: date | None,
    date_to: date | None,
    category: str | None,
    txn_type: str | None,
    search: str | None,
    flagged_only: bool,
    sort: str,
) -> list[TransactionRecord]:
    transactions = (
        db.query(TransactionRecord)
        .filter(TransactionRecord.statement_id == statement_id)
        .order_by(TransactionRecord.txn_date, TransactionRecord.sort_index)
        .all()
    )
    return filter_transactions(
        transactions,
        date_from=date_from,
        date_to=date_to,
        category=category,
        txn_type=txn_type,
        search=search,
        flagged_only=flagged_only,
        sort=sort,
    )


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "statement"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)[:80]


@router.get("/statements/{statement_id}/export")
def export_statement(
    statement_id: str,
    background: BackgroundTasks,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    txn_type: str | None = Query(None, alias="type"),
    search: str | None = None,
    flagged_only: bool = False,
    sort: str = Query("date_asc", pattern="^(date_asc|date_desc|amount_asc|amount_desc)$"),
    db: Session = Depends(get_db),
) -> FileResponse:
    job = db.get(StatementJob, statement_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "STATEMENT_NOT_FOUND", "message": "Statement not found."},
        )
    transactions = _statement_transactions(
        db,
        statement_id,
        date_from=date_from,
        date_to=date_to,
        category=category,
        txn_type=txn_type,
        search=search,
        flagged_only=flagged_only,
        sort=sort,
    )
    if not transactions:
        raise HTTPException(
            status_code=404,
            detail={"code": "NO_TRANSACTIONS_FOUND", "message": "No transactions match the filters."},
        )
    suffix = ".xlsx" if format == "xlsx" else ".csv"
    output = settings.upload_dir / f"export_{uuid.uuid4().hex}{suffix}"
    if format == "xlsx":
        export_xlsx(job, transactions, output)
    else:
        write_csv(transactions, output)
    background.add_task(_cleanup, output)
    filename = f"{_safe_stem(job.filename)}_transactions{suffix}"
    return FileResponse(
        path=output,
        media_type=XLSX_MEDIA if format == "xlsx" else CSV_MEDIA,
        filename=filename,
    )


@router.get("/merge/export")
def export_merged(
    background: BackgroundTasks,
    ids: str = Query(..., description="Comma-separated statement IDs"),
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    db: Session = Depends(get_db),
) -> FileResponse:
    ordered_ids = [item.strip() for item in ids.split(",") if item.strip()]
    if not ordered_ids:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_IDS", "message": "Provide at least one statement ID."},
        )
    jobs = db.query(StatementJob).filter(StatementJob.id.in_(ordered_ids)).all()
    by_id = {job.id: job for job in jobs}
    missing = [item for item in ordered_ids if item not in by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "STATEMENT_NOT_FOUND",
                "message": f"Statement(s) not found: {', '.join(missing)}",
            },
        )
    ordered_jobs = [by_id[item] for item in ordered_ids]
    combined: list[TransactionRecord] = []
    statement_names: dict[str, str] = {}
    for job in ordered_jobs:
        statement_names[job.id] = job.filename
        combined.extend(
            db.query(TransactionRecord)
            .filter(TransactionRecord.statement_id == job.id)
            .order_by(TransactionRecord.txn_date, TransactionRecord.sort_index)
            .all()
        )
    if not combined:
        raise HTTPException(
            status_code=404,
            detail={"code": "NO_TRANSACTIONS_FOUND", "message": "No transactions to export."},
        )
    suffix = ".xlsx" if format == "xlsx" else ".csv"
    output = settings.upload_dir / f"merged_{uuid.uuid4().hex}{suffix}"
    if format == "xlsx":
        export_xlsx(ordered_jobs[0], combined, output, merged_jobs=ordered_jobs)
    else:
        write_csv(
            combined,
            output,
            include_statement=True,
            statement_names=statement_names,
        )
    background.add_task(_cleanup, output)
    return FileResponse(
        path=output,
        media_type=XLSX_MEDIA if format == "xlsx" else CSV_MEDIA,
        filename=f"merged_statements{suffix}",
    )

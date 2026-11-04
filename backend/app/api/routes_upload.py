"""Statement upload and history endpoints."""
from __future__ import annotations

import gc
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.serializers import job_to_out
from app.config import settings
from app.core.errors import FileTooLargeError, InvalidFileError, PipelineError
from app.core.pipeline import process_statement
from app.db import get_db
from app.models.db_models import StatementJob
from app.models.schemas import StatementListItem, StatementOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["statements"])


@router.post(
    "/statements",
    response_model=StatementOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a bank statement PDF",
)
async def upload_statement(
    file: UploadFile = File(...),
    password: str | None = Form(None),
    db: Session = Depends(get_db),
) -> StatementOut:
    filename = file.filename or "statement.pdf"
    if not filename.lower().endswith(".pdf"):
        raise InvalidFileError("Only PDF files are accepted (missing .pdf extension).")
    if file.content_type and file.content_type not in {
        "application/pdf",
        "application/octet-stream",
        "binary/octet-stream",
    }:
        raise InvalidFileError(f"Unsupported content type: {file.content_type}.")

    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > settings.max_file_size:
            raise FileTooLargeError(
                f"File is larger than {settings.max_file_size // (1024 * 1024)} MB."
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise InvalidFileError("The uploaded file is empty.")
    if not data.startswith(b"%PDF"):
        raise InvalidFileError("The file does not have a valid PDF signature (%PDF).")

    temp_path = settings.upload_dir / f"{uuid.uuid4().hex}.pdf"
    temp_path.write_bytes(data)
    try:
        processed = process_statement(
            temp_path,
            filename,
            db,
            password=password or None,
        )
    except PipelineError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("statement processing failed for %s", filename)
        raise PipelineError(
            "PROCESSING_FAILED",
            "The statement could not be processed. Check the file and try again.",
            500,
        ) from exc
    finally:
        if settings.delete_uploads_after_processing:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError as exc:
                # Windows keeps a handle briefly when a PDF parser rejected the file.
                logger.warning("could not delete temporary upload %s: %s", temp_path, exc)
                gc.collect()
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    logger.warning("temporary upload left on disk: %s", temp_path)

    job = db.get(StatementJob, processed.job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Statement was processed but not persisted.")
    return job_to_out(job)


@router.get("/statements", response_model=list[StatementListItem], summary="Statement history")
def list_statements(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[StatementListItem]:
    jobs = (
        db.query(StatementJob)
        .order_by(StatementJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        StatementListItem(
            id=job.id,
            filename=job.filename,
            status=job.status,
            pdf_type=job.pdf_type,
            bank_detected=job.bank_detected,
            num_pages=job.num_pages,
            extraction_confidence=job.extraction_confidence,
            transaction_count=int((job.stats or {}).get("transaction_count", 0)),
            created_at=job.created_at,
        )
        for job in jobs
    ]


@router.delete("/statements/{statement_id}", status_code=204, summary="Delete a statement")
def delete_statement(statement_id: str, db: Session = Depends(get_db)) -> None:
    job = db.get(StatementJob, statement_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Statement not found.")
    db.delete(job)
    db.commit()

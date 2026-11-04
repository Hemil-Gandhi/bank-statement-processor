"""End-to-end pipeline tests for OCR (IMAGE) and mixed text/image statements."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.ocr_extractor import ocr_available
from app.core.pipeline import process_statement
from app.models.db_models import Base


@pytest.fixture()
def session(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'pipeline.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_scanned_pdf_uses_ocr_and_reconciles(session, samples_dir: Path) -> None:
    if not ocr_available():
        pytest.skip("Tesseract is not installed")
    pdf = samples_dir / "scanned_statement.pdf"
    result = process_statement(pdf, pdf.name, session)

    assert result.detection.pdf_type == "IMAGE"
    assert result.detection.per_page_types == ["IMAGE"]
    assert len(result.transactions) == 8
    assert result.validation.reconciled_rows == 8
    assert result.validation.closing_reconciled is True
    assert result.account.account_holder_name == "SAMPLE CUSTOMER"
    assert result.account.ifsc == "SBIN0001234"
    # The OCR layer must not duplicate the value date into the narration.
    assert all("01/04/2024 01/04/2024" not in txn.description for txn in result.transactions)
    assert any("ocr_path_used" in warning for warning in result.warnings)


def test_mixed_pdf_uses_per_page_detection(session, samples_dir: Path) -> None:
    if not ocr_available():
        pytest.skip("Tesseract is not installed")
    pdf = samples_dir / "mixed_statement.pdf"
    result = process_statement(pdf, pdf.name, session)

    assert result.detection.pdf_type == "MIXED"
    assert result.detection.per_page_types == ["TEXT", "IMAGE"]
    assert len(result.transactions) == 36
    assert result.validation.reconciled_rows == 36
    assert result.validation.closing_reconciled is True
    assert {txn.page for txn in result.transactions} == {1, 2}


def test_text_statement_is_classified_and_persisted(session, sbi_pdf: Path) -> None:
    result = process_statement(sbi_pdf, sbi_pdf.name, session)

    assert result.detection.pdf_type == "TEXT"
    assert len(result.transactions) == 36
    assert result.validation.closing_reconciled is True
    assert result.account.opening_balance is not None
    assert result.account.closing_balance is not None

    categories = {txn.category for txn in result.transactions}
    assert "Salary/Income" in categories
    assert "Cash Withdrawal (ATM)" in categories
    assert "Uncategorized" not in categories
    assert any(txn.recurring for txn in result.transactions)

    from app.models.db_models import StatementJob, TransactionRecord

    job = session.get(StatementJob, result.job_id)
    assert job is not None
    assert job.stats["transaction_count"] == 36
    assert session.query(TransactionRecord).filter_by(statement_id=result.job_id).count() == 36

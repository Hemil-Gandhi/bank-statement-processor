"""Generate sample CSV/XLSX exports from the generated fixture statements.

Run from the project root:
    .venv/Scripts/python scripts/generate_sample_exports.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.pipeline import process_statement  # noqa: E402
from app.export.csv_exporter import write_csv  # noqa: E402
from app.export.xlsx_exporter import export_xlsx  # noqa: E402
from app.models.db_models import Base, StatementJob, TransactionRecord  # noqa: E402


def _records(session, job_id: str) -> list[TransactionRecord]:
    return (
        session.query(TransactionRecord)
        .filter(TransactionRecord.statement_id == job_id)
        .order_by(TransactionRecord.txn_date, TransactionRecord.sort_index)
        .all()
    )


def main() -> None:
    samples = PROJECT / "samples"
    output = samples / "exports"
    output.mkdir(parents=True, exist_ok=True)

    db_path = Path(tempfile.gettempdir()) / "bsp_sample_exports.db"
    db_path.unlink(missing_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        jobs: list[StatementJob] = []
        for filename in ("sbi_statement.pdf", "hdfc_statement.pdf"):
            path = samples / filename
            processed = process_statement(path, filename, session)
            job = session.get(StatementJob, processed.job_id)
            assert job is not None
            jobs.append(job)

            transactions = _records(session, job.id)
            stem = Path(filename).stem.replace("_statement", "")
            export_xlsx(job, transactions, output / f"{stem}_transactions.xlsx")
            write_csv(transactions, output / f"{stem}_transactions.csv")
            print(f"{filename}: {len(transactions)} rows -> {stem}_transactions.xlsx/.csv")

        combined = [txn for job in jobs for txn in _records(session, job.id)]
        names = {job.id: job.filename for job in jobs}
        export_xlsx(jobs[0], combined, output / "merged_transactions.xlsx", merged_jobs=jobs)
        write_csv(
            combined,
            output / "merged_transactions.csv",
            include_statement=True,
            statement_names=names,
        )
        print(f"merged: {len(combined)} rows -> merged_transactions.xlsx/.csv")
    finally:
        session.close()
        engine.dispose()
        db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

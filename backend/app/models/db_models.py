"""SQLAlchemy models: jobs, transactions and the user-override learning memory."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class StatementJob(Base):
    __tablename__ = "statement_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    pdf_type: Mapped[str] = mapped_column(String(16), default="TEXT")
    per_page_types: Mapped[list] = mapped_column(JSON, default=list)
    bank_detected: Mapped[str | None] = mapped_column(String(128))
    bank_profile: Mapped[str | None] = mapped_column(String(64))
    num_pages: Mapped[int] = mapped_column(Integer, default=0)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    account_details: Mapped[dict] = mapped_column(JSON, default=dict)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    password_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    transactions: Mapped[list["TransactionRecord"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan"
    )


class TransactionRecord(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    statement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("statement_jobs.id", ondelete="CASCADE"), index=True
    )
    page: Mapped[int] = mapped_column(Integer, default=1)
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    value_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    raw_description: Mapped[str] = mapped_column(Text, default="")
    reference_no: Mapped[str | None] = mapped_column(String(128))
    debit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    credit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    category: Mapped[str] = mapped_column(String(64), default="Uncategorized", index=True)
    category_source: Mapped[str] = mapped_column(String(16), default="fallback")
    category_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    flags: Mapped[list] = mapped_column(JSON, default=list)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    statement: Mapped[StatementJob] = relationship(back_populates="transactions")


class UserOverride(Base):
    __tablename__ = "user_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    statement_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description_pattern: Mapped[str] = mapped_column(Text)
    normalized_pattern: Mapped[str] = mapped_column(String(512), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

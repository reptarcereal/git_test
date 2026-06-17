"""SQLAlchemy ORM models for persisted Starlink usage data."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ServiceLine(Base):
    """One Starlink service line (terminal/subscription) on the account."""

    __tablename__ = "service_lines"

    service_line_number: Mapped[str] = mapped_column(String, primary_key=True)
    nickname: Mapped[str | None] = mapped_column(String, nullable=True)
    account_number: Mapped[str | None] = mapped_column(String, nullable=True)
    service_plan: Mapped[str | None] = mapped_column(String, nullable=True)
    # Customer this unit belongs to, resolved from the Spot.ai mapping.
    customer: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BillingCycleUsage(Base):
    """Usage for one service line in one billing cycle.

    One row per (service_line_number, cycle_key); upserted on each poll. Keeping
    every cycle gives accounting a full month-by-month history to verify
    overages, while the dashboard reads the most recent cycle by default.
    """

    __tablename__ = "billing_cycle_usage"
    __table_args__ = (
        UniqueConstraint("service_line_number", "cycle_key", name="uq_line_cycle"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_line_number: Mapped[str] = mapped_column(String, index=True)

    # Stable identifier for the cycle (cycle end date, YYYY-MM-DD) used for
    # grouping, the month picker, and the unique constraint.
    cycle_key: Mapped[str] = mapped_column(String, index=True)
    cycle_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cycle_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Core usage figures (in GB). "priority" data is what counts against the cap.
    included_gb: Mapped[float] = mapped_column(Float, default=0.0)
    priority_used_gb: Mapped[float] = mapped_column(Float, default=0.0)
    standard_used_gb: Mapped[float] = mapped_column(Float, default=0.0)

    # Derived at write time so the dashboard reads are trivial.
    overage_gb: Mapped[float] = mapped_column(Float, default=0.0)
    used_pct: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="ok")  # ok|warning|over
    estimated_overage_cost: Mapped[float] = mapped_column(Float, default=0.0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PollRun(Base):
    """Metadata about each polling run for observability."""

    __tablename__ = "poll_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lines_processed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="running")  # running|ok|error
    error: Mapped[str | None] = mapped_column(String, nullable=True)

"""SQLAlchemy ORM models for persisted Starlink usage data."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
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
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UsageSnapshot(Base):
    """A point-in-time reading of a service line's billing-cycle usage.

    One row is written per service line per poll, giving a history we can chart
    and from which we always read the latest per line for the dashboard.
    """

    __tablename__ = "usage_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_line_number: Mapped[str] = mapped_column(String, index=True)

    # Billing cycle window the usage applies to.
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

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
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

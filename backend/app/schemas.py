"""Pydantic response models for the dashboard API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, PlainSerializer


def _as_utc_iso(value: datetime) -> str:
    """Serialize datetimes as UTC ISO strings with an explicit offset.

    SQLite returns naive datetimes (func.now() is UTC but carries no tzinfo).
    Without an offset, the browser parses them as local time and the converted
    Arizona time comes out wrong, so we attach UTC for naive values.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


# datetime that always serializes with a UTC offset.
UtcDateTime = Annotated[
    datetime, PlainSerializer(_as_utc_iso, return_type=str, when_used="json")
]


class ServiceLineUsage(BaseModel):
    service_line_number: str
    nickname: str | None
    service_plan: str | None
    account_number: str | None
    cycle_start: UtcDateTime | None
    cycle_end: UtcDateTime | None
    included_gb: float
    priority_used_gb: float
    standard_used_gb: float
    overage_gb: float
    used_pct: float
    status: str
    estimated_overage_cost: float
    captured_at: UtcDateTime | None


class Summary(BaseModel):
    total_lines: int
    lines_ok: int
    lines_warning: int
    lines_over: int
    total_overage_gb: float
    estimated_overage_cost: float
    last_updated: UtcDateTime | None
    mock_mode: bool


class PollRunInfo(BaseModel):
    id: int
    started_at: UtcDateTime
    finished_at: UtcDateTime | None
    lines_processed: int
    status: str
    error: str | None

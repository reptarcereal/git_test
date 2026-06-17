"""Pydantic response models for the dashboard API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ServiceLineUsage(BaseModel):
    service_line_number: str
    nickname: str | None
    service_plan: str | None
    account_number: str | None
    cycle_start: datetime | None
    cycle_end: datetime | None
    included_gb: float
    priority_used_gb: float
    standard_used_gb: float
    overage_gb: float
    used_pct: float
    status: str
    estimated_overage_cost: float
    captured_at: datetime | None


class Summary(BaseModel):
    total_lines: int
    lines_ok: int
    lines_warning: int
    lines_over: int
    total_overage_gb: float
    estimated_overage_cost: float
    last_updated: datetime | None
    mock_mode: bool


class PollRunInfo(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    lines_processed: int
    status: str
    error: str | None

"""Normalized usage records and overage computation.

Both the live Starlink client and the mock generator produce ``UsageRecord``
objects, so the overage math lives in exactly one place.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import Settings

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_OVER = "over"


@dataclass
class UsageRecord:
    """Source-agnostic view of a service line's current billing-cycle usage."""

    service_line_number: str
    nickname: str | None = None
    customer: str | None = None
    account_number: str | None = None
    service_plan: str | None = None
    cycle_start: datetime | None = None
    cycle_end: datetime | None = None
    included_gb: float = 0.0
    priority_used_gb: float = 0.0
    standard_used_gb: float = 0.0


@dataclass
class OverageResult:
    overage_gb: float
    used_pct: float
    status: str
    estimated_overage_cost: float


def compute_overage(record: UsageRecord, settings: Settings) -> OverageResult:
    """Derive overage figures from a usage record.

    Only *priority* (included-allotment) data counts against the cap. A line
    with a zero/unknown allotment is treated as uncapped and never "over".
    """
    included = max(record.included_gb, 0.0)
    used = max(record.priority_used_gb, 0.0)

    overage_gb = max(0.0, used - included) if included > 0 else 0.0
    used_pct = (used / included * 100.0) if included > 0 else 0.0
    cost = round(overage_gb * settings.overage_cost_per_gb, 2)

    if overage_gb > 0:
        status = STATUS_OVER
    elif included > 0 and used_pct >= settings.warning_threshold_pct:
        status = STATUS_WARNING
    else:
        status = STATUS_OK

    return OverageResult(
        overage_gb=round(overage_gb, 3),
        used_pct=round(used_pct, 1),
        status=status,
        estimated_overage_cost=cost,
    )

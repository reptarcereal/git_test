"""FastAPI application: dashboard REST API + static frontend serving."""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_session, init_db
from .models import BillingCycleUsage, PollRun, ServiceLine
from .overage import STATUS_OVER, STATUS_WARNING
from .poller import poll_loop, run_poll
from .schemas import CycleInfo, PollRunInfo, ServiceLineUsage, Summary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Arizona is MST year-round (no DST), so a fixed UTC-7 offset is always
# correct and avoids needing the tzdata package (absent on Windows).
_AZ = timezone(timedelta(hours=-7), "MST")
_stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    task = asyncio.create_task(poll_loop(_stop_event))
    try:
        yield
    finally:
        _stop_event.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


app = FastAPI(title="Starlink Overage Dashboard", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _rows_for_cycle(session: Session, cycle: str | None):
    """Return (usage, service_line) pairs for a given cycle.

    When ``cycle`` is None, use the most recent cycle per line (cycle_key is a
    YYYY-MM-DD string, so lexicographic max == newest).
    """
    if cycle:
        stmt = (
            select(BillingCycleUsage, ServiceLine)
            .where(BillingCycleUsage.cycle_key == cycle)
            .join(
                ServiceLine,
                ServiceLine.service_line_number
                == BillingCycleUsage.service_line_number,
                isouter=True,
            )
        )
        return session.execute(stmt).all()

    latest = (
        select(
            BillingCycleUsage.service_line_number,
            func.max(BillingCycleUsage.cycle_key).label("max_key"),
        )
        .group_by(BillingCycleUsage.service_line_number)
        .subquery()
    )
    stmt = (
        select(BillingCycleUsage, ServiceLine)
        .join(
            latest,
            (BillingCycleUsage.service_line_number == latest.c.service_line_number)
            & (BillingCycleUsage.cycle_key == latest.c.max_key),
        )
        .join(
            ServiceLine,
            ServiceLine.service_line_number == BillingCycleUsage.service_line_number,
            isouter=True,
        )
    )
    return session.execute(stmt).all()


def _to_usage(row: BillingCycleUsage, line: ServiceLine | None) -> ServiceLineUsage:
    return ServiceLineUsage(
        service_line_number=row.service_line_number,
        nickname=line.nickname if line else None,
        customer=line.customer if line else None,
        service_plan=line.service_plan if line else None,
        account_number=line.account_number if line else None,
        cycle_start=row.cycle_start,
        cycle_end=row.cycle_end,
        included_gb=row.included_gb,
        priority_used_gb=row.priority_used_gb,
        standard_used_gb=row.standard_used_gb,
        overage_gb=row.overage_gb,
        used_pct=row.used_pct,
        status=row.status,
        estimated_overage_cost=row.estimated_overage_cost,
        captured_at=row.updated_at,
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _cycle_label(key: str) -> str:
    """Human label for a cycle key (YYYY-MM-DD end date) -> 'Mon D, YYYY'."""
    try:
        return datetime.strptime(key, "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return key


@app.get("/api/cycles", response_model=list[CycleInfo])
def cycles(session: Session = Depends(get_session)) -> list[CycleInfo]:
    """Distinct billing cycles available, newest first, for the month picker."""
    keys = session.execute(
        select(BillingCycleUsage.cycle_key)
        .distinct()
        .order_by(BillingCycleUsage.cycle_key.desc())
    ).scalars().all()
    return [CycleInfo(cycle=k, label=_cycle_label(k)) for k in keys]


@app.get("/api/summary", response_model=Summary)
def summary(
    cycle: str | None = None, session: Session = Depends(get_session)
) -> Summary:
    rows = _rows_for_cycle(session, cycle)
    snaps = [snap for snap, _ in rows]
    last_updated = max((s.updated_at for s in snaps), default=None)
    key = cycle or (snaps[0].cycle_key if snaps else None)
    return Summary(
        total_lines=len(snaps),
        lines_ok=sum(1 for s in snaps if s.status == "ok"),
        lines_warning=sum(1 for s in snaps if s.status == STATUS_WARNING),
        lines_over=sum(1 for s in snaps if s.status == STATUS_OVER),
        total_overage_gb=round(sum(s.overage_gb for s in snaps), 2),
        estimated_overage_cost=round(
            sum(s.estimated_overage_cost for s in snaps), 2
        ),
        last_updated=last_updated,
        cycle=key,
        cycle_label=_cycle_label(key) if key else None,
        mock_mode=get_settings().effective_mock_mode,
    )


def _filtered_lines(
    session: Session, status: str | None, search: str | None, cycle: str | None
) -> list[ServiceLineUsage]:
    items = [_to_usage(snap, line) for snap, line in _rows_for_cycle(session, cycle)]
    if status:
        items = [i for i in items if i.status == status]
    if search:
        q = search.lower()
        items = [
            i
            for i in items
            if q in (i.nickname or "").lower()
            or q in i.service_line_number.lower()
            or q in (i.customer or "").lower()
        ]
    # Worst offenders first.
    items.sort(key=lambda i: (i.overage_gb, i.used_pct), reverse=True)
    return items


@app.get("/api/service-lines", response_model=list[ServiceLineUsage])
def service_lines(
    status: str | None = Query(None, pattern="^(ok|warning|over)$"),
    search: str | None = None,
    cycle: str | None = None,
    session: Session = Depends(get_session),
) -> list[ServiceLineUsage]:
    return _filtered_lines(session, status, search, cycle)


@app.get("/api/service-lines.csv")
def service_lines_csv(
    status: str | None = Query(None, pattern="^(ok|warning|over)$"),
    search: str | None = None,
    cycle: str | None = None,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Export the (filtered) service-line table as CSV — opens in Excel."""
    items = _filtered_lines(session, status, search, cycle)

    def _date(value: datetime | None) -> str:
        # Arizona (MST, no DST) date to match the dashboard.
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(_AZ).strftime("%Y-%m-%d")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Service Line",
            "Nickname",
            "Customer",
            "Plan",
            "Account",
            "Priority Used (GB)",
            "Included (GB)",
            "Standard Used (GB)",
            "Utilization (%)",
            "Overage (GB)",
            "Est. Cost ($)",
            "Status",
            "Cycle Start",
            "Cycle End",
        ]
    )
    for i in items:
        writer.writerow(
            [
                i.service_line_number,
                i.nickname or "",
                i.customer or "",
                i.service_plan or "",
                i.account_number or "",
                i.priority_used_gb,
                i.included_gb,
                i.standard_used_gb,
                i.used_pct,
                i.overage_gb,
                i.estimated_overage_cost,
                i.status,
                _date(i.cycle_start),
                _date(i.cycle_end),
            ]
        )
    buffer.seek(0)
    tag = cycle or datetime.now(_AZ).strftime("%Y%m%d")
    filename = f"starlink-overages-{tag}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/overages", response_model=list[ServiceLineUsage])
def overages(
    cycle: str | None = None, session: Session = Depends(get_session)
) -> list[ServiceLineUsage]:
    items = [_to_usage(snap, line) for snap, line in _rows_for_cycle(session, cycle)]
    items = [i for i in items if i.status in (STATUS_WARNING, STATUS_OVER)]
    items.sort(key=lambda i: (i.overage_gb, i.used_pct), reverse=True)
    return items


@app.post("/api/refresh", response_model=PollRunInfo)
def refresh(
    background: BackgroundTasks, session: Session = Depends(get_session)
) -> PollRunInfo:
    """Trigger an immediate poll in the background and return run metadata."""
    run = run_poll(get_settings())
    return PollRunInfo(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        lines_processed=run.lines_processed,
        status=run.status,
        error=run.error,
    )


@app.get("/api/poll-runs", response_model=list[PollRunInfo])
def poll_runs(session: Session = Depends(get_session)) -> list[PollRunInfo]:
    stmt = select(PollRun).order_by(PollRun.started_at.desc()).limit(20)
    return [
        PollRunInfo(
            id=r.id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            lines_processed=r.lines_processed,
            status=r.status,
            error=r.error,
        )
        for r in session.execute(stmt).scalars()
    ]


# Serve the built React app if present (frontend/dist). Mounted last so it does
# not shadow the /api routes.
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="ui")

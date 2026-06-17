"""Scheduled polling: fetch usage, compute overages, persist snapshots."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from .config import Settings, get_settings
from .db import SessionLocal
from .mock_data import generate_usage_records
from .models import PollRun, ServiceLine, UsageSnapshot
from .overage import UsageRecord, compute_overage
from .starlink_client import StarlinkClient

logger = logging.getLogger(__name__)


def _collect_records(settings: Settings) -> list[UsageRecord]:
    if settings.effective_mock_mode:
        logger.info("Polling in MOCK mode (no Starlink credentials in use).")
        return generate_usage_records()
    with StarlinkClient(settings) as client:
        return client.fetch_all_usage()


def run_poll(settings: Settings | None = None) -> PollRun:
    """Execute one full polling pass synchronously. Returns the PollRun row."""
    settings = settings or get_settings()
    session = SessionLocal()
    run = PollRun(started_at=datetime.now(timezone.utc), status="running")
    session.add(run)
    session.commit()

    try:
        records = _collect_records(settings)
        for rec in records:
            result = compute_overage(rec, settings)

            existing = session.get(ServiceLine, rec.service_line_number)
            if existing is None:
                session.add(
                    ServiceLine(
                        service_line_number=rec.service_line_number,
                        nickname=rec.nickname,
                        account_number=rec.account_number,
                        service_plan=rec.service_plan,
                        active=True,
                    )
                )
            else:
                existing.nickname = rec.nickname
                existing.service_plan = rec.service_plan
                existing.account_number = rec.account_number

            session.add(
                UsageSnapshot(
                    service_line_number=rec.service_line_number,
                    cycle_start=rec.cycle_start,
                    cycle_end=rec.cycle_end,
                    included_gb=rec.included_gb,
                    priority_used_gb=rec.priority_used_gb,
                    standard_used_gb=rec.standard_used_gb,
                    overage_gb=result.overage_gb,
                    used_pct=result.used_pct,
                    status=result.status,
                    estimated_overage_cost=result.estimated_overage_cost,
                )
            )

        run.lines_processed = len(records)
        run.status = "ok"
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("Poll complete: %d service lines processed.", len(records))
    except Exception as exc:  # noqa: BLE001 — record failure, don't crash loop
        session.rollback()
        run = session.get(PollRun, run.id) or run
        run.status = "error"
        run.error = str(exc)[:1000]
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        logger.exception("Poll failed.")
    finally:
        session.close()
    return run


async def poll_loop(stop_event: asyncio.Event) -> None:
    """Run ``run_poll`` on the configured interval until ``stop_event`` is set."""
    settings = get_settings()
    if settings.poll_on_startup:
        await asyncio.to_thread(run_poll, settings)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.poll_interval_seconds
            )
        except asyncio.TimeoutError:
            await asyncio.to_thread(run_poll, settings)

"""Scheduled polling: fetch usage, compute overages, persist snapshots."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from .config import Settings, get_settings
from .db import SessionLocal
from .mock_data import generate_usage_records
from .models import BillingCycleUsage, PollRun, ServiceLine
from .overage import UsageRecord, compute_overage
from .spotai_client import build_customer_map
from .starlink_client import StarlinkClient

logger = logging.getLogger(__name__)


def _resolve_customers(settings: Settings, records: list[UsageRecord]) -> dict[str, str]:
    """Map service_line_number -> customer.

    Mock data carries its own customer; live data resolves nicknames against the
    Spot.ai location->customer map.
    """
    spot_map = (
        build_customer_map(settings)
        if settings.spot_ai_enabled and not settings.effective_mock_mode
        else {}
    )
    out: dict[str, str] = {}
    for rec in records:
        if rec.customer:
            out[rec.service_line_number] = rec.customer
        elif rec.nickname and rec.nickname.lower() in spot_map:
            out[rec.service_line_number] = spot_map[rec.nickname.lower()]
    return out


def cycle_key(rec: UsageRecord) -> str:
    """Stable per-cycle identifier (cycle end date, falling back to start)."""
    dt = rec.cycle_end or rec.cycle_start
    return dt.strftime("%Y-%m-%d") if dt else "current"


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
        seen = {rec.service_line_number for rec in records}
        customers = _resolve_customers(settings, records)
        handled_lines: set[str] = set()
        for rec in records:
            result = compute_overage(rec, settings)

            # Upsert the ServiceLine once per line (records repeat per cycle).
            if rec.service_line_number not in handled_lines:
                handled_lines.add(rec.service_line_number)
                customer = customers.get(rec.service_line_number)
                existing = session.get(ServiceLine, rec.service_line_number)
                if existing is None:
                    session.add(
                        ServiceLine(
                            service_line_number=rec.service_line_number,
                            nickname=rec.nickname,
                            customer=customer,
                            account_number=rec.account_number,
                            service_plan=rec.service_plan,
                            active=True,
                        )
                    )
                else:
                    existing.nickname = rec.nickname
                    existing.customer = customer
                    existing.service_plan = rec.service_plan
                    existing.account_number = rec.account_number

            # Upsert the per-cycle usage row (one per line per billing cycle).
            key = cycle_key(rec)
            row = session.execute(
                select(BillingCycleUsage).where(
                    BillingCycleUsage.service_line_number == rec.service_line_number,
                    BillingCycleUsage.cycle_key == key,
                )
            ).scalar_one_or_none()
            if row is None:
                row = BillingCycleUsage(
                    service_line_number=rec.service_line_number, cycle_key=key
                )
                session.add(row)
            row.cycle_start = rec.cycle_start
            row.cycle_end = rec.cycle_end
            row.included_gb = rec.included_gb
            row.priority_used_gb = rec.priority_used_gb
            row.standard_used_gb = rec.standard_used_gb
            row.overage_gb = result.overage_gb
            row.used_pct = result.used_pct
            row.status = result.status
            row.estimated_overage_cost = result.estimated_overage_cost

        # Prune lines no longer present (e.g. leftover mock data after switching
        # to live, or removed service lines). History for existing lines is kept.
        if seen:
            stale = session.execute(
                select(ServiceLine.service_line_number).where(
                    ServiceLine.service_line_number.not_in(seen)
                )
            ).scalars().all()
            if stale:
                session.query(BillingCycleUsage).filter(
                    BillingCycleUsage.service_line_number.in_(stale)
                ).delete(synchronize_session=False)
                session.query(ServiceLine).filter(
                    ServiceLine.service_line_number.in_(stale)
                ).delete(synchronize_session=False)
                logger.info("Pruned %d stale service line(s).", len(stale))

        run.lines_processed = len(seen)
        run.status = "ok"
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        logger.info(
            "Poll complete: %d service lines, %d cycle rows.",
            len(seen),
            len(records),
        )
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

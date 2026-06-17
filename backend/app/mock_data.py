"""Synthetic data generator used when credentials are absent or MOCK_MODE=1.

Produces a stable-but-realistic fleet of 200+ service lines so the dashboard,
poller, and overage math can be exercised end-to-end without the real API.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .overage import UsageRecord

_PLANS = [
    ("Priority 1TB", 1000.0),
    ("Priority 2TB", 2000.0),
    ("Priority 6TB", 6000.0),
    ("Local Priority 50GB", 50.0),
    ("Mobile Priority 50GB", 50.0),
]
_SITES = [
    "HQ", "Warehouse", "Field-Crew", "Tower", "Vessel", "RV", "Clinic",
    "Branch", "Relay", "Depot",
]


def generate_usage_records(count: int = 220, seed: int = 42) -> list[UsageRecord]:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cycle_end = (cycle_start + timedelta(days=32)).replace(day=1)

    records: list[UsageRecord] = []
    for i in range(count):
        plan_name, included = rng.choice(_PLANS)
        # Spread usage so a realistic minority are in warning/over territory.
        usage_factor = rng.choices(
            population=[
                rng.uniform(0.0, 0.6),   # comfortably under
                rng.uniform(0.6, 0.85),  # creeping up
                rng.uniform(0.85, 1.05), # near / at cap
                rng.uniform(1.05, 1.8),  # over
            ],
            weights=[55, 22, 13, 10],
            k=1,
        )[0]
        priority_used = round(included * usage_factor, 2)
        site = rng.choice(_SITES)
        records.append(
            UsageRecord(
                service_line_number=f"SL-{1000 + i}",
                nickname=f"{site}-{i:03d}",
                account_number="ACC-MOCK-0001",
                service_plan=plan_name,
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                included_gb=included,
                priority_used_gb=priority_used,
                standard_used_gb=round(rng.uniform(0, 500), 2),
            )
        )
    return records

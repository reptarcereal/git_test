"""Tests for the overage computation — the core business logic."""
from app.config import Settings
from app.overage import (
    STATUS_OK,
    STATUS_OVER,
    STATUS_WARNING,
    UsageRecord,
    compute_overage,
)

SETTINGS = Settings(warning_threshold_pct=80.0, overage_cost_per_gb=1.0)


def _rec(included: float, used: float) -> UsageRecord:
    return UsageRecord(
        service_line_number="SL-1",
        included_gb=included,
        priority_used_gb=used,
    )


def test_under_cap_is_ok():
    r = compute_overage(_rec(1000, 500), SETTINGS)
    assert r.status == STATUS_OK
    assert r.overage_gb == 0.0
    assert r.used_pct == 50.0
    assert r.estimated_overage_cost == 0.0


def test_warning_threshold():
    r = compute_overage(_rec(1000, 850), SETTINGS)
    assert r.status == STATUS_WARNING
    assert r.overage_gb == 0.0


def test_over_cap_computes_overage_and_cost():
    r = compute_overage(_rec(1000, 1250), SETTINGS)
    assert r.status == STATUS_OVER
    assert r.overage_gb == 250.0
    assert r.used_pct == 125.0
    assert r.estimated_overage_cost == 250.0


def test_exactly_at_cap_is_warning_not_over():
    r = compute_overage(_rec(1000, 1000), SETTINGS)
    assert r.status == STATUS_WARNING
    assert r.overage_gb == 0.0


def test_uncapped_line_never_over():
    r = compute_overage(_rec(0, 5000), SETTINGS)
    assert r.status == STATUS_OK
    assert r.overage_gb == 0.0
    assert r.used_pct == 0.0

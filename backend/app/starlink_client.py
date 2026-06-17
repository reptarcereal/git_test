"""Client for the Starlink Enterprise / Account Management API v2.

Implements the OAuth2 client-credentials flow, pagination, and rate-limit
backoff. The functions that map raw API JSON into our ``UsageRecord`` are
isolated and clearly marked: Starlink's response shapes can vary by account
and API revision, so adjust ``_parse_service_line`` / ``_parse_usage`` to match
the exact payloads your account returns. Everything else stays the same.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import Settings
from .overage import UsageRecord

logger = logging.getLogger(__name__)


class StarlinkAPIError(RuntimeError):
    pass


class StarlinkClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._http = httpx.Client(
            base_url=settings.starlink_api_base,
            timeout=settings.request_timeout_seconds,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "StarlinkClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- Auth ---------------------------------------------------------------
    def _get_token(self) -> str:
        """Return a valid bearer token, refreshing ~60s before expiry."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        resp = httpx.post(
            self._s.starlink_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._s.starlink_client_id,
                "client_secret": self._s.starlink_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self._s.request_timeout_seconds,
        )
        if resp.status_code != 200:
            raise StarlinkAPIError(
                f"Token request failed ({resp.status_code}): {resp.text[:300]}"
            )
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + float(payload.get("expires_in", 3600))
        return self._token

    # -- Low-level request with retry/backoff -------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._s.max_retries):
            token = self._get_token()
            headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
            try:
                resp = self._http.request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as exc:  # network-level error
                last_exc = exc
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 401:  # token expired/revoked -> force refresh
                self._token = None
                kwargs["headers"] = {}
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                self._sleep_backoff(attempt, retry_after)
                last_exc = StarlinkAPIError(
                    f"{resp.status_code} on {path}: {resp.text[:200]}"
                )
                continue
            if resp.status_code >= 400:
                raise StarlinkAPIError(
                    f"{resp.status_code} on {path}: {resp.text[:300]}"
                )
            return resp

        raise StarlinkAPIError(f"Request to {path} failed after retries: {last_exc}")

    @staticmethod
    def _sleep_backoff(attempt: int, retry_after: str | None = None) -> None:
        if retry_after and retry_after.isdigit():
            time.sleep(min(int(retry_after), 30))
            return
        time.sleep(min(2 ** attempt, 16))

    # -- High-level API -----------------------------------------------------
    def fetch_all_usage(self) -> list[UsageRecord]:
        """Return one UsageRecord per (service line, billing cycle).

        Pulls all available billing cycles so accounting has full history; the
        dashboard reads the most recent cycle per line by default.
        """
        lines = self._list_service_lines()
        usage_by_line = self._query_billing_usage(
            [ln["serviceLineNumber"] for ln in lines]
        )
        records: list[UsageRecord] = []
        for ln in lines:
            sln = ln["serviceLineNumber"]
            records.extend(
                _parse_cycles(ln, usage_by_line.get(sln, {}), self._s)
            )
        return records

    def _path(self, suffix: str) -> str:
        # v2 endpoints live under <host>/api/public/<version>/...
        return f"/api/public/{self._s.starlink_api_version}/{suffix}"

    @staticmethod
    def _unwrap_list(body: dict) -> list[dict]:
        """Pull the array of rows out of a Starlink paginated ServiceResponse.

        Shape is {"content": {"results"|"content": [...]}, "isValid": ...}.
        """
        content = body.get("content", body) or {}
        if isinstance(content, list):
            return content
        return content.get("results", content.get("content", [])) or []

    def _list_service_lines(self) -> list[dict[str, Any]]:
        # v2 is account-scoped by the service account: no account number in the
        # path. GET /api/public/v2/service-lines, paginated by `page` (size 100).
        results: list[dict[str, Any]] = []
        page = 0
        while True:
            resp = self._request(
                "GET", self._path("service-lines"), params={"page": page}
            )
            items = self._unwrap_list(resp.json())
            if not items:
                break
            results.extend(items)
            if len(items) < 100:  # server page size is fixed at 100
                break
            page += 1
        return results

    def _query_billing_usage(self, line_numbers: list[str]) -> dict[str, dict]:
        """Query current-cycle data usage for all service lines.

        v2: POST /api/public/v2/data-usage/query, paginated via `page`/`limit`
        query params (limit up to 250). Wrapped so a body/shape mismatch logs a
        warning instead of blanking the whole dashboard. The request body and
        response field names are finalized from the account's v2 swagger.
        """
        out: dict[str, dict] = {}
        limit = min(max(self._s.poll_page_size, 50), 250)
        page = 0
        try:
            while True:
                resp = self._request(
                    "POST",
                    self._path("data-usage/query"),
                    params={"page": page, "limit": limit},
                    # QueryDataUsageRequest: pull history of previous cycles too.
                    json={
                        "previousBillingCycles": self._s.history_cycles,
                        "activeServiceLinesOnly": True,
                    },
                )
                rows = self._unwrap_list(resp.json())
                if not rows:
                    break
                for item in rows:
                    sln = item.get("serviceLineNumber")
                    if sln:
                        out[sln] = item
                if len(rows) < limit:
                    break
                page += 1
        except StarlinkAPIError as exc:
            logger.warning("data-usage/query failed, usage will be blank: %s", exc)
        return out


# --------------------------------------------------------------------------
# Response mapping (Starlink v2 schema).
#   line  = ServiceLineResponse              (GET /service-lines)
#   usage = ServiceLineDataUsageForBillingCycles (POST /data-usage/query)
# --------------------------------------------------------------------------
def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (ValueError, TypeError):
        return None


def _parse_cycles(
    line: dict[str, Any], usage: dict[str, Any], settings: Settings
) -> list[UsageRecord]:
    """Expand one service line into a UsageRecord per billing cycle."""
    plan = usage.get("servicePlan") or {}
    cycles = usage.get("billingCycles") or []
    # usageLimitGB = priority limit (metered) or data-pool capacity (Priority).
    included = _num(plan.get("usageLimitGB"))
    sln = line.get("serviceLineNumber", "")
    nickname = line.get("nickname")
    plan_name = line.get("productReferenceId") or plan.get("productId")
    account = usage.get("accountNumber") or settings.starlink_account_number

    if not cycles:
        # No usage history yet: emit a single empty current-cycle record so the
        # line still appears on the dashboard.
        return [
            UsageRecord(
                service_line_number=sln,
                nickname=nickname,
                account_number=account,
                service_plan=plan_name,
                included_gb=included,
            )
        ]

    records: list[UsageRecord] = []
    for cycle in cycles:
        records.append(
            UsageRecord(
                service_line_number=sln,
                nickname=nickname,
                account_number=account,
                service_plan=plan_name,
                cycle_start=_parse_dt(cycle.get("startDate")),
                cycle_end=_parse_dt(cycle.get("endDate")),
                included_gb=included,
                # totalPriorityGB counts against the cap (incl. opt-in priority).
                priority_used_gb=_num(cycle.get("totalPriorityGB")),
                standard_used_gb=_num(cycle.get("totalStandardGB")),
            )
        )
    return records


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

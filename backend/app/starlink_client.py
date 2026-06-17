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
        """List every service line on the account and attach current usage."""
        lines = self._list_service_lines()
        usage_by_line = self._query_billing_usage(
            [ln["serviceLineNumber"] for ln in lines]
        )
        records: list[UsageRecord] = []
        for ln in lines:
            sln = ln["serviceLineNumber"]
            records.append(_parse_service_line(ln, usage_by_line.get(sln, {}), self._s))
        return records

    @property
    def _v(self) -> str:
        return self._s.starlink_api_version

    def _list_service_lines(self) -> list[dict[str, Any]]:
        # v2: account-scoped by the service account, so no account number in the
        # path. GET /public/v2/service-lines (paginated).
        results: list[dict[str, Any]] = []
        page = 0
        while True:
            resp = self._request(
                "GET",
                f"/public/{self._v}/service-lines",
                params={"pageIndex": page, "limit": self._s.poll_page_size},
            )
            body = resp.json()
            content = body.get("content", body) or {}
            items = content.get("results", content.get("content", [])) if isinstance(content, dict) else content
            if not items:
                break
            results.extend(items)
            # Stop when the page is short — robust across paging schemes.
            if len(items) < self._s.poll_page_size:
                break
            page += 1
        return results

    def _query_billing_usage(self, line_numbers: list[str]) -> dict[str, dict]:
        """Query current-cycle data usage for the given service lines.

        v2: POST /public/v2/data-usage/query. Done in batches to respect
        request-size and rate limits. NOTE: the request body and response
        shape below are best-effort — confirm against your account's swagger.
        """
        out: dict[str, dict] = {}
        batch = self._s.poll_page_size
        for i in range(0, len(line_numbers), batch):
            chunk = line_numbers[i : i + batch]
            resp = self._request(
                "POST",
                f"/public/{self._v}/data-usage/query",
                json={
                    "serviceLinesFilter": chunk,
                    "pageIndex": 0,
                    "pageLimit": batch,
                },
            )
            body = resp.json()
            content = body.get("content", body) or {}
            rows = content.get("results", content.get("dataUsage", [])) if isinstance(content, dict) else content
            for item in rows:
                sln = item.get("serviceLineNumber")
                if sln:
                    out[sln] = item
        return out


# --------------------------------------------------------------------------
# Response mapping — ADJUST THESE TO YOUR ACCOUNT'S PAYLOAD SHAPE.
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


def _parse_service_line(
    line: dict[str, Any], usage: dict[str, Any], settings: Settings
) -> UsageRecord:
    return UsageRecord(
        service_line_number=line.get("serviceLineNumber", ""),
        nickname=line.get("nickname") or line.get("serviceLineName"),
        account_number=settings.starlink_account_number,
        service_plan=line.get("productReferenceId") or line.get("servicePlan"),
        cycle_start=_parse_dt(usage.get("startDate") or usage.get("cycleStart")),
        cycle_end=_parse_dt(usage.get("endDate") or usage.get("cycleEnd")),
        included_gb=_num(usage.get("includedGB") or usage.get("dataAllotmentGB")),
        priority_used_gb=_num(
            usage.get("priorityGB")
            or usage.get("totalPriorityGB")
            or usage.get("dataUsageGB")
        ),
        standard_used_gb=_num(usage.get("standardGB") or usage.get("optInPriorityGB")),
    )


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

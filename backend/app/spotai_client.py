"""Spot.ai client: build a unit-number -> customer mapping.

The Spot.ai API (https://developers.spot.ai) is organization-scoped and uses
Bearer-token auth, so each API key corresponds to one organization = one
customer. For each configured account we list that org's locations
(GET /locations, cursor-paginated, returns id + name) and treat each location
name as a Starlink "unit number" (nickname). The account's customer label is
then attached to every matching service line.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class SpotAiClient:
    def __init__(self, api_key: str, settings: Settings) -> None:
        self._http = httpx.Client(
            base_url=settings.spot_ai_api_base,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=settings.request_timeout_seconds,
        )
        self._retries = settings.max_retries

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SpotAiClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def list_locations(self) -> list[dict[str, Any]]:
        """All locations for this org, following cursor pagination."""
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            resp = self._http.get("/locations", params=params)
            resp.raise_for_status()
            body = resp.json()
            # Response shape: {"data": [{id, name}, ...], "next": <cursor|null>}.
            items = (
                body.get("data")
                or body.get("locations")
                or body.get("results")
                or (body if isinstance(body, list) else [])
            )
            results.extend(items)
            cursor = body.get("next") if isinstance(body, dict) else None
            if not cursor or not items:
                break
        return results


def build_customer_map(settings: Settings) -> dict[str, str]:
    """Return {location_name_lower: customer} across all Spot.ai accounts.

    Failures for one account are logged and skipped so the poll still succeeds.
    """
    mapping: dict[str, str] = {}
    for account in settings.spot_ai_account_list:
        api_key = account["api_key"]
        customer_label = account.get("customer") or ""
        try:
            with SpotAiClient(api_key, settings) as client:
                locations = client.list_locations()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Spot.ai location fetch failed for an account: %s", exc)
            continue
        for loc in locations:
            name = (loc.get("name") or "").strip()
            if not name:
                continue
            # Prefer an org/customer field on the location if present; otherwise
            # use the account's configured customer label.
            customer = (
                loc.get("organization")
                or loc.get("organizationName")
                or loc.get("customer")
                or customer_label
            )
            if customer:
                mapping[name.lower()] = customer
    logger.info("Spot.ai: mapped %d locations to customers.", len(mapping))
    return mapping

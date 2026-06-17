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
import re
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


def extract_unit_tokens(text: str | None) -> list[str]:
    """Reduce a nickname or location name to its unit identity token(s).

    A unit's identity is an optional *glued* alpha prefix plus its number:
      - "VX002"      -> "VX2"   (the glued "VX" series code is significant)
      - "Unit 002"   -> "2"     (a separate word like "Unit"/"Site" is a label,
                                  ignored; only the number matters)
      - "Site 118 - Phoenix" -> "118"
      - "Starlink Mini Test" -> []   (no number)

    So "VX002" (VX2) and "Unit 002" (2) are correctly treated as different
    units, while formatting differences (spacing, leading zeros, trailing city
    names) are ignored. Letters are only kept when glued to the digits with no
    space, e.g. "VX-002" -> "VX2".
    """
    tokens: list[str] = []
    seen: set[str] = set()
    for word in re.split(r"\s+", (text or "").strip()):
        m = re.match(r"^([A-Za-z]*)[-_]*0*(\d+)", word)
        if not m:
            continue
        prefix = m.group(1).upper()
        number = m.group(2).lstrip("0") or "0"
        token = f"{prefix}{number}"
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


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
    """Return {unit_token: customer} across all Spot.ai accounts.

    Each location name is reduced to its unit identity token(s); failures for
    one account are logged and skipped so the poll still succeeds.
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
        # Prefer an org/customer field on the location if present, else the
        # account's configured customer label.
        for loc in locations:
            customer = (
                loc.get("organization")
                or loc.get("organizationName")
                or loc.get("customer")
                or customer_label
            )
            if not customer:
                continue
            for token in extract_unit_tokens(loc.get("name")):
                if token in mapping and mapping[token] != customer:
                    logger.warning(
                        "Spot.ai: unit %s maps to multiple customers (%s, %s)",
                        token, mapping[token], customer,
                    )
                mapping.setdefault(token, customer)
    logger.info("Spot.ai: mapped %d unit tokens to customers.", len(mapping))
    return mapping

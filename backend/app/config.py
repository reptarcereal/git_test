"""Application configuration, loaded from environment variables / .env.

All Starlink-specific values are configurable so the same code can target the
real Enterprise (Account Management) API v2 or run in MOCK mode for local
development and demos.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Mode --------------------------------------------------------------
    # When True, the app serves synthetic data and never calls Starlink.
    # Automatically treated as True if credentials are missing.
    mock_mode: bool = False

    # --- Starlink API v2 credentials & endpoints ---------------------------
    starlink_client_id: str = ""
    starlink_client_secret: str = ""
    starlink_account_number: str = ""

    # OAuth2 client-credentials token endpoint.
    starlink_token_url: str = "https://www.starlink.com/api/auth/connect/token"
    # Base URL (host) for the API. v2 endpoints live under /api/public/<ver>/.
    starlink_api_base: str = "https://www.starlink.com"
    # API version segment used in request paths (v1 deprecated 2026-05-01).
    starlink_api_version: str = "v2"

    # --- Spot.ai customer mapping ------------------------------------------
    # Maps Starlink nicknames (unit numbers) to customers via Spot.ai locations.
    # The Spot.ai API is organization-scoped, so each API key = one customer
    # (organization). Configure one key per customer:
    #   SPOT_AI_ACCOUNTS='[{"customer":"Acme Corp","api_key":"sk_..."}, ...]'
    # Or a single key + customer label for a one-org setup.
    spot_ai_api_base: str = "https://dev-api.spot.ai/v1"
    spot_ai_api_key: str = ""
    spot_ai_customer: str = ""
    spot_ai_accounts: str = ""  # JSON list of {"customer", "api_key"}

    # --- Polling -----------------------------------------------------------
    poll_interval_seconds: int = 3600  # how often to refresh usage (default 1h)
    poll_page_size: int = 100  # service lines per API page / batch
    poll_on_startup: bool = True
    # Previous billing cycles to pull for history (high = "max available";
    # Starlink returns as many as it has). 0 = current cycle only.
    history_cycles: int = 60

    # --- Overage accounting ------------------------------------------------
    # % of the included allotment at which a line is flagged "warning".
    warning_threshold_pct: float = 80.0
    # Estimated cost per GB of overage (priority data), used for $ estimates.
    overage_cost_per_gb: float = 1.00

    # --- Storage -----------------------------------------------------------
    database_url: str = "sqlite:///./starlink_dashboard.db"

    # --- HTTP client -------------------------------------------------------
    request_timeout_seconds: float = 30.0
    max_retries: int = 4

    @property
    def has_credentials(self) -> bool:
        return bool(
            self.starlink_client_id
            and self.starlink_client_secret
            and self.starlink_account_number
        )

    @property
    def effective_mock_mode(self) -> bool:
        return self.mock_mode or not self.has_credentials

    @property
    def spot_ai_account_list(self) -> list[dict[str, str]]:
        """Normalized list of {"customer", "api_key"} Spot.ai accounts."""
        import json

        accounts: list[dict[str, str]] = []
        if self.spot_ai_accounts.strip():
            try:
                parsed = json.loads(self.spot_ai_accounts)
                if isinstance(parsed, list):
                    accounts.extend(
                        {"customer": a.get("customer", ""), "api_key": a.get("api_key", "")}
                        for a in parsed
                        if a.get("api_key")
                    )
            except (ValueError, AttributeError):
                pass
        if self.spot_ai_api_key:
            accounts.append(
                {"customer": self.spot_ai_customer, "api_key": self.spot_ai_api_key}
            )
        return accounts

    @property
    def spot_ai_enabled(self) -> bool:
        return bool(self.spot_ai_account_list)


@lru_cache
def get_settings() -> Settings:
    return Settings()

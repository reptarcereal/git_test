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
    # Base URL for the Enterprise / Account Management API.
    starlink_api_base: str = "https://web-api.starlink.com"
    # API version segment used in request paths (v1 deprecated 2026-05-01).
    starlink_api_version: str = "v2"

    # --- Polling -----------------------------------------------------------
    poll_interval_seconds: int = 3600  # how often to refresh usage (default 1h)
    poll_page_size: int = 100  # service lines per API page / batch
    poll_on_startup: bool = True

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


@lru_cache
def get_settings() -> Settings:
    return Settings()

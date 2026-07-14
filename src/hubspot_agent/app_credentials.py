from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hubspot_agent.fileio import write_private_json


def _credentials_file() -> Path:
    return Path.home() / ".claude" / "hubspot" / "app_credentials.json"


def _ensure_config_dir() -> Path:
    path = _credentials_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.parent


def load_app_credentials() -> dict[str, Any] | None:
    path = _credentials_file()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def save_app_credentials(
    client_id: str,
    client_secret: str,
    app_id: str | None = None,
    region: str = "us",
) -> None:
    if region not in _REGIONS:
        raise ValueError(f"Invalid region {region!r}; expected one of {_REGIONS}")
    _ensure_config_dir()
    payload: dict[str, Any] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "region": region,
    }
    if app_id is not None:
        payload["app_id"] = app_id
    path = _credentials_file()
    write_private_json(path, payload)


def get_client_id() -> str | None:
    creds = load_app_credentials()
    return creds.get("client_id") if creds else None


def get_client_secret() -> str | None:
    creds = load_app_credentials()
    return creds.get("client_secret") if creds else None


def get_region() -> str:
    """Return the configured app region (``"us"`` or ``"eu"``); default ``"us"``."""
    creds = load_app_credentials()
    region = creds.get("region", "us") if creds else "us"
    return region if region in _REGIONS else "us"


def get_oauth_endpoints() -> tuple[str, str]:
    """Return ``(authorize_url, token_url)`` for the configured app region.

    HubSpot apps are region-specific: an EU app (created in the EU developer
    portal) must use the eu1 endpoints, or the OAuth flow fails with
    "Hub is unknown to this Hublet, but it appears to exist in Hublet eu1".
    """
    return _REGION_ENDPOINTS[get_region()]


def get_api_base_url() -> str:
    """Return the HubSpot API base URL for the configured app region."""
    return _REGION_API_BASE[get_region()]


_REGIONS = ("us", "eu")
_REGION_ENDPOINTS = {
    "us": (
        "https://app.hubspot.com/oauth/authorize",
        "https://api.hubapi.com/oauth/v1/token",
    ),
    "eu": (
        "https://app-eu1.hubspot.com/oauth/authorize",
        "https://api-eu1.hubapi.com/oauth/v1/token",
    ),
}
_REGION_API_BASE = {
    "us": "https://api.hubapi.com",
    "eu": "https://api-eu1.hubapi.com",
}

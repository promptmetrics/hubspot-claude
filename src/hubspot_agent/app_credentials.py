from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
) -> None:
    _ensure_config_dir()
    payload: dict[str, Any] = {"client_id": client_id, "client_secret": client_secret}
    if app_id is not None:
        payload["app_id"] = app_id
    _credentials_file().write_text(json.dumps(payload, indent=2))


def get_client_id() -> str | None:
    creds = load_app_credentials()
    return creds.get("client_id") if creds else None


def get_client_secret() -> str | None:
    creds = load_app_credentials()
    return creds.get("client_secret") if creds else None

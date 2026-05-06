from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PortalConfig:
    portal_id: str
    token: str
    tier: str = "unknown"
    scopes_granted: list[str] | None = None


CONFIG_DIR = Path.home() / ".claude" / "hubspot"


def _ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def detect_default_portal(working_dir: str) -> str | None:
    portal_file = Path(working_dir) / ".hubspot-portal"
    if portal_file.exists():
        return portal_file.read_text().strip().splitlines()[0].strip()
    return None


def load_portal_config(portal_id: str) -> PortalConfig | None:
    """Load portal config from environment or config directory."""
    token = os.getenv(f"HUBSPOT_TOKEN_{portal_id}")
    if not token:
        token_file = CONFIG_DIR / f"{portal_id}.token"
        if token_file.exists():
            token = token_file.read_text().strip()
    if not token:
        return None
    return PortalConfig(
        portal_id=portal_id,
        token=token,
        tier=os.getenv(f"HUBSPOT_TIER_{portal_id}", "unknown"),
        scopes_granted=os.getenv(f"HUBSPOT_SCOPES_{portal_id}", "").split(",") if os.getenv(f"HUBSPOT_SCOPES_{portal_id}") else [],
    )


def save_portal_config(portal: PortalConfig) -> None:
    _ensure_config_dir()
    token_file = CONFIG_DIR / f"{portal.portal_id}.token"
    token_file.write_text(portal.token)

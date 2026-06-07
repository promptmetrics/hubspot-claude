from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hubspot_agent.config import CONFIG_DIR


def _pending_previews_dir(portal_id: str) -> Path:
    return CONFIG_DIR / portal_id / "pending_previews"


def store(portal_id: str, action_id: str, data: dict[str, Any]) -> None:
    """Persist a pending preview to disk with a server-side timestamp."""
    pending_dir = _pending_previews_dir(portal_id)
    pending_dir.mkdir(parents=True, exist_ok=True)
    file_path = pending_dir / f"{action_id}.json"
    data["_stored_at"] = datetime.now(timezone.utc).isoformat()
    file_path.write_text(json.dumps(data, indent=2, default=str))
    file_path.chmod(0o600)


def load(portal_id: str, action_id: str) -> dict[str, Any] | None:
    """Load a pending preview from disk by action_id."""
    file_path = _pending_previews_dir(portal_id) / f"{action_id}.json"
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text())


def clear(portal_id: str, action_id: str) -> None:
    """Remove a pending preview from disk."""
    file_path = _pending_previews_dir(portal_id) / f"{action_id}.json"
    if file_path.exists():
        file_path.unlink()


def list_pending(portal_id: str) -> list[Path]:
    """List pending preview files, newest first."""
    pending_dir = _pending_previews_dir(portal_id)
    if not pending_dir.exists():
        return []
    return sorted(pending_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)


def reap_expired(portal_id: str, max_age_hours: int = 24) -> int:
    """Remove previews older than max_age_hours. Returns count removed."""
    pending_dir = _pending_previews_dir(portal_id)
    if not pending_dir.exists():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
    removed = 0
    for file_path in pending_dir.iterdir():
        if file_path.suffix != ".json":
            continue
        try:
            data = json.loads(file_path.read_text())
            stored = data.get("_stored_at")
            if not stored:
                mtime = file_path.stat().st_mtime
                if mtime < cutoff:
                    file_path.unlink()
                    removed += 1
                continue
            stored_dt = datetime.fromisoformat(stored)
            if stored_dt.timestamp() < cutoff:
                file_path.unlink()
                removed += 1
        except (json.JSONDecodeError, ValueError, OSError):
            continue
    return removed

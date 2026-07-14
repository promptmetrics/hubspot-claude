from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hubspot_agent.config import CONFIG_DIR


def _log_path(portal_id: str) -> Path:
    return CONFIG_DIR / portal_id / "loop-log.ndjson"


def log_event(
    portal_id: str,
    trace_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> Path:
    """Append a single NDJSON event to the portal loop log.

    The loop log is append-only and is not authoritative for control flow;
    it exists for debugging, audit, and user visibility.
    """
    log_file = _log_path(portal_id)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "event_type": event_type,
        "payload": payload or {},
    }
    fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")
        fh.flush()
    return log_file


def get_recent(portal_id: str, trace_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Return the most recent events from the loop log, newest first.

    If ``trace_id`` is provided, only events for that trace are returned.
    """
    log_file = _log_path(portal_id)
    if not log_file.exists():
        return []

    events: list[dict[str, Any]] = []
    try:
        with log_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if trace_id is not None and event.get("trace_id") != trace_id:
                    continue
                events.append(event)
    except OSError:
        return []

    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return events[:limit]


def rotate(portal_id: str, max_bytes: int = 1_000_000, keep: int = 3) -> None:
    """Rotate the loop log if it exceeds ``max_bytes``.

    Keeps up to ``keep`` archived logs in addition to the active log.
    """
    log_file = _log_path(portal_id)
    if not log_file.exists() or log_file.stat().st_size <= max_bytes:
        return

    archive_dir = log_file.parent / "loop-log-archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = archive_dir / f"loop-log-{timestamp}.ndjson"
    log_file.rename(archive)

    archives = sorted(archive_dir.glob("loop-log-*.ndjson"), key=lambda p: p.stat().st_mtime)
    for old in archives[:-keep]:
        old.unlink()

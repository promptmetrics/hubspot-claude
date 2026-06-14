from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hubspot_agent.redaction import redact_dict_for_disk


class ActionLedger:
    """Append-only action log for idempotency and observability.

    Writes `started` and `completed` entries to `action_log.jsonl`.
    Re-dispatch checks in-flight actions to prevent duplicates.
    """

    STALE_SECONDS = 3600  # 1 hour

    def __init__(self, portal_id: str, base_dir: Path | None = None) -> None:
        self.portal_id = portal_id
        self.base_dir = base_dir or (Path.home() / ".claude" / "hubspot" / portal_id)
        self.log_file = self.base_dir / "action_log.jsonl"

    def _append(self, entry: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        safe_entry = redact_dict_for_disk(entry)
        line = json.dumps(safe_entry, sort_keys=True) + "\n"
        # Atomic append via temp file + rename to avoid interleaved writes
        fd, temp_path = tempfile.mkstemp(dir=str(self.base_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                if self.log_file.exists():
                    f.write(self.log_file.read_text())
                f.write(line)
            os.replace(temp_path, self.log_file)
        except Exception:
            os.unlink(temp_path)
            raise

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        """Deterministic hash of a JSON payload for comparison."""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _parse_iso_timestamp(ts: str) -> datetime:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    def start_action(
        self,
        action_id: str,
        agent: str,
        action: str,
        payload: dict[str, Any],
    ) -> None:
        self._append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_id": action_id,
            "status": "started",
            "agent": agent,
            "action": action,
            "payload_hash": self._hash_payload(payload),
        })

    def complete_action(self, action_id: str, result: dict[str, Any]) -> None:
        self._append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_id": action_id,
            "status": "completed",
            "result": result,
        })

    def _load_entries(self) -> list[dict[str, Any]]:
        if not self.log_file.exists():
            return []
        lines = self.log_file.read_text().strip().splitlines()
        entries: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def get_in_flight(self) -> list[dict[str, Any]]:
        """Return actions with `started` but no matching `completed`."""
        entries = self._load_entries()
        started: dict[str, dict[str, Any]] = {}
        completed: set[str] = set()
        for entry in entries:
            aid = entry.get("action_id")
            if not aid:
                continue
            status = entry.get("status")
            if status == "started":
                started[aid] = entry
            elif status == "completed":
                completed.add(aid)
        return [entry for aid, entry in started.items() if aid not in completed]

    def find_similar_in_flight(
        self,
        agent: str,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Find an in-flight action with the same agent, action, and payload.

        Ignores entries older than STALE_SECONDS to avoid blocking on
        actions whose completion was never recorded.
        """
        target_hash = self._hash_payload(payload)
        now = datetime.now(timezone.utc)
        for entry in self.get_in_flight():
            ts = entry.get("timestamp")
            if ts:
                try:
                    entry_time = self._parse_iso_timestamp(ts)
                    if (now - entry_time).total_seconds() > self.STALE_SECONDS:
                        continue
                except ValueError:
                    pass
            if (
                entry.get("agent") == agent
                and entry.get("action") == action
                and entry.get("payload_hash") == target_hash
            ):
                return entry
        return None

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent log entries across all statuses."""
        entries = self._load_entries()
        return entries[-limit:]

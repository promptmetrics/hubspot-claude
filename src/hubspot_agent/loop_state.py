from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hubspot_agent.config import CONFIG_DIR
from hubspot_agent.models import LoopPlan, StepArtifact


class LoopState:
    """Durable in-memory representation of a running loop.

    Loop state is persisted to disk so that a long-running or interrupted
    loop can be resumed across conversation turns.  It is intentionally a
    plain data container; control decisions live in ``LoopController``.
    """

    def __init__(
        self,
        *,
        portal_id: str,
        request_text: str,
        trace_id: str,
        plan: LoopPlan,
        current_step: int = 0,
        artifacts: list[StepArtifact] | None = None,
        status: str = "running",
        started_at: datetime | None = None,
        updated_at: datetime | None = None,
        iterations: int = 0,
        last_error: str | None = None,
        last_verification_hash: str | None = None,
        plateau_count: int = 0,
        pending_action_id: str | None = None,
    ) -> None:
        self.portal_id = portal_id
        self.request_text = request_text
        self.trace_id = trace_id
        self.plan = plan
        self.current_step = current_step
        self.artifacts = artifacts or []
        self.status = status
        self.started_at = started_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.iterations = iterations
        self.last_error = last_error
        self.last_verification_hash = last_verification_hash
        self.plateau_count = plateau_count
        # Set while the loop is paused at a write step (status
        # ``awaiting_approval``): the ``action_id`` of the persisted pending
        # preview the human must ``approve``.  Cleared once the write is
        # verified and the loop advances.
        self.pending_action_id = pending_action_id

    @property
    def total_steps(self) -> int:
        return len(self.plan.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "portal_id": self.portal_id,
            "request_text": self.request_text,
            "trace_id": self.trace_id,
            "plan": self.plan.model_dump(mode="json"),
            "current_step": self.current_step,
            "artifacts": [a.model_dump(mode="json") for a in self.artifacts],
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "iterations": self.iterations,
            "last_error": self.last_error,
            "last_verification_hash": self.last_verification_hash,
            "plateau_count": self.plateau_count,
            "pending_action_id": self.pending_action_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoopState":
        return cls(
            portal_id=data["portal_id"],
            request_text=data["request_text"],
            trace_id=data["trace_id"],
            plan=LoopPlan.model_validate(data["plan"]),
            current_step=data.get("current_step", 0),
            artifacts=[StepArtifact.model_validate(a) for a in data.get("artifacts", [])],
            status=data.get("status", "running"),
            started_at=datetime.fromisoformat(data["started_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            iterations=data.get("iterations", 0),
            last_error=data.get("last_error"),
            last_verification_hash=data.get("last_verification_hash"),
            plateau_count=data.get("plateau_count", 0),
            pending_action_id=data.get("pending_action_id"),
        )


def _state_path(portal_id: str) -> Path:
    return CONFIG_DIR / portal_id / "loop-state.json"


def load(portal_id: str) -> LoopState | None:
    """Load the persisted loop state for a portal, if any."""
    path = _state_path(portal_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    try:
        return LoopState.from_dict(data)
    except (KeyError, ValueError, TypeError):
        return None


def save(state: LoopState) -> Path:
    """Atomically persist loop state to disk."""
    state.updated_at = datetime.now(timezone.utc)
    path = _state_path(state.portal_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(dir_fd, fcntl.LOCK_EX)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="loop-state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state.to_dict(), fh, indent=2, default=str)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    finally:
        fcntl.flock(dir_fd, fcntl.LOCK_UN)
        os.close(dir_fd)
    path.chmod(0o600)
    return path


def clear(portal_id: str) -> None:
    """Remove persisted loop state for a portal."""
    path = _state_path(portal_id)
    if path.exists():
        path.unlink()


# Statuses where the loop is deliberately parked waiting on a human
# (an ``approve`` or a verification verdict).  These are exempt from the
# staleness reaper: a paused loop must survive across turns and a lunch break,
# so we never clear it just because 2h elapsed with no update.
_HUMAN_WAIT_STATUSES = frozenset({"awaiting_approval", "awaiting_verification"})


def is_stale(state: LoopState, max_age_hours: int = 2) -> bool:
    """Return True if the loop state has not been updated recently.

    A loop parked on a human decision (``awaiting_approval`` /
    ``awaiting_verification``) is never stale — clearing it would silently drop
    an in-flight, already-previewed (or already-executed) write.
    """
    if state.status in _HUMAN_WAIT_STATUSES:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return state.updated_at < cutoff

"""Per-portal store for scheduled tasks.

One JSON file per schedule under ``CONFIG_DIR/<portal_id>/schedules/<id>.json``.
Mirrors the flock + atomic-write discipline of :mod:`hubspot_agent.persistence`
(``_dir_lock`` for serialized writers, ``_atomic_write_json`` for
mkstemp -> fsync -> os.replace at 0o600) so a scheduled batch can never observe
a half-written schedule record.

``config.CONFIG_DIR`` is read lazily (attribute access) so test fixtures that
monkeypatch it redirect the reads.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from hubspot_agent import config
from hubspot_agent.config import _validate_portal_id

_SCHEDULE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _validate_schedule_id(schedule_id: str) -> None:
    if not schedule_id or not _SCHEDULE_ID_RE.fullmatch(schedule_id):
        raise ValueError(f"Invalid schedule_id: {schedule_id!r}")


class Schedule:
    """A registered recurring task: a cron expression plus a stored concrete plan.

    Plain data container (like :class:`hubspot_agent.loop_state.LoopState`); the
    ``plan`` is a serialized ``LoopPlan`` kept as a dict so this module does not
    depend on the model layer.
    """

    def __init__(
        self,
        *,
        id: str,
        name: str,
        cron: str,
        plan: dict[str, Any],
        created_at: datetime,
        last_run_at: datetime | None = None,
        last_batch: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.cron = cron
        self.plan = plan
        self.created_at = created_at
        # Set after a run records its wall-clock fire time.
        self.last_run_at = last_run_at
        # The most recent staged batch: {run_at, status, pending_action_ids, summary}.
        self.last_batch = last_batch

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "cron": self.cron,
            "plan": self.plan,
            "created_at": self.created_at.isoformat(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_batch": self.last_batch,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Schedule":
        last_run = data.get("last_run_at")
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            cron=data["cron"],
            plan=data.get("plan", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_run_at=datetime.fromisoformat(last_run) if last_run else None,
            last_batch=data.get("last_batch"),
        )


def _schedules_dir(portal_id: str) -> Path:
    _validate_portal_id(portal_id)
    return config.CONFIG_DIR / portal_id / "schedules"


@contextmanager
def _dir_lock(dir_path: Path):
    """Exclusive flock on a directory to serialize concurrent schedule writers."""
    dir_path.mkdir(parents=True, exist_ok=True)
    fd = os.open(dir_path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON to ``path`` (mkstemp -> fsync -> os.replace, 0o600).

    Caller holds ``_dir_lock``; this helper does not lock (avoids self-deadlock).
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + "-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def save(portal_id: str, schedule: Schedule) -> None:
    """Persist a schedule to disk."""
    _validate_schedule_id(schedule.id)
    schedules_dir = _schedules_dir(portal_id)
    file_path = schedules_dir / f"{schedule.id}.json"
    with _dir_lock(schedules_dir):
        _atomic_write_json(file_path, schedule.to_dict())


def load(portal_id: str, schedule_id: str) -> Schedule | None:
    """Load a schedule by id, or None if absent/unreadable/corrupt."""
    if not schedule_id or not _SCHEDULE_ID_RE.fullmatch(schedule_id):
        return None
    file_path = _schedules_dir(portal_id) / f"{schedule_id}.json"
    if not file_path.exists():
        return None
    try:
        data = json.loads(file_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    try:
        return Schedule.from_dict(data)
    except (KeyError, ValueError, TypeError):
        return None


def list_schedules(portal_id: str) -> list[Schedule]:
    """All schedules for a portal, newest-first by ``created_at`` ([] if none)."""
    schedules_dir = _schedules_dir(portal_id)
    if not schedules_dir.exists():
        return []
    schedules: list[Schedule] = []
    for file_path in schedules_dir.iterdir():
        if file_path.suffix != ".json":
            continue
        try:
            data = json.loads(file_path.read_text())
            schedules.append(Schedule.from_dict(data))
        except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError):
            continue
    schedules.sort(key=lambda s: s.created_at, reverse=True)
    return schedules


def remove(portal_id: str, schedule_id: str) -> bool:
    """Delete a schedule. Returns True if a file was removed, else False."""
    if not schedule_id or not _SCHEDULE_ID_RE.fullmatch(schedule_id):
        return False
    schedules_dir = _schedules_dir(portal_id)
    if not schedules_dir.exists():
        return False
    file_path = schedules_dir / f"{schedule_id}.json"
    with _dir_lock(schedules_dir):
        if file_path.exists():
            file_path.unlink()
            return True
    return False


def _mutate(portal_id: str, schedule_id: str, apply) -> None:
    """Load-mutate-save a schedule under lock; no-op if it is missing."""
    if not schedule_id or not _SCHEDULE_ID_RE.fullmatch(schedule_id):
        return
    schedules_dir = _schedules_dir(portal_id)
    file_path = schedules_dir / f"{schedule_id}.json"
    with _dir_lock(schedules_dir):
        if not file_path.exists():
            return
        try:
            data = json.loads(file_path.read_text())
            schedule = Schedule.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError):
            return
        apply(schedule)
        _atomic_write_json(file_path, schedule.to_dict())


def set_last_batch(portal_id: str, schedule_id: str, batch: dict[str, Any]) -> None:
    """Record the schedule's most recent staged batch (no-op if missing)."""
    def _apply(s: Schedule) -> None:
        s.last_batch = batch
    _mutate(portal_id, schedule_id, _apply)


def set_last_run(portal_id: str, schedule_id: str, when: datetime) -> None:
    """Record the schedule's most recent run time (no-op if missing)."""
    def _apply(s: Schedule) -> None:
        s.last_run_at = when
    _mutate(portal_id, schedule_id, _apply)

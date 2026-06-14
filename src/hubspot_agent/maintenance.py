from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PruneReport:
    pruned_count: int
    pruned_files: list[str] = field(default_factory=list)


@dataclass
class MaintenanceReport:
    snapshots: PruneReport
    checkpoints: PruneReport
    rotated: bool


def _validate_portal_id(portal_id: str) -> None:
    if not portal_id or not re.fullmatch(r"[0-9]+", portal_id):
        raise ValueError(f"Invalid portal_id: {portal_id}")


def _portal_dir(portal_id: str) -> Path:
    _validate_portal_id(portal_id)
    return Path.home() / ".claude" / "hubspot" / portal_id


def _is_older_than(path: Path, max_age_days: int) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) > (max_age_days * 86400)
    except OSError:
        return False


def prune_snapshots(portal_id: str, max_age_days: int = 30) -> PruneReport:
    snapshot_dir = _portal_dir(portal_id) / "undo_snapshots"
    pruned: list[str] = []
    if snapshot_dir.exists() and snapshot_dir.is_dir():
        for file_path in snapshot_dir.glob("*.json"):
            if not file_path.is_file():
                continue
            if _is_older_than(file_path, max_age_days):
                try:
                    file_path.unlink()
                    pruned.append(file_path.name)
                except OSError:
                    continue
    return PruneReport(pruned_count=len(pruned), pruned_files=pruned)


def prune_completed_checkpoints(portal_id: str, max_age_days: int = 7) -> PruneReport:
    completed_dir = _portal_dir(portal_id) / "completed"
    pruned: list[str] = []
    if completed_dir.exists() and completed_dir.is_dir():
        for file_path in completed_dir.glob("*.jsonl"):
            if not file_path.is_file():
                continue
            if _is_older_than(file_path, max_age_days):
                try:
                    file_path.unlink()
                    pruned.append(file_path.name)
                except OSError:
                    continue
    return PruneReport(pruned_count=len(pruned), pruned_files=pruned)


def rotate_jsonl(file_path: Path | str, max_size_mb: int = 100) -> bool:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return False
    max_bytes = max_size_mb * 1024 * 1024
    try:
        if path.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False
    rotated = path.with_suffix(".1.jsonl")
    try:
        os.replace(str(path), str(rotated))
    except OSError:
        return False
    return True


async def run_maintenance(portal_id: str) -> MaintenanceReport:
    try:
        snapshots = await asyncio.to_thread(prune_snapshots, portal_id)
    except Exception:
        snapshots = PruneReport(pruned_count=0)
    try:
        checkpoints = await asyncio.to_thread(prune_completed_checkpoints, portal_id)
    except Exception:
        checkpoints = PruneReport(pruned_count=0)
    traces_path = _portal_dir(portal_id) / "traces.jsonl"
    try:
        rotated = await asyncio.to_thread(rotate_jsonl, traces_path)
    except Exception:
        rotated = False
    return MaintenanceReport(snapshots=snapshots, checkpoints=checkpoints, rotated=rotated)

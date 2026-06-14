from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_undo_snapshot(
    snapshot_dir: str,
    action_id: str,
    original_values: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> Path:
    dir_path = Path(snapshot_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{action_id}.json"
    payload: dict[str, Any] = {
        "action_id": action_id,
        "original_values": original_values,
    }
    if metadata:
        payload["metadata"] = metadata
    file_path.write_text(json.dumps(payload, indent=2))
    return file_path


def update_undo_snapshot(
    snapshot_dir: str,
    action_id: str,
    original_values: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path | None:
    """Merge additional data into an existing undo snapshot."""
    file_path = Path(snapshot_dir) / f"{action_id}.json"
    if not file_path.exists():
        return None
    payload = json.loads(file_path.read_text())
    if original_values is not None:
        payload["original_values"] = original_values
    if metadata is not None:
        payload.setdefault("metadata", {}).update(metadata)
    file_path.write_text(json.dumps(payload, indent=2))
    return file_path


def load_undo_snapshot(snapshot_dir: str, action_id: str) -> dict[str, Any] | None:
    file_path = Path(snapshot_dir) / f"{action_id}.json"
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text())


def delete_undo_snapshot(snapshot_dir: str, action_id: str) -> None:
    file_path = Path(snapshot_dir) / f"{action_id}.json"
    if file_path.exists():
        file_path.unlink()

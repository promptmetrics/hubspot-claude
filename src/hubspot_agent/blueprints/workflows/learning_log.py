"""Append-only learning log for unknown workflow actions.

When the extractor hits an ``actionTypeId`` it can't natively invert, it keeps
the action raw and records it here so the converter's coverage can grow over
time. R11: this stores field *names* and truncated (~100 char) *value previews*
only — never full payloads — so a portal's private data does not leak into a
log file that lives on the user's disk.

Path: ``~/.claude/hubspot/<portal_id>/blueprint_learning.jsonl`` (one JSON
object per line, append-only). Dedupe is per ``action_type_id`` within a single
``record_unknown_actions`` call (one extraction run).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PREVIEW_LIMIT = 100


def _portal_dir(portal_id: str, base_dir: Path | None) -> Path:
    root = base_dir if base_dir is not None else Path.home() / ".claude" / "hubspot"
    return root / str(portal_id)


def _truncate(value: Any) -> str:
    if isinstance(value, str):
        s = value
    else:
        s = json.dumps(value, default=str)
    return s[:_PREVIEW_LIMIT]


def record_unknown_actions(
    portal_id: str,
    workflow_id: str,
    unknown_actions: list[dict[str, Any]],
    base_dir: Path | None = None,
    recorded_at: str | None = None,
) -> Path:
    """Append one JSONL record per *new* ``action_type_id`` in this run.

    Returns the path to ``blueprint_learning.jsonl``. Idempotent within a run:
    if the same ``action_type_id`` appears in several unknown actions, only the
    first is logged. ``recorded_at`` (ISO 8601) is caller-supplied so the
    function stays deterministic in tests (no wall-clock reads).
    """
    log_path = _portal_dir(portal_id, base_dir) / "blueprint_learning.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for entry in unknown_actions:
        action_type_id = entry.get("action_type_id") or entry.get("actionTypeId") or ""
        if not action_type_id or action_type_id in seen:
            continue
        seen.add(action_type_id)
        fields = entry.get("value_previews") or {}
        previews = {k: _truncate(v) for k, v in fields.items()}
        records.append({
            "portal_id": str(portal_id),
            "workflow_id": str(workflow_id),
            "recorded_at": recorded_at or "",
            "action_type_id": str(action_type_id),
            "field_names": list(entry.get("field_names") or fields.keys()),
            "value_previews": previews,
            "note": entry.get("note", ""),
        })

    if not records:
        return log_path

    with log_path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return log_path
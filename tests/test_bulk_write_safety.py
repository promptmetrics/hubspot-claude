"""Bug 5b: bulk update undo.

A ``hubspot_bulk_update_objects`` call is MEDIUM risk (``.write`` scope, not
destructive), so before bug 5b the snapshot pre-fetch skipped it — the snapshot
was saved with ``undoable=True`` but empty ``original_values``, and ``undo``
failed with "No original values recorded".  These tests exercise the full
tool path: ``handle_tool`` builds the preview (pre-fetching each record's
current values), the count gate (bug 5a) guards execution, and ``undo``
restores every record via ``hubspot_update_object``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hubspot_agent.cli import hubspot_command
from hubspot_agent.config import PortalConfig, save_portal_config
from hubspot_agent.handlers import HandlerError, execute_pending_write, handle_tool


class _FakeClient:
    async def close(self):
        pass


@pytest.fixture
def portal_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
    (tmp_path / ".hubspot-portal").write_text("123\n")
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))
    return tmp_path


def _bulk_update_input() -> dict:
    return {
        "object_type": "contacts",
        "records": [
            {"id": "c-1", "properties": {"firstname": "New1"}},
            {"id": "c-2", "properties": {"firstname": "New2"}},
        ],
    }


@pytest.mark.asyncio
async def test_bulk_update_preview_captures_each_record_originals(portal_dir):
    originals = {
        "c-1": {"firstname": "Old1", "email": "a@example.com"},
        "c-2": {"firstname": "Old2", "email": "b@example.com"},
    }

    async def fake_invoke(tool_name, portal_id, **kwargs):
        if tool_name == "hubspot_get_object":
            oid = str(kwargs["object_id"])
            return {"id": oid, "properties": originals[oid]}
        return {}

    portal_config = PortalConfig(portal_id="123", token="test-token")
    with patch("hubspot_agent.handlers.invoke_tool", side_effect=fake_invoke):
        result = await handle_tool(
            _FakeClient(), None, portal_config,
            {"tool_name": "hubspot_bulk_update_objects", "input": _bulk_update_input()},
        )

    data = result["data"]
    assert data["status"] == "preview"
    assert data["required_confirmation"] == 2
    assert data["original_values"] == originals


@pytest.mark.asyncio
async def test_bulk_update_bare_approve_refused_then_exact_count_executes(portal_dir):
    originals = {"c-1": {"firstname": "Old1"}, "c-2": {"firstname": "Old2"}}

    async def fake_invoke(tool_name, portal_id, **kwargs):
        if tool_name == "hubspot_get_object":
            oid = str(kwargs["object_id"])
            return {"id": oid, "properties": originals[oid]}
        if tool_name == "hubspot_bulk_update_objects":
            return {"succeeded": 2, "failed": 0, "total": 2, "results": [], "errors": []}
        return {}

    portal_config = PortalConfig(portal_id="123", token="test-token")
    with patch("hubspot_agent.handlers.invoke_tool", side_effect=fake_invoke):
        result = await handle_tool(
            _FakeClient(), None, portal_config,
            {"tool_name": "hubspot_bulk_update_objects", "input": _bulk_update_input()},
        )
        action_id = result["data"]["action_id"]

        # Bug 5a: bare approve (no count) on a 2-record write is refused.
        with pytest.raises(Exception) as exc:
            await execute_pending_write(portal_config, action_id, confirm_count=None)
        assert "Multi-record" in str(exc.value) or "impact count" in str(exc.value)

        # Exact count executes and saves a snapshot with both records' originals.
        exec_result = await execute_pending_write(portal_config, action_id, confirm_count=2)
        assert exec_result.status == "success"

    snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
    assert snapshot_file.exists()
    snapshot = json.loads(snapshot_file.read_text())
    assert snapshot["original_values"] == originals
    assert snapshot["metadata"]["intent_type"] == "update"
    assert snapshot["metadata"]["undoable"] is True


@pytest.mark.asyncio
async def test_bulk_update_flat_records_rejected_at_preview(portal_dir):
    """Bug A (0.2.4): a mis-shaped bulk payload must fail at preview time —
    a human should never be asked to approve a doomed write, and no pending
    action may be persisted for it."""
    flat_input = {
        "object_type": "contacts",
        "records": [
            {"id": "c-1", "firstname": "New1"},  # flat: property not wrapped
            {"id": "c-2", "firstname": "New2"},
        ],
    }
    portal_config = PortalConfig(portal_id="123", token="test-token")
    with pytest.raises(HandlerError) as exc:
        await handle_tool(
            _FakeClient(), None, portal_config,
            {"tool_name": "hubspot_bulk_update_objects", "input": flat_input},
        )
    assert exc.value.error["kind"] == "validation"
    assert "properties" in str(exc.value)

    pending_dir = portal_dir / "123" / "pending_previews"
    assert not pending_dir.exists() or not any(pending_dir.iterdir())


def test_bulk_update_undo_restores_all_records(portal_dir):
    """End-to-end via the CLI: bulk update -> approve with count -> undo.

    Patches ``handlers.invoke_tool`` for the preview pre-fetch + execute, then
    ``cli.invoke_tool`` + ``HubSpotClient`` for the undo restores.
    """
    originals = {
        "c-1": {"firstname": "Old1", "email": "a@example.com"},
        "c-2": {"firstname": "Old2", "email": "b@example.com"},
    }

    async def fake_invoke(tool_name, portal_id, **kwargs):
        if tool_name == "hubspot_get_object":
            oid = str(kwargs["object_id"])
            return {"id": oid, "properties": originals[oid]}
        if tool_name == "hubspot_bulk_update_objects":
            return {"succeeded": 2, "failed": 0, "total": 2, "results": [], "errors": []}
        return {}

    portal_config = PortalConfig(portal_id="123", token="test-token")
    action_id = None
    with patch("hubspot_agent.handlers.invoke_tool", side_effect=fake_invoke):
        preview = hubspot_command(
            "tool hubspot_bulk_update_objects --input "
            + json.dumps(_bulk_update_input()),
            working_dir=str(portal_dir),
        )
        payload = json.loads(preview)
        action_id = payload["action_id"]

    # Approve with the exact count executes the bulk update (handlers.invoke_tool).
    with patch("hubspot_agent.handlers.invoke_tool", side_effect=fake_invoke):
        approved = hubspot_command(f"approve {action_id} 2", working_dir=str(portal_dir))
    assert "Approved and executed" in approved

    restore_calls: list[dict] = []

    async def fake_restore(tool_name, portal_id, **kwargs):
        if tool_name == "hubspot_update_object":
            restore_calls.append({"object_id": str(kwargs["object_id"]), "properties": kwargs["properties"]})
        return {}

    fake_client = AsyncMock()
    fake_client.close = AsyncMock()
    with patch("hubspot_agent.client.HubSpotClient", return_value=fake_client), \
         patch("hubspot_agent.cli.invoke_tool", side_effect=fake_restore):
        undone = hubspot_command(f"undo {action_id}", working_dir=str(portal_dir))

    assert "Restored 2" in undone
    assert len(restore_calls) == 2
    restored_ids = {c["object_id"] for c in restore_calls}
    assert restored_ids == {"c-1", "c-2"}
    for call in restore_calls:
        assert call["properties"] == originals[call["object_id"]]

    # A successful undo consumes the snapshot.
    assert not (portal_dir / "123" / "undo_snapshots" / f"{action_id}.json").exists()
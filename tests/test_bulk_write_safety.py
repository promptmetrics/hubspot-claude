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
        if tool_name == "hubspot_bulk_update_objects":
            return {"succeeded": 2, "failed": 0, "total": 2, "results": [], "errors": []}
        return {}

    portal_config = PortalConfig(portal_id="123", token="test-token")
    with patch("hubspot_agent.handlers.invoke_tool", side_effect=fake_invoke):
        result = await handle_tool(
            _FakeClient(), None, portal_config,
            {"tool_name": "hubspot_bulk_update_objects", "input": _bulk_update_input()},
        )

    data = result["data"]
    # Phase 2: a reversible 2-record bulk update is AUTO tier and applies
    # immediately — there is no preview envelope to inspect.
    assert data["status"] == "applied"
    action_id = data["action_id"]
    # Capture-for-undo coverage is preserved: the undo snapshot written for the
    # action_id holds EVERY record's pre-change originals (asserted on the
    # snapshot instead of the now-gone preview envelope).
    snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
    assert snapshot_file.exists()
    snapshot = json.loads(snapshot_file.read_text())
    assert snapshot["original_values"] == originals
    assert snapshot["metadata"]["intent_type"] == "update"
    assert snapshot["metadata"]["undoable"] is True


@pytest.mark.asyncio
async def test_reversible_bulk_update_auto_applies_but_destructive_still_gated(portal_dir):
    """Phase 2 contract shift + preserved count-gate coverage.

    The old Bug-5a typed-count gate for a *reversible* multi-record bulk UPDATE
    is intentionally gone: such a write is AUTO tier and applies with no count.
    The typed-count (FULL_GATE) gate now guards destructive / non-reversible
    ops, which this test still exercises via a destructive delete — bare approve
    is refused, exact count executes.  Count-gate coverage stays in this file.
    """
    originals = {"c-1": {"firstname": "Old1"}, "c-2": {"firstname": "Old2"}}

    async def fake_invoke(tool_name, portal_id, **kwargs):
        if tool_name == "hubspot_get_object":
            oid = str(kwargs["object_id"])
            return {"id": oid, "properties": originals.get(oid, {"firstname": "Old"})}
        if tool_name == "hubspot_bulk_update_objects":
            return {"succeeded": 2, "failed": 0, "total": 2, "results": [], "errors": []}
        if tool_name == "hubspot_delete_object":
            return {"id": str(kwargs.get("object_id")), "archived": True}
        return {}

    portal_config = PortalConfig(portal_id="123", token="test-token")
    with patch("hubspot_agent.handlers.invoke_tool", side_effect=fake_invoke):
        # (a) reversible 2-record bulk update AUTO-applies — no count needed.
        applied = await handle_tool(
            _FakeClient(), None, portal_config,
            {"tool_name": "hubspot_bulk_update_objects", "input": _bulk_update_input()},
        )
        assert applied["data"]["status"] == "applied"

        # (b) a destructive delete is FULL_GATE: it previews and demands a count.
        preview = await handle_tool(
            _FakeClient(), None, portal_config,
            {"tool_name": "hubspot_delete_object", "input": {"object_type": "contacts", "object_id": "c-1"}},
        )
        del_data = preview["data"]
        assert del_data["status"] == "preview"
        assert del_data["requires_count"] is True
        del_action = del_data["action_id"]

        # Bare approve (no count) on a destructive write is refused.
        with pytest.raises(Exception) as exc:
            await execute_pending_write(portal_config, del_action, confirm_count=None)
        assert "Destructive" in str(exc.value) or "impact count" in str(exc.value)
        # Gate rejected before execution — the preview is still on disk.
        assert (portal_dir / "123" / "pending_previews" / f"{del_action}.json").exists()

        # Exact count executes the destructive write.
        exec_result = await execute_pending_write(portal_config, del_action, confirm_count=1)
        assert exec_result.status == "success"


@pytest.mark.asyncio
async def test_preview_snapshot_fetch_scoped_to_changed_properties(portal_dir):
    """Bug B (0.2.4): the pre-write snapshot GET must request only the
    properties being changed, so ``original_values`` (replayed by undo) never
    carries read-only system fields.  Covers the single-update and bulk
    branches of ``_build_tool_preview``."""
    fetch_props: list[list[str] | None] = []

    async def fake_invoke(tool_name, portal_id, **kwargs):
        if tool_name == "hubspot_get_object":
            fetch_props.append(kwargs.get("properties"))
            return {"id": str(kwargs["object_id"]), "properties": {"firstname": "Old"}}
        return {}

    portal_config = PortalConfig(portal_id="123", token="test-token")
    with patch("hubspot_agent.handlers.invoke_tool", side_effect=fake_invoke):
        await handle_tool(
            _FakeClient(), None, portal_config,
            {"tool_name": "hubspot_bulk_update_objects", "input": _bulk_update_input()},
        )
        await handle_tool(
            _FakeClient(), None, portal_config,
            {
                "tool_name": "hubspot_update_object",
                "input": {"object_type": "contacts", "object_id": "c-1", "properties": {"firstname": "New"}},
            },
        )

    assert fetch_props == [["firstname"], ["firstname"], ["firstname"]]


@pytest.mark.asyncio
async def test_bulk_update_snapshot_fetch_failure_warns_and_marks_non_undoable(portal_dir):
    """Latent hardening (0.2.4): if every per-record snapshot GET fails at
    preview time, the preview must (a) surface a warning that undo will be
    unavailable and (b) mark the saved snapshot non-undoable — not persist a
    hollow ``undoable=True`` snapshot whose empty ``original_values`` the
    operator only discovers at undo time.  See ``handlers._build_tool_preview``
    (the ``except Exception: continue`` swallow) + ``snapshot.save_undo_snapshot_for_action``.
    """

    async def fake_invoke(tool_name, portal_id, **kwargs):
        if tool_name == "hubspot_get_object":
            raise RuntimeError("snapshot GET failed")
        if tool_name == "hubspot_bulk_update_objects":
            return {"succeeded": 2, "failed": 0, "total": 2, "results": [], "errors": []}
        return {}

    portal_config = PortalConfig(portal_id="123", token="test-token")
    with patch("hubspot_agent.handlers.invoke_tool", side_effect=fake_invoke):
        result = await handle_tool(
            _FakeClient(), None, portal_config,
            {"tool_name": "hubspot_bulk_update_objects", "input": _bulk_update_input()},
        )
        data = result["data"]
        assert data["status"] == "preview"
        # No originals captured — every per-record GET raised.
        assert data["original_values"] == {}
        # The warning surfaces at PREVIEW time, not undo time.
        assert "warning" in data["preview"]
        assert "undo" in data["preview"]["warning"].lower()

        action_id = data["action_id"]
        exec_result = await execute_pending_write(portal_config, action_id, confirm_count=2)
        assert exec_result.status == "success"

    snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
    assert snapshot_file.exists()
    snapshot = json.loads(snapshot_file.read_text())
    assert snapshot["original_values"] == {}
    assert snapshot["metadata"]["intent_type"] == "update"
    # Fail-closed: an update with no captured originals must not claim undoability.
    assert snapshot["metadata"]["undoable"] is False


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
    """End-to-end via the CLI: bulk update AUTO-applies -> undo.

    Phase 2: a reversible 2-record bulk update is AUTO tier, so the ``tool``
    command executes immediately (capturing the undo snapshot on the way) —
    there is no separate ``approve`` step.  Undo must still restore every
    record from the captured snapshot, so undo coverage is preserved.

    Patches ``handlers.invoke_tool`` for the preview pre-fetch + auto-execute,
    then ``cli.invoke_tool`` + ``HubSpotClient`` for the undo restores.
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
        applied = hubspot_command(
            "tool hubspot_bulk_update_objects --input "
            + json.dumps(_bulk_update_input()),
            working_dir=str(portal_dir),
        )
        payload = json.loads(applied)
        # AUTO-applied in one shot (no approve): the bulk update ran now.
        assert payload["status"] == "applied"
        action_id = payload["action_id"]

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
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hubspot_agent.cli import hubspot_command
from hubspot_agent.config import PortalConfig, save_portal_config
from hubspot_agent.snapshot import save_undo_snapshot


@pytest.fixture
def portal_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))
    return tmp_path


@pytest.fixture
def mock_client():
    client = AsyncMock()
    with patch("hubspot_agent.client.HubSpotClient", return_value=client):
        yield client


@pytest.fixture
def mock_invoke_tool():
    with patch("hubspot_agent.cli.invoke_tool") as mock:
        yield mock


def test_undo_update_reapplies_original_values(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "upd-1",
        {"1": {"email": "old@example.com"}, "2": {"email": "also@example.com"}},
        metadata={"intent_type": "update", "target_object": "contacts", "undoable": True},
    )

    result = hubspot_command("undo upd-1", working_dir=str(portal_dir))

    assert "Restored 2" in result
    calls = mock_invoke_tool.call_args_list
    assert len(calls) == 2
    for call in calls:
        assert call.kwargs["object_type"] == "contacts"
        assert call.kwargs["object_id"] in {"1", "2"}


def test_undo_create_deletes_created_records(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "crt-1",
        {},
        metadata={
            "intent_type": "create",
            "target_object": "contacts",
            "undoable": True,
            "created_ids": ["101", "102"],
        },
    )

    result = hubspot_command("undo crt-1", working_dir=str(portal_dir))

    assert "Deleted 2" in result
    calls = mock_invoke_tool.call_args_list
    assert len(calls) == 2
    ids = {call.kwargs["object_id"] for call in calls}
    assert ids == {"101", "102"}


def test_undo_delete_returns_not_undoable(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "del-1",
        {},
        metadata={"intent_type": "delete", "target_object": "contacts", "undoable": False},
    )

    result = hubspot_command("undo del-1", working_dir=str(portal_dir))

    assert "not undoable" in result.lower()
    mock_invoke_tool.assert_not_called()


# ---------------------------------------------------------------------------
# M13: a failed undo must keep the snapshot (only reconciliation artifact) and
# must not write an `undo:<id>` audit entry for an undo that never happened.
# ---------------------------------------------------------------------------


def test_failed_undo_keeps_snapshot_and_skips_audit(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "del-1",
        {},
        metadata={"intent_type": "delete", "target_object": "contacts", "undoable": False},
    )

    result = hubspot_command("undo del-1", working_dir=str(portal_dir))

    assert "not undoable" in result.lower()
    assert (portal_dir / "123" / "undo_snapshots" / "del-1.json").exists()
    audit_file = Path.home() / ".claude" / "hubspot" / "123" / "audit.log"
    assert not audit_file.exists() or "undo:del-1" not in audit_file.read_text()


def test_successful_undo_deletes_snapshot_and_audits(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "upd-9",
        {"1": {"email": "old@example.com"}},
        metadata={"intent_type": "update", "target_object": "contacts", "undoable": True},
    )

    result = hubspot_command("undo upd-9", working_dir=str(portal_dir))

    assert "Restored 1" in result
    assert not (portal_dir / "123" / "undo_snapshots" / "upd-9.json").exists()
    audit_file = Path.home() / ".claude" / "hubspot" / "123" / "audit.log"
    assert audit_file.exists() and "undo:upd-9" in audit_file.read_text()


def test_undo_merge_snapshot_not_undoable_and_survives(portal_dir, mock_client, mock_invoke_tool):
    # M5: merge snapshots exist for manual reconciliation; undo must refuse
    # and leave the artifact in place.
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "mrg-1",
        {"1": {"email": "primary@example.com"}, "2": {"email": "dup@example.com"}},
        metadata={"intent_type": "merge", "target_object": "contacts", "undoable": False},
    )

    result = hubspot_command("undo mrg-1", working_dir=str(portal_dir))

    assert "not undoable" in result.lower()
    mock_invoke_tool.assert_not_called()
    assert (portal_dir / "123" / "undo_snapshots" / "mrg-1.json").exists()


# ---------------------------------------------------------------------------
# Bug B (0.2.4): undo said "Restored" while restoring nothing.  Two defects:
# the restore payload replayed the ENTIRE snapshot dict including read-only
# system fields (hs_lastmodifieddate, hs_object_id, createdate) which HubSpot
# 400s on, and the invoke_tool error envelope was discarded so the failure was
# swallowed, the user told the restore happened, and the snapshot (the only
# reconciliation artifact) deleted.
# ---------------------------------------------------------------------------


def test_undo_update_failure_reports_and_keeps_snapshot(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "upd-f1",
        {"1": {"email": "old@example.com"}},
        metadata={"intent_type": "update", "target_object": "contacts", "undoable": True},
    )
    mock_invoke_tool.return_value = {
        "error": "HubSpot API error 400: property is read-only",
        "tool": "hubspot_update_object",
    }

    result = hubspot_command("undo upd-f1", working_dir=str(portal_dir))

    assert "Restored 1 contacts" not in result
    assert "❌" in result
    assert "read-only" in result
    assert (portal_dir / "123" / "undo_snapshots" / "upd-f1.json").exists()
    audit_file = Path.home() / ".claude" / "hubspot" / "123" / "audit.log"
    assert not audit_file.exists() or "undo:upd-f1" not in audit_file.read_text()


def test_undo_update_partial_failure_keeps_snapshot(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "upd-p1",
        {"1": {"email": "old@example.com"}, "2": {"email": "also@example.com"}},
        metadata={"intent_type": "update", "target_object": "contacts", "undoable": True},
    )
    mock_invoke_tool.side_effect = [
        {"id": "1"},
        {"error": "HubSpot API error 500: boom", "tool": "hubspot_update_object"},
    ]

    result = hubspot_command("undo upd-p1", working_dir=str(portal_dir))

    assert "1 of 2" in result
    assert "❌" in result
    # Both records were attempted (maximize restoration before reporting).
    assert len(mock_invoke_tool.call_args_list) == 2
    assert (portal_dir / "123" / "undo_snapshots" / "upd-p1.json").exists()
    audit_file = Path.home() / ".claude" / "hubspot" / "123" / "audit.log"
    assert not audit_file.exists() or "undo:upd-p1" not in audit_file.read_text()


def test_undo_strips_read_only_properties(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "upd-ro",
        {
            "1": {
                "email": "old@example.com",
                "hs_lastmodifieddate": "2026-07-14T13:19:48.902Z",
                "createdate": "2026-07-14T13:19:29.918Z",
                "hs_object_id": "1",
            }
        },
        metadata={"intent_type": "update", "target_object": "contacts", "undoable": True},
    )
    mock_invoke_tool.return_value = {"id": "1"}

    result = hubspot_command("undo upd-ro", working_dir=str(portal_dir))

    assert "Restored 1" in result
    call = mock_invoke_tool.call_args_list[0]
    assert call.kwargs["properties"] == {"email": "old@example.com"}
    assert not (portal_dir / "123" / "undo_snapshots" / "upd-ro.json").exists()


def test_undo_create_delete_404_treated_as_already_gone(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "crt-404",
        {},
        metadata={
            "intent_type": "create",
            "target_object": "contacts",
            "undoable": True,
            "created_ids": ["101", "102"],
        },
    )
    mock_invoke_tool.side_effect = [
        {"error": "HubSpot API error 404: Not Found", "tool": "hubspot_delete_object"},
        {},
    ]

    result = hubspot_command("undo crt-404", working_dir=str(portal_dir))

    assert "Deleted 2" in result
    assert not (portal_dir / "123" / "undo_snapshots" / "crt-404.json").exists()


def test_undo_create_delete_failure_keeps_snapshot(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "crt-f1",
        {},
        metadata={
            "intent_type": "create",
            "target_object": "contacts",
            "undoable": True,
            "created_ids": ["101", "102"],
        },
    )
    mock_invoke_tool.side_effect = [
        {"error": "HubSpot API error 500: boom", "tool": "hubspot_delete_object"},
        {},
    ]

    result = hubspot_command("undo crt-f1", working_dir=str(portal_dir))

    assert "❌" in result
    assert (portal_dir / "123" / "undo_snapshots" / "crt-f1.json").exists()


def test_undo_list_shows_actions(portal_dir):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "upd-1",
        {"1": {"email": "old@example.com"}},
        metadata={"intent_type": "update", "target_object": "contacts", "undoable": True},
    )
    save_undo_snapshot(
        snapshot_dir,
        "del-1",
        {},
        metadata={"intent_type": "delete", "target_object": "contacts", "undoable": False},
    )

    result = hubspot_command("undo list", working_dir=str(portal_dir))

    assert "upd-1" in result
    assert "del-1" in result
    assert "undoable" in result
    assert "not undoable" in result

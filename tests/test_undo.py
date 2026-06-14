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

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
    with patch("hubspot_agent.cli.invoke_tool"):
        yield


def test_undo_action_is_logged_to_audit(portal_dir, mock_client, mock_invoke_tool):
    snapshot_dir = str(portal_dir / "123" / "undo_snapshots")
    save_undo_snapshot(
        snapshot_dir,
        "upd-1",
        {"1": {"email": "old@example.com"}},
        metadata={"intent_type": "update", "target_object": "contacts", "undoable": True},
    )

    hubspot_command("undo upd-1", working_dir=str(portal_dir))

    audit_file = portal_dir / ".claude" / "hubspot" / "123" / "audit.log"
    assert audit_file.exists()
    lines = audit_file.read_text().strip().splitlines()
    assert len(lines) >= 1
    entry = json.loads(lines[-1])
    assert entry["action"] == "undo:upd-1"
    assert entry["agent"] == "update"

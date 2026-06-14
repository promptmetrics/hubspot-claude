import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hubspot_agent.cli import hubspot_command
from hubspot_agent.config import PortalConfig, save_portal_config
from hubspot_agent.models import AgentResult, RiskLevel
from hubspot_agent.persistence import load as _load_pending_preview
from hubspot_agent.persistence import store as _store_pending_preview
from hubspot_agent.validation import validate_scopes


_REQUIRED_SCOPES = {
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.contacts.delete",
}


@pytest.fixture
def portal_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.audit._audit_file_path", lambda pid: tmp_path / "audit.log")
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    save_portal_config(
        PortalConfig(
            portal_id="123",
            token="test-token",
            tier="Professional",
            scopes_granted=sorted(_REQUIRED_SCOPES),
        )
    )
    async def noop_initialize(portal_id):
        return None

    async def ready_readiness(*args, **kwargs):
        return {"ready": True}

    monkeypatch.setattr("hubspot_agent.cli.initialize_session", noop_initialize)
    monkeypatch.setattr("hubspot_agent.cli.check_dispatch_readiness", ready_readiness)
    return tmp_path


@pytest.fixture
def mock_client():
    from unittest.mock import AsyncMock

    client = AsyncMock()
    with patch("hubspot_agent.client.HubSpotClient", return_value=client):
        yield client


def test_scope_validation_blocks_and_allows_delete():
    """Scope validation runs before any preview or execute work."""
    blocked = validate_scopes(["objects"], ["crm.objects.contacts.read"], target_object="contacts")
    assert "objects" in blocked
    assert any("delete" in s for s in blocked["objects"])

    allowed = validate_scopes(["objects"], sorted(_REQUIRED_SCOPES), target_object="contacts")
    assert not allowed


def test_delete_list_full_hitl_flow(portal_dir, mock_client):
    """End-to-end acceptance: destructive bulk update with count gate and undo."""
    action_id = "del-list-1"
    request_text = "delete all contacts in the Test list"

    original_values = {
        f"c{i}": {"email": f"c{i}@example.com", "firstname": f"Contact {i}"}
        for i in range(5)
    }

    preview_data = {
        "agent_name": "objects",
        "request_text": request_text,
        "intent": {
            "intent_type": "update",
            "target_object": "contacts",
            "description": request_text,
            "risk_level": RiskLevel.DESTRUCTIVE.value,
            "estimated_impact": 5,
            "required_scopes": [],
        },
        "preview": {
            "preview": {"records": [{"id": f"c{i}"} for i in range(5)]},
            "impact_count": 5,
            "risk_level": RiskLevel.DESTRUCTIVE.value,
            "proposed_payload": {},
            "original_values": original_values,
        },
        "trace_id": "trace-del-list",
        "batch_mode": "single",
        "proposed_payload": {},
        "required_confirmation": 5,
        "confirmed_count": None,
    }

    preview_result = AgentResult(
        agent_name="objects",
        status="preview",
        data={
            "action_id": action_id,
            "preview": "Will remove 5 contacts from the Test list",
            "risk_level": RiskLevel.DESTRUCTIVE.value,
            "impact_type": "update",
            "target_object": "contacts",
            "impact_count": 5,
            "original_values": original_values,
        },
    )

    async def mock_dispatch_parallel(*args, **kwargs):
        _store_pending_preview("123", action_id, preview_data)
        return [preview_result]

    async def mock_dispatch_agent(*args, **kwargs):
        return AgentResult(
            agent_name="objects",
            status="success",
            data={"message": "Removed 5 contacts from the Test list."},
        )

    with patch("hubspot_agent.cli.dispatch_agents_parallel", side_effect=mock_dispatch_parallel):
        with patch("hubspot_agent.cli.dispatch_agent", side_effect=mock_dispatch_agent):
            with patch("hubspot_agent.cli.invoke_tool") as mock_invoke_tool:
                # Step 1: preview shows destructive impact of 5 records.
                result1 = hubspot_command(request_text, working_dir=str(portal_dir))
                assert "Portal: 123" in result1
                assert "destructive" in result1.lower()
                assert "5" in result1
                assert action_id in result1
                assert _load_pending_preview("123", action_id) is not None

                # Step 2: simple approval is rejected for destructive operations.
                result2 = hubspot_command("y", working_dir=str(portal_dir))
                assert "destructive" in result2.lower()
                assert "5" in result2
                assert action_id in result2

                # Step 3: exact impact count is accepted and executes.
                result3 = hubspot_command("5", working_dir=str(portal_dir))
                assert "Approved and executed" in result3
                assert _load_pending_preview("123", action_id) is None

                # Step 4: undo snapshot is saved with original values.
                snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
                assert snapshot_file.exists()
                snapshot = json.loads(snapshot_file.read_text())
                assert snapshot["original_values"] == original_values
                assert snapshot["metadata"]["intent_type"] == "update"
                assert snapshot["metadata"]["target_object"] == "contacts"
                assert snapshot["metadata"]["undoable"] is True

                # Step 5: undo restores the 5 contacts from the snapshot.
                result4 = hubspot_command(f"undo {action_id}", working_dir=str(portal_dir))
                assert "Restored 5" in result4
                calls = mock_invoke_tool.call_args_list
                assert len(calls) == 5
                restored_ids = {call.kwargs["object_id"] for call in calls}
                assert restored_ids == set(original_values.keys())
                for call in calls:
                    assert call.kwargs["object_type"] == "contacts"

                # Undo snapshot is consumed after use.
                assert not snapshot_file.exists()

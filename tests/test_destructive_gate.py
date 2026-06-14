from pathlib import Path
from unittest.mock import patch

import pytest

from hubspot_agent.cli import (
    _is_destructive_preview,
    _present_destructive_preview,
    hubspot_command,
)
from hubspot_agent.config import PortalConfig, save_portal_config
from hubspot_agent.models import AgentResult
from hubspot_agent.persistence import store as _store_pending_preview


def _destructive_preview_data(impact_count: int = 5) -> dict:
    return {
        "agent_name": "objects",
        "request_text": "delete all contacts in the Test list",
        "intent": {
            "intent_type": "delete",
            "target_object": "contacts",
            "description": "delete all contacts in the Test list",
            "risk_level": "destructive",
            "estimated_impact": impact_count,
            "required_scopes": [],
        },
        "preview": {
            "preview": {"records": [{"id": f"c{i}"} for i in range(impact_count)]},
            "impact_count": impact_count,
            "risk_level": "destructive",
            "proposed_payload": {},
            "original_values": {f"c{i}": {"email": f"c{i}@example.com"} for i in range(impact_count)},
        },
        "trace_id": "trace-1",
        "batch_mode": "single",
        "proposed_payload": {},
        "required_confirmation": impact_count,
        "confirmed_count": None,
    }


@pytest.fixture
def portal_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.cli.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    save_portal_config(PortalConfig(portal_id="123", token="test-token"))
    return tmp_path


def test_is_destructive_preview_true_for_destructive_risk():
    data = _destructive_preview_data()
    assert _is_destructive_preview(data) is True


def test_is_destructive_preview_false_for_medium_risk():
    data = _destructive_preview_data()
    data["preview"]["risk_level"] = "medium"
    data["intent"]["risk_level"] = "medium"
    assert _is_destructive_preview(data) is False


def test_present_destructive_preview_shows_impact_count_and_commands():
    text = _present_destructive_preview("abc123", 5)
    assert "5" in text
    assert "approve abc123 5" in text
    assert "confirm 5" in text


def test_simple_y_rejected_for_destructive_preview(portal_dir):
    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    result = hubspot_command("y", working_dir=str(portal_dir))
    assert "destructive" in result.lower()
    assert "approve abc123 5" in result


def test_approve_with_wrong_count_rejected(portal_dir):
    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    result = hubspot_command(f"approve {action_id} 3", working_dir=str(portal_dir))
    assert "destructive" in result.lower()
    assert "approve abc123 5" in result


def test_approve_with_exact_count_executes(portal_dir):
    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(
            agent_name="objects",
            status="success",
            data={"message": "deleted 5 contacts"},
        )

    with patch("hubspot_agent.cli.dispatch_agent", side_effect=fake_dispatch):
        result = hubspot_command(f"approve {action_id} 5", working_dir=str(portal_dir))

    assert "Approved and executed" in result
    snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
    assert snapshot_file.exists()


def test_confirm_command_with_exact_count_executes(portal_dir):
    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(
            agent_name="objects",
            status="success",
            data={"message": "deleted 5 contacts"},
        )

    with patch("hubspot_agent.cli.dispatch_agent", side_effect=fake_dispatch):
        result = hubspot_command("5", working_dir=str(portal_dir))

    assert "Approved and executed" in result


def test_non_destructive_y_still_approves(portal_dir):
    action_id = "abc123"
    data = _destructive_preview_data(1)
    data["preview"]["risk_level"] = "medium"
    data["intent"]["risk_level"] = "medium"
    data["required_confirmation"] = 1
    _store_pending_preview("123", action_id, data)

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(
            agent_name="objects",
            status="success",
            data={"message": "updated contact"},
        )

    with patch("hubspot_agent.cli.dispatch_agent", side_effect=fake_dispatch):
        result = hubspot_command("y", working_dir=str(portal_dir))

    assert "Approved and executed" in result

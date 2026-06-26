import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hubspot_agent.cli import hubspot_command
from hubspot_agent.config import PortalConfig, save_portal_config
from hubspot_agent.models import AgentResult, LoopPlan, PlanStep, RiskLevel
from hubspot_agent.persistence import store as _store_pending_preview
from hubspot_agent.sequential_dispatch import execute_plan


def _preview_data(intent_type: str, risk_level: str, impact_count: int, original_values: dict) -> dict:
    return {
        "agent_name": "objects",
        "request_text": f"{intent_type} contact",
        "intent": {
            "intent_type": intent_type,
            "target_object": "contacts",
            "description": f"{intent_type} contact",
            "risk_level": risk_level,
            "estimated_impact": impact_count,
            "required_scopes": [],
        },
        "preview": {
            "preview": {},
            "impact_count": impact_count,
            "risk_level": risk_level,
            "proposed_payload": {},
            "original_values": original_values,
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


def test_approve_update_saves_original_values_snapshot(portal_dir):
    action_id = "upd-1"
    _store_pending_preview(
        "123", action_id, _preview_data("update", "medium", 2, {"1": {"email": "old@example.com"}})
    )

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(agent_name="objects", status="success", data={"message": "updated"})

    with patch("hubspot_agent.orchestrator.dispatch_agent", side_effect=fake_dispatch):
        hubspot_command(f"approve {action_id}", working_dir=str(portal_dir))

    snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
    assert snapshot_file.exists()
    snapshot = json.loads(snapshot_file.read_text())
    assert snapshot["original_values"] == {"1": {"email": "old@example.com"}}
    assert snapshot["metadata"]["intent_type"] == "update"
    assert snapshot["metadata"]["undoable"] is True


def test_approve_create_saves_empty_snapshot_with_metadata(portal_dir):
    action_id = "crt-1"
    _store_pending_preview(
        "123", action_id, _preview_data("create", "medium", 1, {})
    )

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(
            agent_name="objects",
            status="success",
            data={"result": {"id": "contact-999"}},
        )

    with patch("hubspot_agent.orchestrator.dispatch_agent", side_effect=fake_dispatch):
        hubspot_command(f"approve {action_id}", working_dir=str(portal_dir))

    snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
    assert snapshot_file.exists()
    snapshot = json.loads(snapshot_file.read_text())
    assert snapshot["original_values"] == {}
    assert snapshot["metadata"]["intent_type"] == "create"
    assert snapshot["metadata"]["created_ids"] == ["contact-999"]


@pytest.mark.asyncio
async def test_execute_plan_saves_snapshot_for_write_step(portal_dir):
    plan = LoopPlan(
        goal="Update a contact",
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="update contact",
                risk_level=RiskLevel.MEDIUM,
            )
        ],
        overall_risk=RiskLevel.MEDIUM,
    )

    portal_config = PortalConfig(portal_id="123", token="test-token")

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        if mode == "preview":
            return AgentResult(
                agent_name="objects",
                status="preview",
                data={
                    "action_id": "act-1",
                    "risk_level": "medium",
                    "impact_count": 1,
                    "proposed_payload": {},
                    "original_values": {"42": {"email": "old@example.com"}},
                    "intent_type": "update",
                    "target_object": "contacts",
                },
            )
        return AgentResult(agent_name="objects", status="success", data={"message": "updated"})

    with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
        await execute_plan(plan, "update contact", portal_config, "trace-1")

    snapshot_file = portal_dir / ".claude" / "hubspot" / "123" / "undo_snapshots" / "act-1.json"
    assert snapshot_file.exists()
    snapshot = json.loads(snapshot_file.read_text())
    assert snapshot["original_values"] == {"42": {"email": "old@example.com"}}

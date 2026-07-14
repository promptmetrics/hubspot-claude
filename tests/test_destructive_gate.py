import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hubspot_agent import cli
from hubspot_agent.cli import (
    _is_destructive_preview,
    _present_destructive_preview,
    hubspot_command,
)
from hubspot_agent.config import PortalConfig, save_portal_config
from hubspot_agent.models import AgentResult
from hubspot_agent.persistence import (
    load as _load_pending_preview,
    store as _store_pending_preview,
)


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
    payload = json.loads(result)
    # FR-19 / NFR-15: wrong count → stable error shape + guidance.
    assert payload["error"]["kind"] == "validation"
    assert payload["error"]["retryable"] is False
    assert "approve abc123 5" in payload["error"]["guidance"]


def test_approve_destructive_without_count_rejected(portal_dir):
    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    result = hubspot_command(f"approve {action_id}", working_dir=str(portal_dir))
    payload = json.loads(result)
    assert payload["error"]["kind"] == "validation"
    assert payload["error"]["retryable"] is False
    assert "approve abc123 5" in payload["error"]["guidance"]
    # The pending preview must still be present (no execution, no clear).
    assert _load_pending_preview("123", action_id) is not None


def test_reject_by_id_clears_pending(portal_dir):
    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    result = hubspot_command(f"reject {action_id}", working_dir=str(portal_dir))
    assert "Rejected preview abc123" in result
    assert _load_pending_preview("123", action_id) is None


def test_reject_unknown_id(portal_dir):
    result = hubspot_command("reject nope0000", working_dir=str(portal_dir))
    assert "No pending preview found with ID nope0000" in result


def test_approve_with_exact_count_executes(portal_dir):
    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(
            agent_name="objects",
            status="success",
            data={"message": "deleted 5 contacts"},
        )

    with patch("hubspot_agent.orchestrator.dispatch_agent", side_effect=fake_dispatch):
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

    with patch("hubspot_agent.orchestrator.dispatch_agent", side_effect=fake_dispatch) as mock_dispatch:
        result = hubspot_command("5", working_dir=str(portal_dir))

    assert "Approved and executed" in result
    mock_dispatch.assert_called_once()
    snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
    assert snapshot_file.exists()


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

    with patch("hubspot_agent.orchestrator.dispatch_agent", side_effect=fake_dispatch) as mock_dispatch:
        result = hubspot_command("y", working_dir=str(portal_dir))

    assert "Approved and executed" in result
    mock_dispatch.assert_called_once()
    snapshot_file = portal_dir / "123" / "undo_snapshots" / f"{action_id}.json"
    assert snapshot_file.exists()


# ---------------------------------------------------------------------------
# Bug 8f: a refused write (wrong/missing destructive count) exits 2 while the
# JSON error still prints on stdout; successful previews/reads stay 0.
# ---------------------------------------------------------------------------


def test_router_approve_wrong_count_exits_2_with_json(portal_dir, capsys):
    from hubspot_agent import router

    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    rc = router.route(["--working-dir", str(portal_dir), "approve", action_id, "3"])
    assert rc == 2
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["error"]["kind"] == "validation"


def test_router_approve_bare_destructive_exits_2(portal_dir, capsys):
    from hubspot_agent import router

    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    rc = router.route(["--working-dir", str(portal_dir), "approve", action_id])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["kind"] == "validation"


def test_router_approve_exact_count_exits_0(portal_dir, capsys):
    from hubspot_agent import router

    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(
            agent_name="objects", status="success", data={"message": "deleted 5"}
        )

    with patch("hubspot_agent.orchestrator.dispatch_agent", side_effect=fake_dispatch):
        rc = router.route(["--working-dir", str(portal_dir), "approve", action_id, "5"])
    assert rc == 0
    assert "Approved and executed" in capsys.readouterr().out


def test_cli_main_approve_wrong_count_exits_2(portal_dir, monkeypatch, capsys):
    import sys

    action_id = "abc123"
    _store_pending_preview("123", action_id, _destructive_preview_data(5))

    monkeypatch.setattr(
        sys, "argv", ["hubspot", "--working-dir", str(portal_dir), "approve", action_id, "3"]
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["kind"] == "validation"


# ---------------------------------------------------------------------------
# Bug 5a: a MEDIUM-risk multi-record write (e.g. bulk update, required > 1)
# is not destructive, so the old gate let it be bare-approved against N records
# with no count.  The gate now fires for destructive OR required > 1.
# ---------------------------------------------------------------------------


def _bulk_preview_data(impact_count: int = 3) -> dict:
    data = _destructive_preview_data(impact_count)
    # A bulk update is medium risk, not destructive, but still multi-record.
    data["intent"]["intent_type"] = "update"
    data["intent"]["risk_level"] = "medium"
    data["intent"]["description"] = "bulk update contacts"
    data["preview"]["risk_level"] = "medium"
    return data


def test_bulk_bare_approve_refused(portal_dir):
    action_id = "blk1"
    _store_pending_preview("123", action_id, _bulk_preview_data(3))

    result = hubspot_command(f"approve {action_id}", working_dir=str(portal_dir))
    payload = json.loads(result)
    assert payload["error"]["kind"] == "validation"
    assert "Multi-record" in payload["error"]["message"]
    assert f"approve {action_id} 3" in payload["error"]["guidance"]
    # Not executed — pending still present.
    assert _load_pending_preview("123", action_id) is not None


def test_bulk_wrong_count_refused(portal_dir):
    action_id = "blk1"
    _store_pending_preview("123", action_id, _bulk_preview_data(3))

    result = hubspot_command(f"approve {action_id} 2", working_dir=str(portal_dir))
    payload = json.loads(result)
    assert payload["error"]["kind"] == "validation"
    assert "impact is 3" in payload["error"]["message"]


def test_bulk_exact_count_executes(portal_dir):
    action_id = "blk1"
    _store_pending_preview("123", action_id, _bulk_preview_data(3))

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(agent_name="objects", status="success", data={"message": "updated 3"})

    with patch("hubspot_agent.orchestrator.dispatch_agent", side_effect=fake_dispatch):
        result = hubspot_command(f"approve {action_id} 3", working_dir=str(portal_dir))
    assert "Approved and executed" in result
    assert (portal_dir / "123" / "undo_snapshots" / f"{action_id}.json").exists()


def test_bare_yes_prompts_for_count_on_bulk_preview(portal_dir):
    action_id = "blk1"
    _store_pending_preview("123", action_id, _bulk_preview_data(3))

    result = hubspot_command("y", working_dir=str(portal_dir))
    # Not executed — the bare yes shows the multi-record count prompt instead.
    assert "**3**" in result
    assert f"approve {action_id} 3" in result
    assert "Approved and executed" not in result


def test_confirm_wrong_count_prompts_on_bulk_preview(portal_dir):
    action_id = "blk1"
    _store_pending_preview("123", action_id, _bulk_preview_data(3))

    result = hubspot_command("confirm 2", working_dir=str(portal_dir))
    assert "**3**" in result
    assert "Approved and executed" not in result


def test_confirm_exact_count_executes_on_bulk_preview(portal_dir):
    action_id = "blk1"
    _store_pending_preview("123", action_id, _bulk_preview_data(3))

    async def fake_dispatch(*args, **kwargs):
        return AgentResult(agent_name="objects", status="success", data={"message": "updated 3"})

    with patch("hubspot_agent.orchestrator.dispatch_agent", side_effect=fake_dispatch) as mock_dispatch:
        result = hubspot_command("confirm 3", working_dir=str(portal_dir))
    assert "Approved and executed" in result
    mock_dispatch.assert_called_once()


def test_router_bulk_bare_approve_exits_2(portal_dir, capsys):
    from hubspot_agent import router

    action_id = "blk1"
    _store_pending_preview("123", action_id, _bulk_preview_data(3))

    rc = router.route(["--working-dir", str(portal_dir), "approve", action_id])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["kind"] == "validation"

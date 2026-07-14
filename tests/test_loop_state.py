from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from hubspot_agent.loop_state import LoopState, clear, is_stale, load, save
from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel, StepArtifact


def _make_plan() -> LoopPlan:
    return LoopPlan(
        goal="Test goal",
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="create",
                description="Create a contact",
                risk_level=RiskLevel.MEDIUM,
            ),
        ],
    )


def _make_state() -> LoopState:
    return LoopState(
        portal_id="12345678",
        request_text="create a contact",
        trace_id="trace-1",
        plan=_make_plan(),
        status="running",
    )


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", tmp_path / ".claude" / "hubspot")
    yield


def test_to_dict_roundtrip():
    state = _make_state()
    data = state.to_dict()
    assert data["portal_id"] == "12345678"
    assert data["status"] == "running"
    assert data["current_step"] == 0
    assert data["iterations"] == 0


def test_from_dict_roundtrip():
    state = _make_state()
    restored = LoopState.from_dict(state.to_dict())
    assert restored.portal_id == state.portal_id
    assert restored.request_text == state.request_text
    assert restored.plan.goal == state.plan.goal
    assert restored.plan.steps[0].agent == "objects"
    assert restored.status == state.status


def test_save_and_load():
    state = _make_state()
    path = save(state)
    assert path.exists()
    loaded = load("12345678")
    assert loaded is not None
    assert loaded.request_text == "create a contact"
    assert loaded.trace_id == "trace-1"
    assert loaded.plan.goal == "Test goal"


def test_load_missing_returns_none():
    assert load("99999999") is None


def test_clear_removes_state():
    state = _make_state()
    save(state)
    clear("12345678")
    assert load("12345678") is None


def test_is_stale():
    state = _make_state()
    state.updated_at = datetime.now(timezone.utc) - timedelta(hours=3)
    assert is_stale(state) is True
    assert is_stale(state, max_age_hours=4) is False


def test_pending_action_id_roundtrip():
    state = _make_state()
    state.status = "awaiting_approval"
    state.pending_action_id = "abc12345"
    restored = LoopState.from_dict(state.to_dict())
    assert restored.pending_action_id == "abc12345"
    assert restored.status == "awaiting_approval"


def test_pending_action_id_defaults_none_on_legacy_state():
    # A state dict written before pending_action_id existed still loads.
    data = _make_state().to_dict()
    data.pop("pending_action_id")
    restored = LoopState.from_dict(data)
    assert restored.pending_action_id is None


@pytest.mark.parametrize("status", ["awaiting_approval", "awaiting_verification"])
def test_human_wait_states_never_stale(status):
    # A loop parked on a human decision must survive the 2h reaper — clearing it
    # would drop an already-previewed (or already-executed) write.
    state = _make_state()
    state.status = status
    state.updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
    assert is_stale(state) is False


def test_running_state_still_goes_stale():
    state = _make_state()
    state.status = "running"
    state.updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
    assert is_stale(state) is True


def test_save_updates_timestamp():
    state = _make_state()
    state.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    before = state.updated_at
    save(state)
    loaded = load("12345678")
    assert loaded is not None
    assert loaded.updated_at > before


def test_save_preserves_artifacts():
    state = _make_state()
    state.artifacts.append(
        StepArtifact(step_number=1, agent="objects", outputs={"id": "123"})
    )
    save(state)
    loaded = load("12345678")
    assert loaded is not None
    assert len(loaded.artifacts) == 1
    assert loaded.artifacts[0].outputs["id"] == "123"


def test_save_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", tmp_path / ".claude" / "hubspot")
    state = _make_state()
    save(state)
    leftover_tmp = list((tmp_path / ".claude" / "hubspot" / "12345678").glob("loop-state-*.tmp"))
    assert len(leftover_tmp) == 0


def test_load_corrupt_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", tmp_path / ".claude" / "hubspot")
    state_dir = tmp_path / ".claude" / "hubspot" / "12345678"
    state_dir.mkdir(parents=True)
    (state_dir / "loop-state.json").write_text("not json")
    assert load("12345678") is None

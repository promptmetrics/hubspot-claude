"""PR 2 / bug 2: the durable-loop verbatim tool path.

A loop step may carry ``tool_name`` + ``tool_input`` so the loop executes the
exact payload through ``handle_tool`` instead of free-text agent dispatch
(which fuzzy-matched ``records[0]`` and could write the wrong record).  These
tests cover: the intent-regex stopgap (``\\b``-anchored, search→delete→update
→create priority), ``parse_plan``/``validate_plan`` round-trip and rejections,
the headline end-to-end (adversarial text + verbatim tool step → pending record
persists the payload verbatim → ``execute_pending_write`` replays it exactly and
never re-searches), destructive-count gating, ``{{artifact_key}}`` placeholder
chaining, and backward-compat for legacy text-only plans.
"""
from __future__ import annotations

import json

import pytest

import hubspot_agent.agents  # noqa: F401 — populate the @tool registry for get_tool()
from hubspot_agent import loop_state
from hubspot_agent.config import PortalConfig
from hubspot_agent.handlers import ExecuteError, execute_pending_write
from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel
from hubspot_agent.orchestrator import _parse_agent_intent, run_loop
from hubspot_agent.persistence import load as load_pending
from hubspot_agent.planning import parse_plan, validate_plan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _portal() -> PortalConfig:
    return PortalConfig(portal_id="123", token="test-token", tier="Professional")


@pytest.fixture
def loop_dirs(tmp_path, monkeypatch):
    """Redirect every on-disk root the loop + safety path touches to one temp tree."""
    root = tmp_path / ".claude" / "hubspot"
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", root)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", root)
    # snapshot.snapshot_dir_for_portal reads config.CONFIG_DIR lazily, so the
    # config redirect above already covers undo-snapshot writes.
    return root


class _FakeClient:
    """Stand-in client; real I/O is short-circuited by patching ``invoke_tool``."""

    async def close(self):
        return None


def _patch_invoke_tool(monkeypatch, recorder: list[dict]):
    """Replace ``handlers.invoke_tool`` with a recorder returning canned payloads."""

    async def _fake(tool_name, portal_id, **kwargs):
        call = {"tool": tool_name, "portal_id": portal_id, "kwargs": dict(kwargs)}
        recorder.append(call)
        if tool_name == "hubspot_get_object":
            oid = kwargs.get("object_id", "x")
            return {"id": str(oid), "properties": {"firstname": "Old"}}
        if tool_name == "hubspot_search_objects":
            return [{"id": "901", "properties": {"firstname": "Found"}}]
        if tool_name == "hubspot_update_object":
            return {"id": kwargs.get("object_id"), "properties": kwargs.get("properties", {})}
        if tool_name == "hubspot_delete_object":
            return {"id": kwargs.get("object_id")}
        if tool_name == "hubspot_merge_objects":
            return {"id": kwargs.get("primary_object_id")}
        return {"id": "1"}

    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", _fake)


def _patch_fresh_client(monkeypatch):
    """``_run_loop_tool_step`` builds a fresh client+cache; return fakes."""

    async def _fake_build(portal_config):
        return _FakeClient(), None

    monkeypatch.setattr("hubspot_agent.handlers.build_fresh_client_cache", _fake_build)


# ---------------------------------------------------------------------------
# Intent-regex stopgap
# ---------------------------------------------------------------------------


class TestIntentRegexStopgap:
    def test_renewal_not_classified_as_create(self):
        # "renewal" contains "new" only as a substring; \bnew\b must not match.
        intent = _parse_agent_intent("objects", "renewal contacts")
        assert intent.intent_type != "create"

    def test_created_not_classified_as_create(self):
        # "created" contains "create" only as a substring; \bcreate\b must not match.
        intent = _parse_agent_intent("objects", "created contacts report")
        assert intent.intent_type != "create"

    def test_delete_beats_create_when_both_present(self):
        # Priority search → delete → update → create: a phrase carrying both
        # delete and create verbs must fall into the destructive bucket.
        intent = _parse_agent_intent("objects", "delete old tickets and create a backup")
        assert intent.intent_type == "delete"

    def test_settings_without_verb_is_unknown(self):
        intent = _parse_agent_intent("objects", "contact settings")
        assert intent.intent_type == "unknown"

    def test_explicit_create_still_creates(self):
        intent = _parse_agent_intent("objects", "create a new company")
        assert intent.intent_type == "create"

    def test_explicit_update_still_updates(self):
        intent = _parse_agent_intent("objects", "update the deal stage")
        assert intent.intent_type == "update"


# ---------------------------------------------------------------------------
# parse_plan / validate_plan round-trip + rejections
# ---------------------------------------------------------------------------


def _plan_json(steps):
    return json.dumps(
        {
            "goal": "g",
            "success_criteria": ["ok"],
            "overall_risk": "medium",
            "max_iterations": 3,
            "steps": steps,
        }
    )


class TestPlanToolValidation:
    def test_round_trip_preserves_tool_fields(self):
        text = _plan_json(
            [
                {
                    "step_number": 1,
                    "agent": "objects",
                    "action": "update contact c-42",
                    "risk_level": "medium",
                    "tool_name": "hubspot_update_object",
                    "tool_input": {
                        "object_id": "c-42",
                        "object_type": "contacts",
                        "properties": {"firstname": "Izzy"},
                    },
                }
            ]
        )
        plan = parse_plan(text)
        assert plan is not None
        step = plan.steps[0]
        assert step.tool_name == "hubspot_update_object"
        assert step.tool_input["object_id"] == "c-42"
        assert step.tool_input["properties"] == {"firstname": "Izzy"}
        assert validate_plan(plan) == []

    def test_legacy_text_only_step_validates(self):
        text = _plan_json(
            [{"step_number": 1, "agent": "properties", "action": "create property x"}]
        )
        plan = parse_plan(text)
        assert plan is not None
        assert plan.steps[0].tool_name is None
        assert validate_plan(plan) == []

    def test_unknown_tool_name_rejected(self):
        text = _plan_json(
            [
                {
                    "step_number": 1,
                    "agent": "objects",
                    "action": "do thing",
                    "tool_name": "hubspot_bogus",
                    "tool_input": {"object_id": "1"},
                }
            ]
        )
        plan = parse_plan(text)
        errors = validate_plan(plan)
        assert any("unknown tool 'hubspot_bogus'" in e for e in errors)

    def test_tool_input_without_tool_name_rejected(self):
        text = _plan_json(
            [
                {
                    "step_number": 1,
                    "agent": "objects",
                    "action": "update contact",
                    "tool_input": {"object_id": "c-42"},
                }
            ]
        )
        plan = parse_plan(text)
        errors = validate_plan(plan)
        assert any("tool_input but no tool_name" in e for e in errors)

    def test_write_tool_with_empty_tool_input_rejected(self):
        text = _plan_json(
            [
                {
                    "step_number": 1,
                    "agent": "objects",
                    "action": "create contact",
                    "tool_name": "hubspot_create_object",
                    "tool_input": {},
                }
            ]
        )
        plan = parse_plan(text)
        errors = validate_plan(plan)
        assert any("empty tool_input" in e for e in errors)

    def test_update_tool_missing_object_id_rejected(self):
        text = _plan_json(
            [
                {
                    "step_number": 1,
                    "agent": "objects",
                    "action": "update contact",
                    "tool_name": "hubspot_update_object",
                    "tool_input": {"object_type": "contacts", "properties": {"a": "b"}},
                }
            ]
        )
        plan = parse_plan(text)
        errors = validate_plan(plan)
        assert any("missing 'object_id'" in e for e in errors)

    def test_update_tool_with_placeholder_object_id_accepted(self):
        text = _plan_json(
            [
                {
                    "step_number": 1,
                    "agent": "objects",
                    "action": "find contact",
                    "tool_name": "hubspot_search_objects",
                    "tool_input": {"object_type": "contacts", "query": "x"},
                    "expected_artifact_keys": ["contact_id"],
                },
                {
                    "step_number": 2,
                    "agent": "objects",
                    "action": "update contact",
                    "prerequisites": ["1"],
                    "tool_name": "hubspot_update_object",
                    "tool_input": {
                        "object_id": "{{contact_id}}",
                        "object_type": "contacts",
                        "properties": {"firstname": "Izzy"},
                    },
                },
            ]
        )
        plan = parse_plan(text)
        assert validate_plan(plan) == []

    def test_merge_tool_missing_primary_id_rejected(self):
        text = _plan_json(
            [
                {
                    "step_number": 1,
                    "agent": "objects",
                    "action": "merge contacts",
                    "tool_name": "hubspot_merge_objects",
                    "tool_input": {"object_id_to_merge": "2", "object_type": "contacts"},
                }
            ]
        )
        plan = parse_plan(text)
        errors = validate_plan(plan)
        assert any("missing 'primary_object_id'" in e for e in errors)


# ---------------------------------------------------------------------------
# Headline e2e: verbatim payload, never re-searched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_tool_step_persists_verbatim_and_replays_without_search(
    loop_dirs, monkeypatch
):
    """Adversarial action text + a verbatim tool step: the write lands on the
    named record and execute NEVER re-searches (the bug-2 fuzzy-match path)."""
    recorder: list[dict] = []
    _patch_invoke_tool(monkeypatch, recorder)
    _patch_fresh_client(monkeypatch)

    portal = _portal()
    plan = LoopPlan(
        goal="Renew the contact",
        success_criteria=["contact updated"],
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                # Adversarial text: "renewal" used to route to create via "new".
                action="renewal contact c-42 update firstname",
                risk_level=RiskLevel.MEDIUM,
                tool_name="hubspot_update_object",
                tool_input={
                    "object_id": "c-42",
                    "object_type": "contacts",
                    "properties": {"firstname": "Izzy", "lifecyclestage": "customer"},
                },
            )
        ],
        overall_risk=RiskLevel.MEDIUM,
        max_iterations=3,
    )

    start = await run_loop(plan.goal, portal, ".", "trace-tool", plan=plan)
    assert "paused" in start.lower()

    state = loop_state.load("123")
    assert state.status == "awaiting_approval"
    action_id = state.pending_action_id
    assert action_id

    # The pending record carries the verbatim payload + tool_name, no agent.
    pending = load_pending("123", action_id)
    assert pending is not None
    assert pending["agent_name"] is None
    assert pending["tool_name"] == "hubspot_update_object"
    assert pending["proposed_payload"]["object_id"] == "c-42"
    assert pending["proposed_payload"]["properties"] == {
        "firstname": "Izzy",
        "lifecyclestage": "customer",
    }

    # Approve → execute replays the exact tool with the exact payload.
    result = await execute_pending_write(portal, action_id, client=_FakeClient())
    assert result.status == "success"
    assert result.tool_name == "hubspot_update_object"

    tool_calls = [c["tool"] for c in recorder]
    assert "hubspot_search_objects" not in tool_calls  # the bug-2 path, never taken
    updates = [c for c in recorder if c["tool"] == "hubspot_update_object"]
    assert len(updates) == 1
    assert updates[0]["kwargs"]["object_id"] == "c-42"
    assert updates[0]["kwargs"]["properties"] == {
        "firstname": "Izzy",
        "lifecyclestage": "customer",
    }
    assert updates[0]["kwargs"]["object_type"] == "contacts"


# ---------------------------------------------------------------------------
# Destructive-count gate for a verbatim tool step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_destructive_tool_step_requires_exact_count(loop_dirs, monkeypatch):
    recorder: list[dict] = []
    _patch_invoke_tool(monkeypatch, recorder)
    _patch_fresh_client(monkeypatch)

    portal = _portal()
    plan = LoopPlan(
        goal="Delete the contact",
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="delete contact c-42",
                risk_level=RiskLevel.DESTRUCTIVE,
                tool_name="hubspot_delete_object",
                tool_input={"object_id": "c-42", "object_type": "contacts"},
            )
        ],
        overall_risk=RiskLevel.DESTRUCTIVE,
    )

    await run_loop(plan.goal, portal, ".", "trace-del", plan=plan)
    state = loop_state.load("123")
    action_id = state.pending_action_id
    assert state.status == "awaiting_approval"

    # No count → rejected by the destructive-count gate (FR-19), nothing executed.
    with pytest.raises(ExecuteError):
        await execute_pending_write(portal, action_id, client=_FakeClient())
    assert not [c for c in recorder if c["tool"] == "hubspot_delete_object"]

    # Correct count → executes the exact delete on the named record.
    result = await execute_pending_write(portal, action_id, confirm_count=1, client=_FakeClient())
    assert result.status == "success"
    deletes = [c for c in recorder if c["tool"] == "hubspot_delete_object"]
    assert len(deletes) == 1
    assert deletes[0]["kwargs"]["object_id"] == "c-42"


# ---------------------------------------------------------------------------
# {{artifact_key}} placeholder chaining across a read → write sequence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_placeholder_chain_read_feeds_write(loop_dirs, monkeypatch):
    recorder: list[dict] = []
    _patch_invoke_tool(monkeypatch, recorder)
    _patch_fresh_client(monkeypatch)

    portal = _portal()
    plan = LoopPlan(
        goal="Find then update the contact",
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="search for the contact",
                tool_name="hubspot_search_objects",
                tool_input={"object_type": "contacts", "query": "izzy"},
                expected_artifact_keys=["contact_id"],
            ),
            PlanStep(
                step_number=2,
                agent="objects",
                action="update the found contact",
                prerequisites=["1"],
                risk_level=RiskLevel.MEDIUM,
                tool_name="hubspot_update_object",
                tool_input={
                    "object_id": "{{contact_id}}",
                    "object_type": "contacts",
                    "properties": {"firstname": "Izzy"},
                },
            ),
        ],
        overall_risk=RiskLevel.MEDIUM,
    )

    start = await run_loop(plan.goal, portal, ".", "trace-chain", plan=plan)
    assert "paused" in start.lower()

    state = loop_state.load("123")
    assert state.status == "awaiting_approval"
    action_id = state.pending_action_id

    # Step 1 ran inline and surfaced the found id under contact_id.
    assert state.artifacts[0].outputs.get("contact_id") == "901"
    assert state.current_step == 1  # parked at the write step (index 1), not yet executed

    # The placeholder was resolved before the preview persisted — the pending
    # record names the concrete id, not the {{contact_id}} template.
    pending = load_pending("123", action_id)
    assert pending["proposed_payload"]["object_id"] == "901"

    result = await execute_pending_write(portal, action_id, client=_FakeClient())
    assert result.status == "success"
    updates = [c for c in recorder if c["tool"] == "hubspot_update_object"]
    assert updates[0]["kwargs"]["object_id"] == "901"


@pytest.mark.asyncio
async def test_loop_unresolvable_placeholder_fails_closed(loop_dirs, monkeypatch):
    _patch_invoke_tool(monkeypatch, [])
    _patch_fresh_client(monkeypatch)

    portal = _portal()
    plan = LoopPlan(
        goal="Update a contact",
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="update the contact",
                risk_level=RiskLevel.MEDIUM,
                tool_name="hubspot_update_object",
                # No prior step supplies contact_id → unresolvable.
                tool_input={
                    "object_id": "{{contact_id}}",
                    "object_type": "contacts",
                    "properties": {"firstname": "Izzy"},
                },
            )
        ],
        overall_risk=RiskLevel.MEDIUM,
    )

    await run_loop(plan.goal, portal, ".", "trace-missing", plan=plan)
    state = loop_state.load("123")
    # Failed closed: no pending write was previewed.
    assert state.status == "failed"
    assert state.pending_action_id is None
    assert "contact_id" in (state.last_error or "")
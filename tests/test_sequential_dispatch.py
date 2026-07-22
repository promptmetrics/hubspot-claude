import pytest
from unittest.mock import patch

from hubspot_agent.models import AgentResult, LoopPlan, PlanStep, RiskLevel, StepArtifact, VerificationResult
from hubspot_agent.sequential_dispatch import (
    classify_intent_type,
    execute_plan,
    is_write_step,
    verify_step,
)


# --------------------------------------------------------------------------- #
# Write detection — the gate (is_write_step) must agree with the executor's
# own intent parser (classify_intent_type) so a free-text write step can never
# slip past approval and inline-execute.  Regression for the synonym-verb hole.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("action", [
    "remove stale deals",       # delete synonym (not in the old verb set)
    "purge the deal",
    "clear the company",
    "destroy the ticket",
    "drop the contact",
    "set lifecyclestage on the deal",   # update synonym
    "modify the contact",
    "rename the property",
    "patch the record",
    "add a new contact",        # create synonym
    "insert a company",
])
def test_is_write_step_catches_synonym_write_verbs(action):
    step = PlanStep(step_number=1, agent="objects", action=action, risk_level=RiskLevel.LOW)
    assert is_write_step(step) is True
    assert classify_intent_type(action) in {"create", "update", "delete"}


@pytest.mark.parametrize("action", [
    "merge duplicate companies",   # explicit object-mutation verbs preserved
    "enroll contacts in the workflow",
    "toggle the workflow",
    "bulk update deals",
    "upsert the contact",
])
def test_is_write_step_preserves_explicit_mutation_verbs(action):
    step = PlanStep(step_number=1, agent="objects", action=action, risk_level=RiskLevel.LOW)
    assert is_write_step(step) is True


@pytest.mark.parametrize("action", [
    "find deals closing this quarter",
    "show me the contact",
    "list companies in the pipeline",
    "get the ticket",
    "search for stale deals to remove",   # search verb wins → read (fail-safe priority)
])
def test_is_write_step_leaves_reads_as_reads(action):
    step = PlanStep(step_number=1, agent="objects", action=action, risk_level=RiskLevel.LOW)
    assert is_write_step(step) is False
    assert classify_intent_type(action) == "search"


def _make_plan() -> LoopPlan:
    return LoopPlan(
        goal="Create a property and a workflow",
        steps=[
            PlanStep(
                step_number=1,
                agent="properties",
                action="create property renewal_date",
                description="Create property",
                expected_artifact_keys=["property_id"],
                risk_level=RiskLevel.MEDIUM,
            ),
            PlanStep(
                step_number=2,
                agent="workflows",
                action="create workflow enrollment rule",
                description="Create workflow",
                prerequisites=["1"],
                expected_artifact_keys=["workflow_id"],
                risk_level=RiskLevel.MEDIUM,
            ),
        ],
        overall_risk=RiskLevel.MEDIUM,
    )


@pytest.mark.asyncio
async def test_execute_plan_passes_artifacts_between_steps():
    plan = _make_plan()

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        if agent_name == "properties":
            return AgentResult(
                agent_name="properties",
                status="preview" if mode == "preview" else "success",
                data={"artifacts": {"property_id": "prop-123"}},
            )
        if agent_name == "workflows":
            assert "prop-123" in user_request
            return AgentResult(
                agent_name="workflows",
                status="preview" if mode == "preview" else "success",
                data={"artifacts": {"workflow_id": "wf-456"}},
            )
        return AgentResult(agent_name=agent_name, status="error", error_message="unknown agent")

    with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
        artifacts = await execute_plan(
            plan, "create property and workflow", None, "trace-1",
            approve_callback=lambda _: True,
        )

    assert len(artifacts) == 2
    assert artifacts[0].outputs["property_id"] == "prop-123"
    assert artifacts[1].outputs["workflow_id"] == "wf-456"


@pytest.mark.asyncio
async def test_execute_plan_stops_on_error():
    plan = _make_plan()

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        return AgentResult(
            agent_name=agent_name,
            status="error",
            error_message="boom",
        )

    with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
        try:
            await execute_plan(plan, "create property and workflow", None, "trace-1")
        except RuntimeError as exc:
            assert "preview failed" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError")


@pytest.mark.asyncio
async def test_execute_plan_respects_rejected_approval():
    plan = _make_plan()

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        return AgentResult(
            agent_name=agent_name,
            status="preview" if mode == "preview" else "success",
            data={"artifacts": {"property_id": "prop-123"}},
        )

    with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
        try:
            await execute_plan(
                plan,
                "create property and workflow",
                None,
                "trace-1",
                approve_callback=lambda _: False,
            )
        except RuntimeError as exc:
            assert "not approved" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError")


@pytest.mark.asyncio
async def test_execute_plan_captures_created_ids():
    plan = LoopPlan(
        goal="Create a contact",
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="create contact",
                expected_artifact_keys=["object_id"],
            )
        ],
    )

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        return AgentResult(
            agent_name=agent_name,
            status="preview" if mode == "preview" else "success",
            data={"artifacts": {"object_id": "contact-789"}},
        )

    with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
        artifacts = await execute_plan(
            plan, "create a contact", None, "trace-1",
            approve_callback=lambda _: True,
        )

    assert artifacts[0].created_ids == ["contact-789"]


@pytest.mark.asyncio
async def test_verify_step_decides_verified():
    step = PlanStep(step_number=1, agent="properties", action="create property")
    artifact = StepArtifact(step_number=1, agent="properties", outputs={"property_id": "prop-123"})
    raw = '{"status": "verified", "checked_count": 1, "verified_count": 1, "message": "ok"}'

    with patch("hubspot_agent.sequential_dispatch.spawn_agent", return_value=raw):
        decision, result = await verify_step(step, artifact, None)

    assert decision == "verified"
    assert result.status == VerificationResult.Status.VERIFIED


@pytest.mark.asyncio
async def test_verify_step_decides_retry_on_mismatch():
    step = PlanStep(step_number=1, agent="properties", action="update property")
    artifact = StepArtifact(step_number=1, agent="properties", outputs={"property_id": "prop-123"})
    raw = '{"status": "mismatch", "mismatches": [{"field": "name", "expected": "A", "actual": "B"}]}'

    with patch("hubspot_agent.sequential_dispatch.spawn_agent", return_value=raw):
        decision, result = await verify_step(step, artifact, None)

    assert decision == "retry"
    assert result.status == VerificationResult.Status.MISMATCH


@pytest.mark.asyncio
async def test_verify_step_decides_escalate_on_error():
    step = PlanStep(step_number=1, agent="properties", action="create property")
    artifact = StepArtifact(step_number=1, agent="properties", outputs={"property_id": "prop-123"})

    with patch("hubspot_agent.sequential_dispatch.spawn_agent", return_value="garbage"):
        decision, result = await verify_step(step, artifact, None)

    assert decision == "escalate"
    assert result.status == VerificationResult.Status.ERROR


@pytest.mark.asyncio
async def test_verify_step_no_runtime_assumes_verified():
    step = PlanStep(step_number=1, agent="properties", action="create property")
    artifact = StepArtifact(step_number=1, agent="properties", outputs={"property_id": "prop-123"})

    with patch("hubspot_agent.sequential_dispatch.spawn_agent", return_value="[agent:verify:no_runtime]"):
        decision, result = await verify_step(step, artifact, None)

    assert decision == "verified"

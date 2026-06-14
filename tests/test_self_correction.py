import pytest
from unittest.mock import patch

from hubspot_agent.models import AgentResult, LoopPlan, PlanStep, RiskLevel
from hubspot_agent.sequential_dispatch import execute_plan


def _make_plan() -> LoopPlan:
    return LoopPlan(
        goal="Create a contact",
        steps=[
            PlanStep(
                step_number=1,
                agent="objects",
                action="create contact",
                expected_artifact_keys=["object_id"],
                risk_level=RiskLevel.MEDIUM,
            )
        ],
        overall_risk=RiskLevel.MEDIUM,
    )


@pytest.mark.asyncio
async def test_execute_plan_applies_corrected_payload_after_approval():
    plan = _make_plan()

    calls = []

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        calls.append((mode, kwargs.get("proposed_payload")))
        if mode == "preview":
            return AgentResult(
                agent_name="objects",
                status="preview",
                data={
                    "action_id": "act-1",
                    "risk_level": "medium",
                    "impact_count": 1,
                    "proposed_payload": {"name": "first"},
                    "original_values": {},
                    "intent_type": "create",
                    "target_object": "contacts",
                },
            )
        # First execute returns a corrected payload.
        if len([c for c in calls if c[0] == "execute"]) == 1:
            return AgentResult(
                agent_name="objects",
                status="corrected",
                data={},
                corrected_payload={"name": "corrected"},
                correction_reason="name was taken",
            )
        return AgentResult(
            agent_name="objects",
            status="success",
            data={"artifacts": {"object_id": "contact-123"}},
        )

    approvals = []

    def approve_callback(preview):
        approvals.append(preview.get("proposed_payload"))
        return True

    with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
        artifacts = await execute_plan(
            plan, "create contact", None, "trace-1", approve_callback=approve_callback
        )

    assert len(artifacts) == 1
    assert artifacts[0].created_ids == ["contact-123"]
    # Preview approval + corrected payload approval
    assert approvals == [{"name": "first"}, {"name": "corrected"}]
    # Three execute calls: first corrected, second successful
    execute_calls = [c for c in calls if c[0] == "execute"]
    assert len(execute_calls) == 2


@pytest.mark.asyncio
async def test_execute_plan_rejects_corrected_payload_when_callback_returns_false():
    plan = _make_plan()

    async def fake_dispatch(agent_name, user_request, portal_config=None, mode="preview", **kwargs):
        if mode == "preview":
            return AgentResult(
                agent_name="objects",
                status="preview",
                data={
                    "action_id": "act-1",
                    "risk_level": "medium",
                    "impact_count": 1,
                    "proposed_payload": {"name": "first"},
                    "original_values": {},
                    "intent_type": "create",
                    "target_object": "contacts",
                },
            )
        return AgentResult(
            agent_name="objects",
            status="corrected",
            data={},
            corrected_payload={"name": "corrected"},
        )

    def approve_callback(preview):
        # Approve initial preview, reject corrected payload.
        return preview.get("proposed_payload") == {"name": "first"}

    with patch("hubspot_agent.orchestrator.dispatch_agent", fake_dispatch):
        try:
            await execute_plan(
                plan, "create contact", None, "trace-1", approve_callback=approve_callback
            )
        except RuntimeError as exc:
            assert "corrected payload was not approved" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError")

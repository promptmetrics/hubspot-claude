from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel
from hubspot_agent.planning import parse_plan, parse_verification_result, plan_to_markdown, validate_plan


_PLAN_JSON = """
{
  "goal": "Create a contact property and a workflow using it",
  "success_criteria": ["property exists", "workflow references property"],
  "steps": [
    {
      "step_number": 1,
      "agent": "properties",
      "action": "create property renewal_date",
      "description": "Create a custom contact property named renewal_date",
      "expected_artifact_keys": ["property_id"],
      "risk_level": "medium"
    },
    {
      "step_number": 2,
      "agent": "workflows",
      "action": "create workflow enrollment rule",
      "description": "Build a workflow that enrolls contacts 30 days before renewal_date",
      "prerequisites": ["1"],
      "risk_level": "medium"
    }
  ],
  "overall_risk": "medium",
  "max_iterations": 3
}
"""


def test_parse_valid_json():
    plan = parse_plan(_PLAN_JSON)
    assert plan is not None
    assert isinstance(plan, LoopPlan)
    assert plan.goal == "Create a contact property and a workflow using it"
    assert len(plan.steps) == 2
    assert plan.steps[0].agent == "properties"
    assert plan.steps[0].risk_level == RiskLevel.MEDIUM
    assert plan.steps[1].prerequisites == ["1"]


def test_parse_markdown_wrapped_json():
    text = f"Here is the plan:\n```json\n{_PLAN_JSON}\n```"
    plan = parse_plan(text)
    assert plan is not None
    assert plan.steps[0].step_number == 1


def test_parse_invalid_json_returns_none():
    assert parse_plan("not json") is None


def test_parse_json_without_steps_returns_none():
    assert parse_plan('{"goal": "do nothing"}') is not None
    plan = parse_plan('{"goal": "do nothing"}')
    assert plan.steps == []


def test_validate_plan_no_errors():
    plan = parse_plan(_PLAN_JSON)
    assert validate_plan(plan) == []


def test_validate_plan_missing_goal():
    plan = LoopPlan(goal="", steps=[PlanStep(step_number=1, agent="objects", action="search")])
    errors = validate_plan(plan)
    assert any("missing a goal" in e for e in errors)


def test_validate_plan_missing_workflow_capability():
    plan = parse_plan(_PLAN_JSON)
    errors = validate_plan(plan, capability_matrix={"workflows": False})
    assert any("workflow" in e.lower() for e in errors)


def test_validate_plan_bad_prerequisite():
    plan = LoopPlan(
        goal="test",
        steps=[
            PlanStep(step_number=1, agent="objects", action="search"),
            PlanStep(step_number=2, agent="workflows", action="build", prerequisites=["99"]),
        ],
    )
    errors = validate_plan(plan)
    assert any("depends on step 99" in e for e in errors)


def test_plan_to_markdown():
    plan = parse_plan(_PLAN_JSON)
    md = plan_to_markdown(plan)
    assert "Create a contact property and a workflow using it" in md
    assert "properties" in md
    assert "workflows" in md
    assert "depends on 1" in md


def test_parse_verification_result_valid():
    raw = '{"status": "verified", "checked_count": 5, "verified_count": 5, "message": "ok"}'
    result = parse_verification_result(raw)
    assert result is not None
    assert result.status.value == "verified"
    assert result.checked_count == 5


def test_parse_verification_result_invalid():
    assert parse_verification_result("not json") is None


def test_parse_verification_result_markdown_wrapped():
    raw = "```json\n{\"status\": \"mismatch\", \"mismatches\": []}\n```"
    result = parse_verification_result(raw)
    assert result is not None
    assert result.status.value == "mismatch"

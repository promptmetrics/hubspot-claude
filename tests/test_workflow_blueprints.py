import pytest

from hubspot_agent.agents.workflows import get_workflows_agent_prompt
from hubspot_agent.blueprints.workflows import (
    WorkflowBlueprint,
    build_blueprint_context,
    get_blueprint,
    list_blueprints,
    register_blueprint,
)
from hubspot_agent.blueprints.workflows.deal_stage_task import _build as build_deal_stage_task
from hubspot_agent.blueprints.workflows.lead_scoring import _build as build_lead_scoring
from hubspot_agent.blueprints.workflows.re_engagement import _build as build_re_engagement
from hubspot_agent.blueprints.workflows.welcome_email import _build as build_welcome_email


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    import hubspot_agent.blueprints.workflows as reg

    original = dict(reg._BLUEPRINT_REGISTRY)
    yield
    reg._BLUEPRINT_REGISTRY.clear()
    reg._BLUEPRINT_REGISTRY.update(original)


def test_list_blueprints_has_starter_set():
    names = {bp.name for bp in list_blueprints()}
    assert names >= {"welcome_email", "lead_scoring", "deal_stage_task", "re_engagement"}


def test_get_blueprint_found():
    bp = get_blueprint("welcome_email")
    assert bp is not None
    assert bp.name == "welcome_email"
    assert "welcome" in bp.description.lower()


def test_get_blueprint_missing():
    assert get_blueprint("nonexistent") is None


def test_register_blueprint():
    bp = WorkflowBlueprint(
        name="test_bp",
        description="A test blueprint.",
        tags=["test"],
        parameter_schema={"foo": {"type": "string", "default": "bar"}},
        build=lambda p: {"name": p.get("foo", "bar")},
    )
    register_blueprint(bp)
    assert get_blueprint("test_bp") is bp


class TestWelcomeEmailBlueprint:
    def test_build_defaults(self):
        payload = build_welcome_email({
            "from_email": "noreply@example.com",
            "list_id": "123",
        })
        assert payload["name"] == "Welcome Email"
        assert payload["type"] == "CONTACT_FLOW"
        assert len(payload["actions"]) == 2
        assert payload["actions"][0]["type"] == "DELAY"
        assert payload["actions"][1]["type"] == "SEND_EMAIL"
        assert payload["enrollment"]["list_id"] == "123"

    def test_build_custom_params(self):
        payload = build_welcome_email({
            "name": "Custom Welcome",
            "from_email": "hi@example.com",
            "delay_hours": 2,
            "subject": "Hello!",
            "body": "Welcome aboard.",
            "list_id": "456",
        })
        assert payload["name"] == "Custom Welcome"
        assert payload["actions"][0]["properties"]["delay"]["amount"] == 2
        assert payload["actions"][1]["properties"]["subject"] == "Hello!"


class TestLeadScoringBlueprint:
    def test_build_defaults(self):
        payload = build_lead_scoring({})
        assert payload["name"] == "Lead Scoring"
        assert payload["type"] == "CONTACT_FLOW"
        assert len(payload["actions"]) == 2
        assert payload["actions"][0]["type"] == "SET_PROPERTY"
        assert payload["actions"][1]["type"] == "BRANCH"

    def test_build_no_threshold(self):
        payload = build_lead_scoring({"threshold": 0})
        assert len(payload["actions"]) == 1
        assert payload["actions"][0]["type"] == "SET_PROPERTY"

    def test_build_custom_params(self):
        payload = build_lead_scoring({
            "score_property": "mycustomscore",
            "increment": 5,
            "threshold": 100,
            "event": "FORM_SUBMISSION",
        })
        set_action = payload["actions"][0]
        assert set_action["properties"]["property"] == "mycustomscore"
        assert "+ 5" in set_action["properties"]["value"]
        assert payload["enrollment"]["event"] == "FORM_SUBMISSION"


class TestDealStageTaskBlueprint:
    def test_build_defaults(self):
        payload = build_deal_stage_task({})
        assert payload["name"] == "Deal Stage Task"
        assert payload["type"] == "DEAL_FLOW"
        assert len(payload["actions"]) == 1
        assert payload["actions"][0]["type"] == "CREATE_TASK"
        assert payload["enrollment"]["property"] == "dealstage"
        assert payload["enrollment"]["value"] == "qualifiedtobuy"

    def test_build_custom_params(self):
        payload = build_deal_stage_task({
            "stage": "closedwon",
            "task_title": "Close celebration",
            "due_days": 3,
            "assignee": "user_42",
        })
        assert payload["enrollment"]["value"] == "closedwon"
        task = payload["actions"][0]["properties"]
        assert task["title"] == "Close celebration"
        assert task["due_date"] == "{timestamp + 3d}"
        assert task["assignee"] == "user_42"


class TestReEngagementBlueprint:
    def test_build_defaults(self):
        payload = build_re_engagement({
            "from_email": "team@example.com",
            "list_id": "789",
        })
        assert payload["name"] == "Re-engagement Campaign"
        assert payload["type"] == "CONTACT_FLOW"
        assert len(payload["actions"]) == 2
        assert payload["actions"][0]["properties"]["delay"]["amount"] == 90
        assert payload["actions"][1]["properties"]["subject"] == "We miss you!"

    def test_build_custom_params(self):
        payload = build_re_engagement({
            "name": "Winback",
            "from_email": "win@example.com",
            "inactive_days": 60,
            "subject": "Come back!",
            "body": "We have new features.",
            "list_id": "999",
        })
        assert payload["name"] == "Winback"
        assert payload["actions"][0]["properties"]["delay"]["amount"] == 60
        assert payload["actions"][1]["properties"]["body"] == "We have new features."


class TestBlueprintContext:
    def test_build_blueprint_context_includes_all(self):
        ctx = build_blueprint_context()
        assert "welcome_email" in ctx
        assert "lead_scoring" in ctx
        assert "deal_stage_task" in ctx
        assert "re_engagement" in ctx
        assert "Before building a workflow from scratch" in ctx

    def test_build_blueprint_context_shows_parameters(self):
        ctx = build_blueprint_context()
        assert "from_email" in ctx
        assert "delay_hours" in ctx
        assert "score_property" in ctx


class TestWorkflowsAgentPrompt:
    def test_prompt_includes_blueprint_context(self):
        prompt = get_workflows_agent_prompt()
        assert "Workflow Blueprints" in prompt.system_prompt
        assert "welcome_email" in prompt.system_prompt
        assert "deal_stage_task" in prompt.system_prompt

    def test_prompt_still_has_tools(self):
        prompt = get_workflows_agent_prompt()
        assert "hubspot_create_workflow" in prompt.system_prompt

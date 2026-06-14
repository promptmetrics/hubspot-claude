import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hubspot_agent.agents._base import AgentPrompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.models import PreviewResult, RiskLevel
from hubspot_agent.orchestrator import dispatch_agent, run_loop


def _portal_config(scopes: list[str] | None) -> PortalConfig:
    return PortalConfig(
        portal_id="123",
        token="test-token",
        tier="Professional",
        scopes_granted=scopes,
    )


@pytest.fixture
def agent_prompt(monkeypatch):
    def _get_prompt(name, portal_config=None):
        return AgentPrompt(
            agent_name=name,
            system_prompt="test prompt",
            tool_names=[],
            domain_description="test domain",
        )

    monkeypatch.setattr("hubspot_agent.agents.get_agent_prompt", _get_prompt)
    monkeypatch.setattr("hubspot_agent.agents.get_agent_category", lambda _: "Core CRM")
    monkeypatch.setattr("hubspot_agent.agents.get_agent_emoji", lambda _: "🧩")


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.close = AsyncMock()
    with patch("hubspot_agent.orchestrator.HubSpotClient", return_value=client):
        yield client


@pytest.mark.asyncio
async def test_dispatch_agent_blocks_when_scope_missing(agent_prompt, mock_client):
    portal = _portal_config(["crm.objects.contacts.read"])

    result = await dispatch_agent("objects", "delete contact", portal)

    assert result.status == "error"
    assert "crm.objects.contacts.delete" in result.error_message


@pytest.mark.asyncio
async def test_dispatch_agent_allows_when_scopes_granted(agent_prompt, mock_client):
    portal = _portal_config(
        [
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.contacts.delete",
        ]
    )

    preview = PreviewResult(
        preview={"message": "will delete contact"},
        impact_count=1,
        risk_level=RiskLevel.DESTRUCTIVE,
    )

    with patch(
        "hubspot_agent.orchestrator._build_preview_for_intent",
        new=AsyncMock(return_value=preview),
    ):
        result = await dispatch_agent("objects", "delete contact", portal)

    assert result.status == "preview"
    assert result.data["risk_level"] == "destructive"


@pytest.mark.asyncio
async def test_dispatch_agent_skips_validation_when_no_scopes_recorded(agent_prompt, mock_client):
    portal = _portal_config(None)

    preview = PreviewResult(
        preview={"message": "will create contact"},
        impact_count=1,
        risk_level=RiskLevel.MEDIUM,
    )

    with patch(
        "hubspot_agent.orchestrator._build_preview_for_intent",
        new=AsyncMock(return_value=preview),
    ):
        result = await dispatch_agent("objects", "create contact", portal)

    assert result.status == "preview"


@pytest.mark.asyncio
async def test_run_loop_surfaces_scope_error_before_executing(agent_prompt):
    plan_json = """
    {
      "goal": "Delete contacts",
      "steps": [
        {"step_number": 1, "agent": "objects", "action": "delete contacts",
         "risk_level": "destructive"}
      ],
      "overall_risk": "destructive"
    }
    """

    portal = _portal_config(["crm.objects.contacts.read"])

    with patch("hubspot_agent.orchestrator.spawn_agent", return_value=plan_json):
        result = await run_loop("delete all contacts", portal, ".", "trace-scope")

    assert "Missing HubSpot OAuth scopes:" in result
    assert "crm.objects.contacts.delete" in result

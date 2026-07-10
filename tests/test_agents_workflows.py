import json

import httpx
import pytest

from hubspot_agent.agents.workflows import _execute_workflows, get_workflows_agent_prompt
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig
from hubspot_agent.models import RiskLevel, TaskIntent


def test_workflows_agent_prompt_has_correct_tools():
    prompt = get_workflows_agent_prompt()
    assert prompt.agent_name == "Workflows Agent"
    expected = [
        "hubspot_get_workflow",
        "hubspot_list_workflows",
        "hubspot_create_workflow",
        "hubspot_create_workflow_from_blueprint",
        "hubspot_update_workflow",
        "hubspot_enroll_workflow",
        "hubspot_toggle_workflow",
    ]
    assert sorted(prompt.tool_names) == sorted(expected)


@pytest.mark.asyncio
async def test_execute_update_does_get_then_put_with_revision(respx_mock):
    """V4 update must GET the current body/revisionId, merge edits, and PUT the whole."""
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    get_route = respx_mock.get("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "1",
                "revisionId": "r9",
                "name": "Old",
                "actions": [{"actionId": "a1"}],
            },
        )
    )
    put_route = respx_mock.put("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(200, json={"id": "1", "revisionId": "r10"})
    )

    intent = TaskIntent(
        intent_type="update",
        description="rename workflow",
        risk_level=RiskLevel.MEDIUM,
    )
    result = await _execute_workflows(
        agent_name="workflows",
        intent=intent,
        request_text="rename workflow 1 to Renamed",
        client=c,
        portal_id="123",
        proposed_payload={"workflow_id": "1", "updates": {"name": "Renamed"}},
    )

    assert result["status"] == "success"
    assert get_route.called
    assert put_route.called
    sent = json.loads(put_route.calls.last.request.content)
    assert sent["revisionId"] == "r9"  # pulled from the GET response
    assert sent["name"] == "Renamed"  # caller edit wins
    assert sent["actions"] == [{"actionId": "a1"}]  # untouched field survives merge
    assert "id" not in sent  # server-managed field stripped before PUT
    await c.close()


@pytest.mark.asyncio
async def test_execute_update_aborts_when_get_fails(respx_mock):
    """If the pre-update GET fails, do not issue a destructive PUT."""
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    put_route = respx_mock.put("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(200, json={"id": "1"})
    )

    intent = TaskIntent(
        intent_type="update",
        description="rename workflow",
        risk_level=RiskLevel.MEDIUM,
    )
    result = await _execute_workflows(
        agent_name="workflows",
        intent=intent,
        request_text="rename workflow 1",
        client=c,
        portal_id="123",
        proposed_payload={"workflow_id": "1", "updates": {"name": "Renamed"}},
    )

    assert result["status"] == "error"
    assert not put_route.called
    await c.close()

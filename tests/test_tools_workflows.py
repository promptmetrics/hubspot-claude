import httpx
import pytest

from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools.workflows import (
    hubspot_get_workflow,
    hubspot_list_workflows,
    hubspot_create_workflow,
    hubspot_update_workflow,
    hubspot_enroll_workflow,
    hubspot_toggle_workflow,
)


@pytest.mark.asyncio
async def test_hubspot_get_workflow(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(200, json={"id": "1", "name": "Test"})
    )
    result = await hubspot_get_workflow(workflow_id="1", client=c, portal_id="123")
    assert result["id"] == "1"
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_list_workflows(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/automation/v4/flows").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "1", "name": "Test"}]})
    )
    result = await hubspot_list_workflows(client=c, portal_id="123")
    assert len(result["results"]) == 1
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_create_workflow(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/automation/v4/flows").mock(
        return_value=httpx.Response(201, json={"id": "2"})
    )
    result = await hubspot_create_workflow(name="New", workflow_type="CONTACT_FLOW", actions=[], enrollment={}, client=c, portal_id="123")
    assert result["id"] == "2"
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_update_workflow(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.patch("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(200, json={"id": "1"})
    )
    result = await hubspot_update_workflow(workflow_id="1", updates={"name": "Updated"}, client=c, portal_id="123")
    assert result["id"] == "1"
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_enroll_workflow(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/automation/v4/flows/1/enrollments").mock(
        return_value=httpx.Response(200)
    )
    result = await hubspot_enroll_workflow(workflow_id="1", object_ids=["101"], client=c, portal_id="123")
    assert "error" not in result
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_toggle_workflow(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/automation/v4/flows/1/toggle").mock(
        return_value=httpx.Response(200)
    )
    result = await hubspot_toggle_workflow(workflow_id="1", enabled=False, client=c, portal_id="123")
    assert "error" not in result
    await c.close()

import httpx
import pytest

from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools.objects import (
    hubspot_get_object,
    hubspot_search_objects,
    hubspot_create_object,
    hubspot_update_object,
    hubspot_delete_object,
    hubspot_batch_upsert_objects,
)


@pytest.mark.asyncio
async def test_hubspot_get_object(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value=httpx.Response(200, json={"id": "1", "properties": {"email": "a@b.com"}})
    )
    result = await hubspot_get_object(object_id="1", object_type="contacts", client=c, portal_id="123")
    assert result["id"] == "1"
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_search_objects(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/search").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "1"}]})
    )
    result = await hubspot_search_objects(object_type="contacts", query={}, client=c, portal_id="123")
    assert len(result["results"]) == 1
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_create_object(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts").mock(
        return_value=httpx.Response(201, json={"id": "2"})
    )
    result = await hubspot_create_object(object_type="contacts", properties={"email": "new@example.com"}, client=c, portal_id="123")
    assert result["id"] == "2"
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_update_object(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.patch("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value=httpx.Response(200, json={"id": "1"})
    )
    result = await hubspot_update_object(object_id="1", object_type="contacts", properties={"email": "updated@example.com"}, client=c, portal_id="123")
    assert result["id"] == "1"
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_delete_object(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.delete("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value=httpx.Response(204)
    )
    result = await hubspot_delete_object(object_id="1", object_type="contacts", client=c, portal_id="123")
    assert "error" not in result
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_batch_upsert_objects(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/batch/create").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "3"}], "errors": []})
    )
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/batch/update").mock(
        return_value=httpx.Response(200, json={"results": [], "errors": []})
    )
    result = await hubspot_batch_upsert_objects(
        object_type="contacts",
        records=[{"email": "batch@example.com"}],
        client=c,
        portal_id="123",
    )
    assert result["succeeded"] == 1
    assert "progress" in result
    assert result["progress"]["action_id"] == result["action_id"]
    assert result["progress"]["total_chunks"] == 1
    assert result["progress"]["completed_chunks"] == 1
    await c.close()

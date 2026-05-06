import httpx
import pytest

from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig


@pytest.mark.asyncio
async def test_client_get_success(respx_mock):
    client = HubSpotClient(PortalConfig(portal_id="123", token="test-token"))
    respx_mock.get("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value=httpx.Response(200, json={"id": "1", "properties": {"email": "a@b.com"}})
    )
    resp = await client.get("/crm/v3/objects/contacts/1", portal_id="123")
    assert resp.body["id"] == "1"
    await client.close()


@pytest.mark.asyncio
async def test_client_post_success(respx_mock):
    client = HubSpotClient(PortalConfig(portal_id="123", token="test-token"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts").mock(
        return_value=httpx.Response(201, json={"id": "2"})
    )
    resp = await client.post("/crm/v3/objects/contacts", portal_id="123", body={"properties": {"email": "new@example.com"}})
    assert resp.body["id"] == "2"
    await client.close()


@pytest.mark.asyncio
async def test_client_rate_limit(respx_mock):
    from hubspot_agent.errors import RateLimitError
    client = HubSpotClient(PortalConfig(portal_id="123", token="test-token"))
    respx_mock.get("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "5"})
    )
    with pytest.raises(RateLimitError):
        await client.get("/crm/v3/objects/contacts/1", portal_id="123")
    await client.close()


@pytest.mark.asyncio
async def test_client_hubspot_error(respx_mock):
    from hubspot_agent.errors import HubSpotError
    client = HubSpotClient(PortalConfig(portal_id="123", token="test-token"))
    respx_mock.get("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    with pytest.raises(HubSpotError):
        await client.get("/crm/v3/objects/contacts/1", portal_id="123")
    await client.close()

import httpx
import pytest

from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig
from hubspot_agent.tools.hygiene import (
    hubspot_find_duplicates,
    hubspot_merge_objects,
    hubspot_bulk_update_objects,
    hubspot_preview_segment,
)


@pytest.mark.asyncio
async def test_hubspot_find_duplicates(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/search").mock(
        return_value=httpx.Response(200, json={"results": [
            {"id": "1", "properties": {"email": "dup@example.com"}},
            {"id": "2", "properties": {"email": "dup@example.com"}},
        ]})
    )
    result = await hubspot_find_duplicates(object_type="contacts", search_field="email", client=c, portal_id="123")
    assert result["total_duplicates"] == 2
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_merge_objects(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/merge").mock(
        return_value=httpx.Response(200, json={"id": "1"})
    )
    result = await hubspot_merge_objects(primary_object_id="1", object_id_to_merge="2", client=c, portal_id="123")
    assert result["id"] == "1"
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_bulk_update_objects(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/batch/update").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "1"}], "errors": []})
    )
    result = await hubspot_bulk_update_objects(object_type="contacts", records=[{"id": "1", "properties": {"email": "new@example.com"}}], client=c, portal_id="123")
    assert result["succeeded"] == 1
    await c.close()


# ---------------------------------------------------------------------------
# M8: object_type must be validated before URL construction — a crafted value
# like "contacts/batch/archive?" would otherwise redirect a bulk update to the
# archive endpoint without tripping the destructive-count gate.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_type", ["contacts/batch/archive?", "../pipelines", "contacts#frag"])
async def test_find_duplicates_rejects_crafted_object_type(respx_mock, bad_type):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    with pytest.raises(ValueError, match="Invalid object_type"):
        await hubspot_find_duplicates(object_type=bad_type, search_field="email", client=c, portal_id="123")
    assert len(respx_mock.calls) == 0
    await c.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_type", ["contacts/batch/archive?", "../pipelines"])
async def test_bulk_update_rejects_crafted_object_type(respx_mock, bad_type):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    with pytest.raises(ValueError, match="Invalid object_type"):
        await hubspot_bulk_update_objects(
            object_type=bad_type,
            records=[{"id": "1", "properties": {"email": "a@example.com"}}],
            client=c,
            portal_id="123",
        )
    assert len(respx_mock.calls) == 0
    await c.close()


@pytest.mark.asyncio
async def test_preview_segment_rejects_crafted_object_type(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    with pytest.raises(ValueError, match="Invalid object_type"):
        await hubspot_preview_segment(object_type="contacts/batch/archive?", query={}, client=c, portal_id="123")
    assert len(respx_mock.calls) == 0
    await c.close()


@pytest.mark.asyncio
async def test_hubspot_preview_segment(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/search").mock(
        return_value=httpx.Response(200, json={"total": 5, "results": [{"id": "1"}]})
    )
    result = await hubspot_preview_segment(object_type="contacts", query={}, client=c, portal_id="123")
    assert result["total"] == 5
    await c.close()

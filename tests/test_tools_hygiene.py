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
# M9: merge honors object_type (default contacts) and expects write+delete
# scopes, matching the registry's destructive classification.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_objects_companies_endpoint(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    route = respx_mock.post("https://api.hubapi.com/crm/v3/objects/companies/merge").mock(
        return_value=httpx.Response(200, json={"id": "9"})
    )
    result = await hubspot_merge_objects(
        primary_object_id="9", object_id_to_merge="10", client=c, portal_id="123", object_type="companies"
    )
    assert result["id"] == "9"
    import json as _json
    body = _json.loads(route.calls[0].request.content)
    assert body == {"primaryObjectId": "9", "objectIdToMerge": "10"}
    await c.close()


@pytest.mark.asyncio
async def test_merge_objects_invalid_object_type_raises(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    with pytest.raises(ValueError, match="Invalid object_type"):
        await hubspot_merge_objects(
            primary_object_id="1", object_id_to_merge="2", client=c, portal_id="123",
            object_type="contacts/merge?",
        )
    assert len(respx_mock.calls) == 0
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


# ---------------------------------------------------------------------------
# Bug 3: find_duplicates must request `properties` + `limit` and paginate, or
# phone/domain duplicates come back empty and large portals look dup-free past
# the first 100-record page.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_duplicates_requests_properties_and_limit(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    route = respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    await hubspot_find_duplicates(object_type="contacts", search_field="email", client=c, portal_id="123")
    import json as _json
    body = _json.loads(route.calls[0].request.content)
    assert body["properties"] == ["email"]
    assert body["limit"] == 100
    await c.close()


@pytest.mark.asyncio
async def test_find_duplicates_phone_requests_calculated_field(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    route = respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    await hubspot_find_duplicates(object_type="contacts", search_field="phone", client=c, portal_id="123")
    import json as _json
    body = _json.loads(route.calls[0].request.content)
    assert "hs_searchable_calculated_phone_number" in body["properties"]
    assert "phone" in body["properties"]
    await c.close()


@pytest.mark.asyncio
async def test_find_duplicates_paginates_across_pages(respx_mock):
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    same_email = "dup@example.com"
    page1 = httpx.Response(
        200,
        json={
            "results": [
                {"id": "1", "properties": {"email": same_email}},
                {"id": "2", "properties": {"email": same_email}},
            ],
            "paging": {"next": {"after": "2"}},
        },
    )
    page2 = httpx.Response(
        200,
        json={"results": [{"id": "3", "properties": {"email": same_email}}]},
    )

    calls = {"i": 0}

    def _side(request):
        calls["i"] += 1
        return page1 if calls["i"] == 1 else page2

    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/search").mock(side_effect=_side)
    result = await hubspot_find_duplicates(object_type="contacts", search_field="email", client=c, portal_id="123")
    assert calls["i"] == 2  # paginated to a second page
    assert result["total_duplicates"] == 3
    assert result["records_scanned"] == 3
    assert result["truncated"] is False
    await c.close()


@pytest.mark.asyncio
async def test_find_duplicates_reports_truncated_at_scan_cap(respx_mock, monkeypatch):
    from hubspot_agent.tools import hygiene as hygiene_mod

    # Force a tiny cap so we don't need 21 real pages to exercise truncation.
    monkeypatch.setattr(hygiene_mod, "_MAX_SCAN_RECORDS", 2)

    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    page = httpx.Response(
        200,
        json={
            "results": [{"id": "1", "properties": {"email": "a@example.com"}}],
            "paging": {"next": {"after": "1"}},  # always another page -> hits the cap
        },
    )
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts/search").mock(return_value=page)
    result = await hubspot_find_duplicates(object_type="contacts", search_field="email", client=c, portal_id="123")
    assert result["truncated"] is True
    assert result["records_scanned"] == 2
    await c.close()

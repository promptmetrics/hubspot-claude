import httpx
import pytest

from hubspot_agent.capabilities import CapabilityCache, CapabilityMatrix
from hubspot_agent.config import PortalConfig
from hubspot_agent.orchestrator import check_dispatch_readiness


@pytest.mark.asyncio
async def test_check_dispatch_readiness_all_clear(respx_mock, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "hubspot_agent.capabilities.CapabilityCache",
        lambda portal_id, base_dir=None: CapabilityCache(portal_id, base_dir=tmp_path),
    )
    respx_mock.get("https://api.hubapi.com/account-info/v3/details").mock(
        return_value=httpx.Response(200, json={"tier": "Enterprise"})
    )
    respx_mock.get("https://api.hubapi.com/crm/v3/schemas").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx_mock.get("https://api.hubapi.com/automation/v4/workflows?limit=1").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx_mock.get("https://api.hubapi.com/settings/v3/users?limit=1").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx_mock.get("https://api.hubapi.com/crm/v3/properties/contacts").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    portal = PortalConfig(
        portal_id="123",
        token="test-token",
        scopes_granted=["crm.objects.contacts.read", "automation.workflows.write"],
    )
    result = await check_dispatch_readiness(["workflows"], portal)
    assert result["ready"] is True


@pytest.mark.asyncio
async def test_check_dispatch_readiness_missing_capability(respx_mock, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "hubspot_agent.capabilities.CapabilityCache",
        lambda portal_id, base_dir=None: CapabilityCache(portal_id, base_dir=tmp_path),
    )
    respx_mock.get("https://api.hubapi.com/account-info/v3/details").mock(
        return_value=httpx.Response(200, json={"tier": "Starter"})
    )
    respx_mock.get("https://api.hubapi.com/crm/v3/schemas").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )
    respx_mock.get("https://api.hubapi.com/automation/v4/workflows?limit=1").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )
    respx_mock.get("https://api.hubapi.com/settings/v3/users?limit=1").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )
    respx_mock.get("https://api.hubapi.com/crm/v3/properties/contacts").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    portal = PortalConfig(
        portal_id="123",
        token="test-token",
        scopes_granted=["crm.objects.contacts.read", "automation.workflows.write"],
    )
    result = await check_dispatch_readiness(["workflows"], portal)
    assert result["ready"] is False
    assert "workflows" in result["decline_reason"]


@pytest.mark.asyncio
async def test_check_dispatch_readiness_missing_capability_on_starter_portal(respx_mock, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "hubspot_agent.capabilities.CapabilityCache",
        lambda portal_id, base_dir=None: CapabilityCache(portal_id, base_dir=tmp_path),
    )
    respx_mock.get("https://api.hubapi.com/account-info/v3/details").mock(
        return_value=httpx.Response(200, json={"tier": "Starter"})
    )
    respx_mock.get("https://api.hubapi.com/crm/v3/schemas").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )
    respx_mock.get("https://api.hubapi.com/automation/v4/workflows?limit=1").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )
    respx_mock.get("https://api.hubapi.com/settings/v3/users?limit=1").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )
    respx_mock.get("https://api.hubapi.com/crm/v3/properties/contacts").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    portal = PortalConfig(
        portal_id="123",
        token="test-token",
        scopes_granted=["crm.objects.contacts.read"],
    )
    result = await check_dispatch_readiness(["workflows"], portal)
    assert result["ready"] is False
    assert result["decline_reason"] is not None
    assert "workflows" in result["decline_reason"]


@pytest.mark.asyncio
async def test_check_dispatch_readiness_uses_cached_matrix(monkeypatch, tmp_path):
    cache = CapabilityCache("123", base_dir=tmp_path)
    cache.set(CapabilityMatrix(workflows=False, users=True))

    monkeypatch.setattr(
        "hubspot_agent.capabilities.CapabilityCache",
        lambda portal_id, base_dir=None: CapabilityCache(portal_id, base_dir=tmp_path),
    )

    portal = PortalConfig(
        portal_id="123",
        token="test-token",
        scopes_granted=["automation.workflows.write"],
    )
    result = await check_dispatch_readiness(["workflows"], portal)
    assert result["ready"] is False
    assert "workflows" in result["decline_reason"]

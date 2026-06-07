import pytest

from hubspot_agent.client import APIResponse
from hubspot_agent.config import PortalConfig
from hubspot_agent.errors import ErrorCategory, HubSpotError, RateLimitError
from hubspot_agent.testing import ChaosConfig, ChaosHubSpotClient


class TestChaosConfig:
    def test_defaults(self):
        cfg = ChaosConfig()
        assert cfg.rate_limit_rate == 0.05
        assert cfg.network_error_rate == 0.01
        assert cfg.truncation_rate == 0.001
        assert cfg.chaos_seed is None

    def test_seeded_rng(self):
        cfg = ChaosConfig(chaos_seed=42)
        assert cfg._rng.random() == ChaosConfig(chaos_seed=42)._rng.random()


class TestChaosHubSpotClient:
    def test_init_defaults(self):
        portal = PortalConfig(portal_id="123", token="t")
        client = ChaosHubSpotClient(portal)
        assert client.chaos_config.rate_limit_rate == 0.05

    def test_select_fault_with_seed(self):
        portal = PortalConfig(portal_id="123", token="t")
        client = ChaosHubSpotClient(portal, ChaosConfig(chaos_seed=1, rate_limit_rate=1.0))
        assert client._select_fault() == "rate_limit"

    def test_select_no_fault(self):
        portal = PortalConfig(portal_id="123", token="t")
        client = ChaosHubSpotClient(portal, ChaosConfig(chaos_seed=1, rate_limit_rate=0.0, network_error_rate=0.0, truncation_rate=0.0))
        assert client._select_fault() is None

    @pytest.mark.asyncio
    async def test_request_rate_limit(self):
        portal = PortalConfig(portal_id="123", token="t")
        client = ChaosHubSpotClient(portal, ChaosConfig(chaos_seed=1, rate_limit_rate=1.0))
        with pytest.raises(RateLimitError):
            await client._request("GET", "/", "123")
        await client.close()

    @pytest.mark.asyncio
    async def test_request_network_error(self):
        portal = PortalConfig(portal_id="123", token="t")
        client = ChaosHubSpotClient(portal, ChaosConfig(chaos_seed=1, rate_limit_rate=0.0, network_error_rate=1.0))
        with pytest.raises(HubSpotError) as exc_info:
            await client._request("GET", "/", "123")
        assert exc_info.value.category == ErrorCategory.SERVER
        await client.close()

    @pytest.mark.asyncio
    async def test_request_no_fault(self, respx_mock):
        portal = PortalConfig(portal_id="123", token="t")
        client = ChaosHubSpotClient(portal, ChaosConfig(chaos_seed=1, rate_limit_rate=0.0, network_error_rate=0.0, truncation_rate=0.0))
        respx_mock.get("https://api.hubapi.com/").mock(return_value=__import__("httpx").Response(200, json={"ok": True}))
        resp = await client._request("GET", "/", "123")
        assert isinstance(resp, APIResponse)
        await client.close()

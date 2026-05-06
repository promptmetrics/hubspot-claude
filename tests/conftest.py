import pytest
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig


@pytest.fixture
def mock_portal():
    return PortalConfig(portal_id="123", token="test-token", tier="Professional")


@pytest.fixture
async def test_client(mock_portal):
    client = HubSpotClient(mock_portal)
    yield client
    await client.close()

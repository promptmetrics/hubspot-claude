import urllib.parse

import pytest
import respx
from httpx import Response

from hubspot_agent.auth import (
    exchange_code_for_token,
    get_authorization_url,
    get_valid_token,
    refresh_access_token,
)
from hubspot_agent.config import load_portal_config


def test_get_authorization_url_with_credentials(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-123", "secret-456")

    url = get_authorization_url("123", ["crm.objects.contacts.read"])
    assert url.startswith("https://app.hubspot.com/oauth/authorize")
    assert "client_id=client-123" in url
    assert "crm.objects.contacts.read" in url
    assert "state=" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url


def test_get_authorization_url_no_credentials(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(ValueError, match="credentials not found"):
        get_authorization_url("123", ["crm.objects.contacts.read"])


@pytest.mark.asyncio
async def test_exchange_code_for_token(respx_mock, monkeypatch, tmp_path):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-123", "secret-456")

    respx_mock.post("https://api.hubapi.com/oauth/v1/token").mock(
        return_value=Response(200, json={
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 21600,
        })
    )

    url = get_authorization_url("123", ["crm.objects.contacts.read"])
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]

    result = await exchange_code_for_token("123", "auth-code-abc", state)
    assert result["access_token"] == "new-access-token"

    portal = load_portal_config("123")
    assert portal is not None
    assert portal.token == "new-access-token"
    assert portal.refresh_token == "new-refresh-token"
    assert portal.auth_type == "oauth"


@pytest.mark.asyncio
async def test_refresh_access_token(respx_mock, tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-123", "secret-456")

    respx_mock.post("https://api.hubapi.com/oauth/v1/token").mock(
        return_value=Response(200, json={
            "access_token": "refreshed-token",
            "refresh_token": "same-refresh-token",
            "expires_in": 21600,
        })
    )

    result = await refresh_access_token("123", "same-refresh-token")
    assert result["access_token"] == "refreshed-token"


@pytest.mark.asyncio
async def test_get_valid_token_oauth_fresh(tmp_path, monkeypatch):
    import time
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)

    from hubspot_agent.config import PortalConfig, save_portal_config
    save_portal_config(PortalConfig(
        portal_id="123",
        token="access-token",
        auth_type="oauth",
        refresh_token="refresh-token",
        expires_at=time.time() + 3600,
    ))

    token = await get_valid_token("123")
    assert token == "access-token"


@pytest.mark.asyncio
async def test_get_valid_token_private_app(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)

    from hubspot_agent.config import PortalConfig, save_portal_config
    save_portal_config(PortalConfig(
        portal_id="123",
        token="pat-na1-abc",
        auth_type="private_app",
    ))

    token = await get_valid_token("123")
    assert token == "pat-na1-abc"


@pytest.mark.asyncio
async def test_get_valid_token_none(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    assert await get_valid_token("123") is None

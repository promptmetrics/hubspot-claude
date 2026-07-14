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
from hubspot_agent.config import PortalConfig, load_portal_config, save_portal_config


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
            "scope": "crm.objects.contacts.read crm.objects.contacts.write",
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
    # Bug 3 regression: the granted scopes from the token response must be
    # persisted into PortalConfig so setup's scope-gap report isn't 0/23.
    assert portal.scopes_granted == [
        "crm.objects.contacts.read",
        "crm.objects.contacts.write",
    ]


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
async def test_refresh_preserves_scopes_when_response_omits_scope(respx_mock, tmp_path, monkeypatch):
    # Bug 3: a refresh response may omit the `scope` field. The previously
    # granted scopes must be preserved so the scope-gap report stays accurate
    # across token refresh, instead of resetting to 0/N granted.
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-123", "secret-456")

    save_portal_config(
        PortalConfig(
            portal_id="123",
            token="old-token",
            auth_type="oauth",
            refresh_token="same-refresh-token",
            scopes_granted=["crm.objects.contacts.read", "crm.objects.contacts.write"],
        )
    )

    # Refresh response carries NO `scope` field.
    respx_mock.post("https://api.hubapi.com/oauth/v1/token").mock(
        return_value=Response(200, json={
            "access_token": "refreshed-token",
            "refresh_token": "same-refresh-token",
            "expires_in": 21600,
        })
    )

    await refresh_access_token("123", "same-refresh-token")

    portal = load_portal_config("123")
    assert portal is not None
    assert portal.token == "refreshed-token"
    assert portal.scopes_granted == [
        "crm.objects.contacts.read",
        "crm.objects.contacts.write",
    ]


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


def test_get_authorization_url_us_region_default(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-us", "secret-us")  # default region='us'

    url = get_authorization_url("123", ["crm.objects.contacts.read"])
    assert url.startswith("https://app.hubspot.com/oauth/authorize")
    assert "client_id=client-us" in url


def test_get_authorization_url_eu_region(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-eu", "secret-eu", region="eu")

    url = get_authorization_url("123", ["crm.objects.contacts.read"])
    assert url.startswith("https://app-eu1.hubspot.com/oauth/authorize")
    assert "client_id=client-eu" in url


# ---------------------------------------------------------------------------
# M1: OAuth `state` path traversal must not reach the filesystem
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_rejects_traversal_state(tmp_path, monkeypatch):
    # A crafted state of "../<portal_id>" used to resolve to the portal token
    # file, which _load_oauth_state unlinked (no expires_at -> "expired").
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.auth.CONFIG_DIR", tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-123", "secret-456")
    save_portal_config(PortalConfig(portal_id="123", token="precious-token"))

    with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
        await exchange_code_for_token("123", "auth-code-abc", "../123")

    # The portal credential file must survive the attempt.
    assert (tmp_path / "123.json").exists()
    assert load_portal_config("123").token == "precious-token"


def test_load_oauth_state_invalid_chars_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("hubspot_agent.auth.CONFIG_DIR", tmp_path)
    from hubspot_agent.auth import _load_oauth_state

    assert _load_oauth_state("../123") is None
    assert _load_oauth_state("a/b") is None
    assert _load_oauth_state("state.json") is None
    assert _load_oauth_state("") is None


def test_oauth_state_file_mode_0o600(tmp_path, monkeypatch):
    # M2: the state file carries the PKCE code_verifier and must be 0600 from
    # birth, not narrowed after a world-readable window.
    import os
    import stat
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.auth.CONFIG_DIR", tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-123", "secret-456")

    get_authorization_url("123", ["crm.objects.contacts.read"])
    state_files = list((tmp_path / "oauth_states").glob("*.json"))
    assert state_files
    assert stat.S_IMODE(os.stat(state_files[0]).st_mode) == 0o600


@pytest.mark.asyncio
async def test_exchange_code_for_token_eu_region(respx_mock, monkeypatch, tmp_path):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)

    from hubspot_agent.app_credentials import save_app_credentials
    save_app_credentials("client-eu", "secret-eu", region="eu")

    respx_mock.post("https://api-eu1.hubapi.com/oauth/v1/token").mock(
        return_value=Response(200, json={
            "access_token": "eu-access-token",
            "refresh_token": "eu-refresh-token",
            "expires_in": 21600,
        })
    )

    url = get_authorization_url("123", ["crm.objects.contacts.read"])
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]

    result = await exchange_code_for_token("123", "auth-code-abc", state)
    assert result["access_token"] == "eu-access-token"

    portal = load_portal_config("123")
    assert portal is not None
    assert portal.token == "eu-access-token"
    assert portal.auth_type == "oauth"

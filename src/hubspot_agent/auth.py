from __future__ import annotations

import secrets
import time
import urllib.parse
from typing import Any

import httpx

from hubspot_agent.app_credentials import get_client_id, get_client_secret
from hubspot_agent.config import PortalConfig, load_portal_config, save_portal_config

_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
_REFRESH_BUFFER_SECONDS = 300  # refresh if within 5 minutes of expiry


def _build_code_verifier() -> str:
    return secrets.token_urlsafe(48)


def get_authorization_url(
    portal_id: str,
    scopes: list[str],
    redirect_uri: str = "http://localhost:3000/oauth/callback",
) -> str:
    client_id = get_client_id()
    if not client_id:
        raise ValueError("HubSpot app credentials not found. Run save_app_credentials() first.")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "response_type": "code",
        "state": portal_id,
    }
    return f"{_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_token(
    portal_id: str,
    code: str,
    redirect_uri: str = "http://localhost:3000/oauth/callback",
) -> dict[str, Any]:
    client_id = get_client_id()
    client_secret = get_client_secret()
    if not client_id or not client_secret:
        raise ValueError("HubSpot app credentials not found.")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        resp.raise_for_status()
        body = resp.json()

    _save_oauth_tokens(
        portal_id=portal_id,
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        expires_in=body.get("expires_in", 21600),
    )
    return body


async def refresh_access_token(portal_id: str, refresh_token: str) -> dict[str, Any]:
    client_id = get_client_id()
    client_secret = get_client_secret()
    if not client_id or not client_secret:
        raise ValueError("HubSpot app credentials not found.")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        body = resp.json()

    _save_oauth_tokens(
        portal_id=portal_id,
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", refresh_token),
        expires_in=body.get("expires_in", 21600),
    )
    return body


async def get_valid_token(portal_id: str) -> str | None:
    portal = load_portal_config(portal_id)
    if not portal:
        return None

    if portal.auth_type == "oauth":
        if portal.expires_at and portal.expires_at - time.time() < _REFRESH_BUFFER_SECONDS:
            if portal.refresh_token:
                body = await refresh_access_token(portal_id, portal.refresh_token)
                return body["access_token"]
            return None
        return portal.token

    return portal.token


def _save_oauth_tokens(
    portal_id: str,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
) -> None:
    from hubspot_agent.config import PortalConfig

    portal = PortalConfig(
        portal_id=portal_id,
        token=access_token,
        auth_type="oauth",
        refresh_token=refresh_token,
        expires_at=time.time() + expires_in,
    )
    save_portal_config(portal)

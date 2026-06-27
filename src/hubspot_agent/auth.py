from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from hubspot_agent.app_credentials import get_client_id, get_client_secret, get_oauth_endpoints
from hubspot_agent.config import CONFIG_DIR, PortalConfig, load_portal_config, save_portal_config

_REFRESH_BUFFER_SECONDS = 300  # refresh if within 5 minutes of expiry
_STATE_EXPIRY_SECONDS = 600  # 10 minutes


def _build_code_verifier() -> str:
    return secrets.token_urlsafe(48)


def _build_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _oauth_state_dir() -> Path:
    path = CONFIG_DIR / "oauth_states"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _oauth_state_file(state: str) -> Path:
    return _oauth_state_dir() / f"{state}.json"


def _save_oauth_state(
    state: str,
    portal_id: str,
    code_verifier: str,
    redirect_uri: str,
) -> None:
    path = _oauth_state_file(state)
    payload = {
        "portal_id": portal_id,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "expires_at": time.time() + _STATE_EXPIRY_SECONDS,
    }
    path.write_text(json.dumps(payload))
    path.chmod(0o600)


def _load_oauth_state(state: str) -> dict[str, Any] | None:
    path = _oauth_state_file(state)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() > data.get("expires_at", 0):
            _clear_oauth_state(state)
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _clear_oauth_state(state: str) -> None:
    try:
        _oauth_state_file(state).unlink(missing_ok=True)
    except OSError:
        pass


def get_authorization_url(
    portal_id: str,
    scopes: list[str],
    redirect_uri: str = "http://localhost:3000/oauth/callback",
) -> str:
    client_id = get_client_id()
    if not client_id:
        raise ValueError("HubSpot app credentials not found. Run save_app_credentials() first.")

    authorize_url, _ = get_oauth_endpoints()

    state = secrets.token_urlsafe(32)
    code_verifier = _build_code_verifier()
    code_challenge = _build_code_challenge(code_verifier)

    _save_oauth_state(state, portal_id, code_verifier, redirect_uri)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorize_url}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_token(
    portal_id: str,
    code: str,
    state: str,
    redirect_uri: str = "http://localhost:3000/oauth/callback",
) -> dict[str, Any]:
    client_id = get_client_id()
    client_secret = get_client_secret()
    if not client_id or not client_secret:
        raise ValueError("HubSpot app credentials not found.")

    state_data = _load_oauth_state(state)
    if not state_data:
        raise ValueError("Invalid or expired OAuth state. Restart the authorization flow.")
    if state_data["portal_id"] != portal_id:
        raise ValueError("OAuth state mismatch. Restart the authorization flow.")

    code_verifier = state_data["code_verifier"]
    _clear_oauth_state(state)

    _, token_url = get_oauth_endpoints()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "code_verifier": code_verifier,
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

    _, token_url = get_oauth_endpoints()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
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

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from hubspot_agent.client import APIResponse, HubSpotClient
from hubspot_agent.errors import ErrorCategory, HubSpotError, RateLimitError


@dataclass
class ChaosConfig:
    rate_limit_rate: float = 0.05
    network_error_rate: float = 0.01
    truncation_rate: float = 0.001
    chaos_seed: int | None = None
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.chaos_seed) if self.chaos_seed is not None else random.Random()


class ChaosHubSpotClient(HubSpotClient):
    _NETWORK_MESSAGES = [
        "Connection reset by peer",
        "Network is unreachable",
        "Connection timed out",
        "Remote end closed connection without response",
        "DNS resolution failed",
    ]

    def __init__(self, portal, chaos_config: ChaosConfig | None = None) -> None:
        super().__init__(portal)
        self.chaos_config = chaos_config or ChaosConfig()
        self._request_count = 0

    def _select_fault(self) -> str | None:
        cfg = self.chaos_config
        self._request_count += 1
        roll = cfg._rng.random()
        cumulative = 0.0

        cumulative += cfg.rate_limit_rate
        if roll < cumulative:
            return "rate_limit"

        cumulative += cfg.network_error_rate
        if roll < cumulative:
            return "network"

        cumulative += cfg.truncation_rate
        if roll < cumulative:
            return "truncation"

        return None

    async def _request(
        self,
        method: str,
        path: str,
        portal_id: str,
        body: Any | None = None,
        expected_scopes: list[str] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> APIResponse:
        fault = self._select_fault()

        if fault == "rate_limit":
            retry_after = self.chaos_config._rng.randint(1, 30)
            raise RateLimitError(
                "Rate limit exceeded (chaos injected)",
                retry_after=retry_after,
            )

        if fault == "network":
            message = self.chaos_config._rng.choice(self._NETWORK_MESSAGES)
            raise HubSpotError(
                message,
                status_code=503,
                category=ErrorCategory.SERVER,
            )

        if fault == "truncation":
            return await self._request_with_truncation(
                method, path, portal_id, body, expected_scopes, data, files
            )

        return await super()._request(method, path, portal_id, body, expected_scopes)

    async def _request_with_truncation(
        self,
        method: str,
        path: str,
        portal_id: str,
        body: Any | None = None,
        expected_scopes: list[str] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> APIResponse:
        await self._enforce_rate_limit()
        await self._get_fresh_token()
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["json"] = body
        real_resp = await self._client.request(method, path, **kwargs)

        fake_resp = real_resp
        if real_resp.text:
            truncated = real_resp.text[: len(real_resp.text) // 2]
            fake_resp = httpx.Response(
                status_code=real_resp.status_code,
                headers=dict(real_resp.headers),
                text=truncated,
            )

        original_request = self._client.request
        async def _fake_request(*args, **kwargs):
            return fake_resp
        setattr(self._client, "request", _fake_request)
        try:
            return await super()._request(method, path, portal_id, body, expected_scopes)
        finally:
            setattr(self._client, "request", original_request)

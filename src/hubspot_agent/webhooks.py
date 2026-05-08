from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import signal
import time
import uuid
from typing import Any

from aiohttp import web

from hubspot_agent.app_credentials import get_client_secret, load_app_credentials
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig, load_portal_config
from hubspot_agent.orchestrator import dispatch_agent
from hubspot_agent.trace import emit_trace, new_trace_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event routing
# ---------------------------------------------------------------------------

_EVENT_ROUTING: dict[str, str] = {
    "contact": "objects",
    "company": "objects",
    "deal": "objects",
    "ticket": "objects",
    "product": "objects",
    "line_item": "objects",
    "quote": "objects",
    "object": "objects",
    "call": "engagements",
    "email": "engagements",
    "meeting": "engagements",
    "note": "engagements",
    "task": "engagements",
    "conversation": "engagements",
    "workflow": "workflows",
    "list": "lists",
    "property": "properties",
    "pipeline": "pipelines",
    "user": "users",
    "association": "associations",
}


def _resolve_agent(event_type: str) -> str | None:
    prefix = event_type.split(".")[0].lower()
    return _EVENT_ROUTING.get(prefix)


# ---------------------------------------------------------------------------
# WebhookEventProcessor
# ---------------------------------------------------------------------------


class WebhookEventProcessor:
    def process(self, event: dict[str, Any], portal_id: str) -> dict[str, Any]:
        event_type = event.get("subscriptionType", event.get("eventType", "unknown"))
        agent_name = _resolve_agent(event_type)

        trace_id = new_trace_id()
        emit_trace(portal_id, "webhook_received", trace_id, {
            "event_type": event_type,
            "agent": agent_name,
            "object_id": event.get("objectId"),
        })

        if agent_name is None:
            logger.warning("No agent mapping for event type: %s", event_type)
            return {
                "status": "unrouted",
                "event_type": event_type,
                "reason": "No agent mapping found",
            }

        portal_config = load_portal_config(portal_id)
        if portal_config is None:
            logger.error("Portal config not found for portal_id: %s", portal_id)
            return {
                "status": "error",
                "event_type": event_type,
                "reason": f"Portal config not found for {portal_id}",
            }

        user_request = f"Webhook event: {event_type} for {event.get('objectId', 'unknown')}"
        payload = {"webhook_event": event}

        # HITL safety: webhooks run in preview mode so a human must approve
        # the resulting action before any write is executed.
        try:
            result = dispatch_agent(
                agent_name=agent_name,
                user_request=user_request,
                portal_config=portal_config,
                mode="preview",
                payload=payload,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.exception("Agent dispatch failed for event type %s", event_type)
            return {
                "status": "error",
                "event_type": event_type,
                "agent": agent_name,
                "reason": str(exc),
            }

        return {
            "status": result.status,
            "event_type": event_type,
            "agent": agent_name,
            "trace_id": trace_id,
            "result": result.model_dump(),
        }


# ---------------------------------------------------------------------------
# WebhookSubscriptionManager
# ---------------------------------------------------------------------------


class WebhookSubscriptionManager:
    def __init__(self) -> None:
        self._local_urls: dict[str, str] = {}  # subscription_id -> url

    def _app_id(self) -> str:
        creds = load_app_credentials()
        if not creds or "app_id" not in creds:
            raise ValueError("App credentials not configured. Run save_app_credentials() with app_id.")
        return creds["app_id"]

    async def list_subscriptions(self, portal_config: PortalConfig) -> list[dict[str, Any]]:
        app_id = self._app_id()
        client = HubSpotClient(portal_config)
        try:
            resp = await client.get(
                f"/webhooks/v1/{app_id}/subscriptions",
                portal_id=portal_config.portal_id,
            )
        finally:
            await client.close()
        results: list[dict[str, Any]] = resp.body.get("results", [])
        for sub in results:
            sub["targetUrl"] = self._local_urls.get(str(sub.get("id")), "")
        return results

    async def create_subscription(
        self,
        portal_config: PortalConfig,
        event_type: str,
        url: str,
    ) -> dict[str, Any]:
        app_id = self._app_id()
        body = {"subscriptionType": event_type, "enabled": True}
        client = HubSpotClient(portal_config)
        try:
            resp = await client.post(
                f"/webhooks/v1/{app_id}/subscriptions",
                portal_id=portal_config.portal_id,
                body=body,
            )
        finally:
            await client.close()
        sub_id = str(resp.body.get("id"))
        if sub_id:
            self._local_urls[sub_id] = url
        return resp.body

    async def delete_subscription(
        self,
        portal_config: PortalConfig,
        subscription_id: str,
    ) -> dict[str, Any]:
        app_id = self._app_id()
        client = HubSpotClient(portal_config)
        try:
            resp = await client.delete(
                f"/webhooks/v1/{app_id}/subscriptions/{subscription_id}",
                portal_id=portal_config.portal_id,
            )
        finally:
            await client.close()
        self._local_urls.pop(subscription_id, None)
        return resp.body


# ---------------------------------------------------------------------------
# WebhookServer
# ---------------------------------------------------------------------------


class WebhookServer:
    def __init__(
        self,
        client_secret: str,
        portal_id: str,
        event_processor: WebhookEventProcessor | None = None,
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        self.client_secret = client_secret
        self.portal_id = portal_id
        self.event_processor = event_processor or WebhookEventProcessor()
        self.host = host
        self.port = port
        self.event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._processor_task: asyncio.Task[Any] | None = None
        self._shutdown_event = asyncio.Event()

    def _validate_legacy_signature(self, body: bytes, signature_header: str | None) -> bool:
        if not signature_header:
            return False
        expected = base64.b64encode(
            hmac.new(self.client_secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(expected, signature_header)

    def _validate_v3_signature(
        self,
        method: str,
        uri: str,
        body: bytes,
        signature_header: str | None,
        timestamp_header: str | None,
    ) -> bool:
        if not signature_header or not timestamp_header:
            return False
        # Validate timestamp freshness (within 5 minutes)
        try:
            timestamp = int(timestamp_header)
        except ValueError:
            return False
        current_time = int(time.time() * 1000)
        if abs(current_time - timestamp) > 300_000:
            logger.warning("V3 signature timestamp expired: %s", timestamp)
            return False
        # Build raw bytes: method + uri + body + timestamp (HubSpot signs raw bytes)
        raw = method.encode() + uri.encode() + body + str(timestamp).encode()
        expected = base64.b64encode(
            hmac.new(self.client_secret.encode(), raw, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(expected, signature_header)

    def _reconstruct_uri(self, request: web.Request) -> str:
        # When behind a reverse proxy (e.g. ngrok), reconstruct the original URL
        # HubSpot signed the request using the public URL, not the internal one
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host", request.headers.get("Host", ""))
        # Use raw_path to preserve percent-encoding (HubSpot signs the encoded URI)
        path = request.raw_path if request.raw_path else request.path
        query = request.query_string
        if query:
            return f"{scheme}://{host}{path}?{query}"
        return f"{scheme}://{host}{path}"

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        body = await request.read()
        # Try V3 signature first, then fall back to legacy
        v3_signature = request.headers.get("X-HubSpot-Signature-v3")
        v3_timestamp = request.headers.get("X-HubSpot-Request-Timestamp")
        uri = self._reconstruct_uri(request)
        method = request.method

        valid = False
        if v3_signature and v3_timestamp:
            valid = self._validate_v3_signature(
                method=method,
                uri=uri,
                body=body,
                signature_header=v3_signature,
                timestamp_header=v3_timestamp,
            )
            if not valid:
                logger.warning(
                    "Invalid V3 webhook signature from %s (uri=%s)",
                    request.remote,
                    uri,
                )
                return web.Response(status=401, text="Unauthorized")
        else:
            legacy_signature = request.headers.get("X-HubSpot-Signature")
            valid = self._validate_legacy_signature(body, legacy_signature)
            if not valid:
                logger.warning(
                    "Invalid legacy webhook signature from %s (uri=%s)",
                    request.remote,
                    uri,
                )
                return web.Response(status=401, text="Unauthorized")

        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        if isinstance(event, list):
            for item in event:
                await self.event_queue.put(item)
        else:
            await self.event_queue.put(event)

        return web.Response(status=200, text="OK")

    async def _process_events(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                event = await asyncio.wait_for(
                    self.event_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            try:
                self.event_processor.process(event, self.portal_id)
            except Exception:
                logger.exception("Event processing failed")
            finally:
                self.event_queue.task_done()

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/webhooks/hubspot", self._handle_webhook)
        return app

    async def start(self) -> None:
        self._app = self._build_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info("Webhook server started on %s:%s", self.host, self.port)

        self._processor_task = asyncio.create_task(self._process_events())

        # Graceful shutdown on SIGTERM
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

    async def stop(self) -> None:
        logger.info("Webhook server shutting down...")
        self._shutdown_event.set()
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("Webhook server stopped.")

    async def run(self) -> None:
        await self.start()
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

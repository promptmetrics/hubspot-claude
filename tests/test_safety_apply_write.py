"""T4: safety.apply_write — scope gate + preview assembly + pending-record persist.

Locks the extract-and-move contract: apply_write produces the same preview_data
shape and action_id that dispatch_agent's inline preview branch did, raises
ScopeBlocked when the portal lacks a required scope, and never calls the
preview builder or store on a blocked scope.
"""
from __future__ import annotations

import re

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hubspot_agent.config import PortalConfig
from hubspot_agent.models import BatchApprovalMode, PreviewResult, RiskLevel
from hubspot_agent.orchestrator import _parse_agent_intent
from hubspot_agent.safety import ScopeBlocked, apply_write, normalize_informing_sources


def _portal_config(scopes: list[str] | None) -> PortalConfig:
    return PortalConfig(
        portal_id="123",
        token="test-token",
        tier="Professional",
        scopes_granted=scopes,
    )


def _preview() -> PreviewResult:
    return PreviewResult(
        preview={"message": "will delete contact"},
        impact_count=1,
        risk_level=RiskLevel.DESTRUCTIVE,
        original_values={"id": "42"},
        informing_sources=[
            {"url": "https://developers.hubspot.com/docs/api/crm/contacts", "trust_tier": "official"}
        ],
    )


@pytest.mark.asyncio
async def test_apply_write_raises_scope_blocked_when_scope_missing():
    portal = _portal_config(["crm.objects.contacts.read"])
    intent = _parse_agent_intent("objects", "delete contact")

    async def _builder_should_not_run(client):
        raise AssertionError("preview_builder must not run when scope is blocked")

    with patch(
        "hubspot_agent.orchestrator._store_pending_preview",
        new=MagicMock(),
    ) as store_mock:
        with pytest.raises(ScopeBlocked) as exc:
            await apply_write(
                client=object(),
                portal_config=portal,
                preview_builder=_builder_should_not_run,
                agent_name="objects",
                intent=intent,
                request_text="delete contact",
            )

    assert "crm.objects.contacts.delete" in str(exc.value)
    assert exc.value.blocked
    store_mock.assert_not_called()


@pytest.mark.asyncio
async def test_apply_write_skips_scope_when_none_recorded():
    portal = _portal_config(None)
    intent = _parse_agent_intent("objects", "create contact")
    preview = _preview()

    with patch(
        "hubspot_agent.orchestrator._store_pending_preview",
        lambda *a, **k: None,
    ):
        aw = await apply_write(
            client=object(),
            portal_config=portal,
            preview_builder=AsyncMock(return_value=preview),
            agent_name="objects",
            intent=intent,
            request_text="create contact",
            trace_id="trace-1",
            proposed_payload={"properties": {"name": "X"}},
        )

    assert aw.preview is preview
    assert re.fullmatch(r"[0-9a-f]{8}", aw.action_id)


@pytest.mark.asyncio
async def test_apply_write_produces_verbatim_preview_data():
    portal = _portal_config(None)
    intent = _parse_agent_intent("objects", "create contact")
    preview = _preview()
    captured: dict = {}

    def capture_store(pid, aid, data):
        captured["pid"] = pid
        captured["aid"] = aid
        captured["data"] = data

    with patch("hubspot_agent.orchestrator._store_pending_preview", capture_store):
        aw = await apply_write(
            client=object(),
            portal_config=portal,
            preview_builder=AsyncMock(return_value=preview),
            agent_name="objects",
            intent=intent,
            request_text="create contact",
            trace_id="trace-1",
            batch_mode=BatchApprovalMode.PATTERN,
            proposed_payload={"properties": {"name": "X"}},
        )

    # action_id and normalized_sources flow through unchanged.
    assert aw.action_id == captured["aid"]
    assert aw.normalized_sources == normalize_informing_sources(preview.informing_sources)
    assert aw.normalized_sources[0]["trust_tier"] == "official"

    # preview_data is byte-for-byte the shape dispatch_agent produced inline.
    pd = captured["data"]
    assert pd["agent_name"] == "objects"
    assert pd["request_text"] == "create contact"
    assert pd["intent"] == intent.model_dump(mode="json")
    assert pd["preview"] == preview.model_dump(mode="json")
    assert pd["trace_id"] == "trace-1"
    assert pd["batch_mode"] == BatchApprovalMode.PATTERN.value
    assert pd["proposed_payload"] == {"properties": {"name": "X"}}
    assert pd["informing_sources"] == aw.normalized_sources
    assert pd["required_confirmation"] == preview.impact_count
    assert pd["confirmed_count"] is None
    assert captured["pid"] == "123"

    # aw.preview_data matches what was persisted.
    assert aw.preview_data == pd


@pytest.mark.asyncio
async def test_apply_write_persists_via_orchestrator_store_binding():
    """The store call resolves from the orchestrator module so existing
    ``orchestrator._store_pending_preview`` patches intercept it (zero-churn)."""
    portal = _portal_config(None)
    intent = _parse_agent_intent("objects", "create contact")
    preview = _preview()
    store_calls: list = []

    with patch(
        "hubspot_agent.orchestrator._store_pending_preview",
        lambda pid, aid, data: store_calls.append((pid, aid, data)),
    ):
        await apply_write(
            client=object(),
            portal_config=portal,
            preview_builder=AsyncMock(return_value=preview),
            agent_name="objects",
            intent=intent,
            request_text="create contact",
        )

    assert len(store_calls) == 1
    pid, aid, data = store_calls[0]
    assert pid == "123"
    assert re.fullmatch(r"[0-9a-f]{8}", aid)
    assert data["agent_name"] == "objects"
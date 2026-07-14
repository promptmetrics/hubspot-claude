"""T11: shared async handlers (FR-16) — daemon / fallback / CLI share one path.

Exercises ``hubspot_agent.handlers`` with a fake warm client + redirected
CONFIG_DIR so no real HubSpot I/O occurs.  Verifies the tool read/write split,
the approve destructive-count gate (FR-19), reject, and the loop_* handlers.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import hubspot_agent.agents  # noqa: F401 — imports tool submodules so the registry is populated
from hubspot_agent import handlers
from hubspot_agent.config import PortalConfig
from hubspot_agent.handlers import ExecuteError, HandlerError, execute_pending_write, handle_approve, handle_loop_abandon, handle_loop_checkpoint
from hubspot_agent.handlers import handle_loop_continue, handle_loop_log, handle_loop_status
from hubspot_agent.handlers import handle_reject, handle_tool
from hubspot_agent.loop_state import LoopState
from hubspot_agent.models import AgentResult, LoopPlan, PlanStep, RiskLevel
from hubspot_agent.persistence import load as _load_pending


class _FakeResp:
    def __init__(self, body):
        self.body = body


class FakeClient:
    def __init__(self):
        self.posts: list[dict] = []
        self.gets: list[dict] = []

    async def get(self, url, **kw):
        self.gets.append({"url": url, **kw})
        return _FakeResp({"id": "42", "properties": {"firstname": "Izzy"}})

    async def post(self, url, **kw):
        self.posts.append({"url": url, **kw})
        return _FakeResp({"id": "new-1", "properties": kw.get("body", {}).get("properties", {})})

    async def patch(self, url, **kw):
        return _FakeResp({"id": "1", "properties": kw.get("body", {}).get("properties", {})})

    async def delete(self, url, **kw):
        return _FakeResp({"id": "1"})

    async def close(self):
        return None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    return tmp_path


def _portal(*, scopes=None):
    return PortalConfig(portal_id="123", token="test-token", tier="Professional", scopes_granted=scopes)


def _make_loop_state():
    plan = LoopPlan(
        goal="Create two properties",
        steps=[
            PlanStep(step_number=1, agent="properties", action="create a", risk_level=RiskLevel.MEDIUM),
            PlanStep(step_number=2, agent="properties", action="create b", risk_level=RiskLevel.MEDIUM),
        ],
    )
    return LoopState(portal_id="123", request_text="create two properties", trace_id="trace-h", plan=plan, current_step=1)


# ---------------------------------------------------------------------------
# handle_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_tool_read_returns_result(env):
    client = FakeClient()
    out = await handle_tool(client, None, _portal(), {"tool_name": "hubspot_get_object", "input": {"object_type": "contacts", "object_id": "42"}})
    assert out["ok"] is True
    assert out["data"]["tool"] == "hubspot_get_object"
    assert out["data"]["result"]["id"] == "42"
    assert client.gets and "contacts/42" in client.gets[0]["url"]


@pytest.mark.asyncio
async def test_handle_tool_unknown_tool(env):
    with pytest.raises(HandlerError) as exc:
        await handle_tool(FakeClient(), None, _portal(), {"tool_name": "hubspot_bogus", "input": {}})
    assert exc.value.error["kind"] == "not_found"


@pytest.mark.asyncio
async def test_handle_tool_missing_name(env):
    with pytest.raises(HandlerError) as exc:
        await handle_tool(FakeClient(), None, _portal(), {"input": {}})
    assert exc.value.error["kind"] == "validation"


@pytest.mark.asyncio
async def test_handle_tool_write_routes_through_apply_write(env):
    client = FakeClient()
    out = await handle_tool(
        client,
        None,
        _portal(),
        {"tool_name": "hubspot_create_object", "input": {"object_type": "contacts", "properties": {"firstname": "Izzy"}}},
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["status"] == "preview"
    assert data["tool"] == "hubspot_create_object"
    assert data["action_id"]
    assert data["risk_level"] == "medium"
    # The preview was persisted (FR-5b: tool-initiated, no agent).
    pending = _load_pending("123", data["action_id"])
    assert pending is not None
    assert pending["agent_name"] is None
    assert pending["tool_name"] == "hubspot_create_object"


@pytest.mark.asyncio
async def test_handle_tool_scope_blocked(env):
    # Granted read only; create needs .write.
    with pytest.raises(HandlerError) as exc:
        await handle_tool(
            FakeClient(),
            None,
            _portal(scopes=["crm.objects.contacts.read"]),
            {"tool_name": "hubspot_create_object", "input": {"object_type": "contacts", "properties": {"firstname": "Izzy"}}},
        )
    assert exc.value.error["kind"] == "scope"
    assert "crm.objects.contacts.write" in exc.value.error["message"]


@pytest.mark.asyncio
async def test_handle_tool_custom_object_cold_cache_discovers_schema(env, monkeypatch):
    # #5: a custom object_type on a cold cache must trigger schema discovery
    # before the tool validates the type — the agent path's initialize_session
    # behavior, now shared by the tool path.  Exercises the real invoke_tool →
    # _validate_object_type → SchemaCache chain end to end.
    from hubspot_agent.cache import SchemaCache

    discovered: list[bool] = []

    async def _fake_discover(portal_config):
        discovered.append(True)
        cache = SchemaCache(portal_config.portal_id)
        cache.set("custom_thing", {"results": [{"name": "color", "type": "string"}]})
        return ["custom_thing"]

    monkeypatch.setattr("hubspot_agent.cache.discover_custom_schemas", _fake_discover)

    out = await handle_tool(
        FakeClient(),
        None,
        _portal(),
        {"tool_name": "hubspot_get_object", "input": {"object_type": "custom_thing", "object_id": "42"}},
    )
    assert out["ok"] is True
    assert discovered == [True]  # cold cache → discovery ran once
    assert out["data"]["result"]["id"] == "42"


@pytest.mark.asyncio
async def test_handle_tool_standard_object_skips_discovery(env, monkeypatch):
    # Idempotency: a built-in object_type must NOT trigger a /schemas fetch.
    async def _fake_discover(portal_config):
        raise AssertionError("standard object_type must not trigger discovery")

    monkeypatch.setattr("hubspot_agent.cache.discover_custom_schemas", _fake_discover)

    out = await handle_tool(
        FakeClient(),
        None,
        _portal(),
        {"tool_name": "hubspot_get_object", "input": {"object_type": "contacts", "object_id": "42"}},
    )
    assert out["ok"] is True


@pytest.mark.asyncio
async def test_handle_tool_concurrent_writes_offload_persistence(env, monkeypatch):
    # #6: the blocking flock+fsync in persistence must run in a worker thread
    # (asyncio.to_thread) so concurrent daemon write RPCs don't stall the event
    # loop.  A slow, blocking _store_pending_preview should run in worker
    # threads, not on the event-loop thread.
    import threading
    import time

    from hubspot_agent import orchestrator

    thread_ids: list[int] = []

    def _slow_store(portal_id, action_id, data):  # simulates blocking fsync
        thread_ids.append(threading.current_thread().ident)
        time.sleep(0.15)

    monkeypatch.setattr(orchestrator, "_store_pending_preview", _slow_store)

    async def _one_write():
        return await handle_tool(
            FakeClient(),
            None,
            _portal(),
            {"tool_name": "hubspot_create_object", "input": {"object_type": "contacts", "properties": {"firstname": "Izzy"}}},
        )

    results = await asyncio.gather(_one_write(), _one_write())
    assert all(r["ok"] for r in results)
    assert len(thread_ids) == 2
    # Persistence ran in worker threads, not on the event-loop thread — so the
    # blocking sleep did not stall the loop and both writes completed.
    main_tid = threading.current_thread().ident
    assert all(tid != main_tid for tid in thread_ids)


# ---------------------------------------------------------------------------
# handle_approve / handle_reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_approve_not_found(env):
    with pytest.raises(HandlerError) as exc:
        await handle_approve(FakeClient(), None, _portal(), {"action_id": "nope0000"})
    assert exc.value.error["kind"] == "not_found"


@pytest.mark.asyncio
async def test_handle_approve_destructive_requires_count(env):
    from hubspot_agent.persistence import store as _store

    preview_data = {
        "agent_name": None,
        "tool_name": "hubspot_delete_object",
        "request_text": "tool hubspot_delete_object",
        "intent": {"intent_type": "delete", "target_object": "contacts", "risk_level": "destructive"},
        "preview": {"risk_level": "destructive", "impact_count": 5},
        "trace_id": "t",
        "batch_mode": "single",
        "proposed_payload": {"object_type": "contacts", "object_id": "42"},
        "required_confirmation": 5,
        "confirmed_count": None,
    }
    _store("123", "deadbeef", preview_data)
    with pytest.raises(HandlerError) as exc:
        await handle_approve(FakeClient(), None, _portal(), {"action_id": "deadbeef"})
    err = exc.value.error
    assert err["kind"] == "validation"
    assert err["retryable"] is False
    assert "approve deadbeef 5" in err["guidance"]
    # Still pending (no execution, no clear).
    assert _load_pending("123", "deadbeef") is not None


@pytest.mark.asyncio
async def test_handle_approve_executes_tool_preview(env):
    from hubspot_agent.persistence import store as _store

    action_id = "abc12345"
    _store(
        "123",
        action_id,
        {
            "agent_name": None,
            "tool_name": "hubspot_create_object",
            "request_text": "tool hubspot_create_object",
            "intent": {"intent_type": "create", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1},
            "trace_id": "t",
            "batch_mode": "single",
            "proposed_payload": {"object_type": "contacts", "properties": {"firstname": "Izzy"}},
            "required_confirmation": 1,
            "confirmed_count": None,
        },
    )
    client = FakeClient()
    out = await handle_approve(client, None, _portal(), {"action_id": action_id})
    assert out["ok"] is True
    assert out["data"]["tool"] == "hubspot_create_object"
    assert out["data"]["status"] == "success"
    assert client.posts  # the create hit the fake client
    # Pending cleared after execute.
    assert _load_pending("123", action_id) is None


@pytest.mark.asyncio
async def test_handle_approve_writes_undo_snapshot_and_audit(env):
    from hubspot_agent import audit
    from hubspot_agent.persistence import store as _store
    from hubspot_agent.snapshot import load_undo_snapshot, snapshot_dir_for_portal

    action_id = "ok123456"
    _store(
        "123",
        action_id,
        {
            "agent_name": None,
            "tool_name": "hubspot_create_object",
            "request_text": "tool hubspot_create_object",
            "intent": {"intent_type": "create", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1, "original_values": {}},
            "proposed_payload": {"object_type": "contacts", "properties": {"firstname": "Izzy"}},
            "required_confirmation": 1,
            "confirmed_count": None,
            "informing_sources": [],
        },
    )
    out = await handle_approve(FakeClient(), None, _portal(), {"action_id": action_id})
    assert out["ok"] is True
    # Undo snapshot captured with the created id (FR-17/FR-18).
    snap = load_undo_snapshot(snapshot_dir_for_portal("123"), action_id)
    assert snap is not None
    assert snap["metadata"]["intent_type"] == "create"
    assert snap["metadata"]["created_ids"] == ["new-1"]
    # Audit record written (FR-17).
    entries = audit.get_recent_audits("123", limit=5)
    assert any(e["action"] == f"approve:{action_id}" for e in entries)


@pytest.mark.asyncio
async def test_handle_approve_surfaces_audit_failed_in_response(env, monkeypatch):
    from hubspot_agent import audit
    from hubspot_agent.persistence import store as _store

    action_id = "aud00001"
    _store(
        "123",
        action_id,
        {
            "agent_name": None,
            "tool_name": "hubspot_create_object",
            "request_text": "tool hubspot_create_object",
            "intent": {"intent_type": "create", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1, "original_values": {}},
            "proposed_payload": {"object_type": "contacts", "properties": {"firstname": "Izzy"}},
            "required_confirmation": 1,
            "confirmed_count": None,
            "informing_sources": [],
        },
    )

    def _boom(**kwargs):
        raise RuntimeError("audit disk on fire")

    monkeypatch.setattr(audit, "log_write", _boom)

    out = await handle_approve(FakeClient(), None, _portal(), {"action_id": action_id})
    assert out["ok"] is True
    assert out["data"]["status"] == "success"
    assert out["data"]["audit_failed"] is True


@pytest.mark.asyncio
async def test_handle_approve_tool_soft_failure_keeps_preview(env, monkeypatch):
    from hubspot_agent.persistence import store as _store
    from hubspot_agent.snapshot import snapshot_dir_for_portal

    action_id = "soft0001"
    _store(
        "123",
        action_id,
        {
            "agent_name": None,
            "tool_name": "hubspot_create_object",
            "request_text": "tool hubspot_create_object",
            "intent": {"intent_type": "create", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1},
            "proposed_payload": {"object_type": "contacts", "properties": {"firstname": "Izzy"}},
            "required_confirmation": 1,
            "confirmed_count": None,
        },
    )

    async def _fail(tool_name, portal_id, client=None, **kw):
        return {"error": "hubspot said no", "tool": "hubspot_create_object"}

    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", _fail)

    with pytest.raises(HandlerError) as exc:
        await handle_approve(FakeClient(), None, _portal(), {"action_id": action_id})
    err = exc.value.error
    assert err["kind"] == "server"
    assert "hubspot said no" in err["message"]
    # Preview still on disk (retryable) — no false success, no clear.
    assert _load_pending("123", action_id) is not None
    # Snapshot dropped: nothing changed, so there is nothing to undo.
    snap = Path(snapshot_dir_for_portal("123")) / f"{action_id}.json"
    assert not snap.exists()


@pytest.mark.asyncio
async def test_handle_approve_destructive_none_required_not_bypassed(env):
    from hubspot_agent.persistence import store as _store

    action_id = "nonereq1"
    _store(
        "123",
        action_id,
        {
            "agent_name": None,
            "tool_name": "hubspot_delete_object",
            "request_text": "tool hubspot_delete_object",
            "intent": {"intent_type": "delete", "target_object": "contacts", "risk_level": "destructive"},
            "preview": {"risk_level": "destructive", "impact_count": 5},
            "proposed_payload": {"object_type": "contacts", "object_id": "42"},
            "required_confirmation": None,
            "confirmed_count": None,
        },
    )
    # required_confirmation=None must coerce to 0, not bypass the gate via
    # None == None. With no confirm_count supplied, a destructive action is
    # rejected and the preview is left on disk.
    with pytest.raises(HandlerError) as exc:
        await handle_approve(FakeClient(), None, _portal(), {"action_id": action_id})
    assert exc.value.error["kind"] == "validation"
    assert _load_pending("123", action_id) is not None


# ---------------------------------------------------------------------------
# execute_pending_write (the shared core used by handle_approve + cli._handle_approve)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_pending_write_not_found(env):
    with pytest.raises(ExecuteError) as exc:
        await execute_pending_write(_portal(), "missing-id")
    assert exc.value.kind == "not_found"


@pytest.mark.asyncio
async def test_execute_pending_write_destructive_wrong_count(env):
    from hubspot_agent.persistence import store as _store

    action_id = "dcount1"
    _store(
        "123",
        action_id,
        {
            "agent_name": "objects",
            "request_text": "delete contacts",
            "intent": {"intent_type": "delete", "target_object": "contacts", "risk_level": "destructive"},
            "preview": {"risk_level": "destructive", "impact_count": 5},
            "trace_id": "t",
            "batch_mode": "single",
            "proposed_payload": {"object_type": "contacts", "object_id": "42"},
            "required_confirmation": 5,
            "confirmed_count": None,
        },
    )
    with pytest.raises(ExecuteError) as exc:
        await execute_pending_write(_portal(), action_id, confirm_count=3)
    assert exc.value.kind == "validation"
    assert exc.value.retryable is False
    assert "approve dcount1 5" in (exc.value.guidance or "")
    # Gate rejected before execution — preview still on disk.
    assert _load_pending("123", action_id) is not None


@pytest.mark.asyncio
async def test_execute_pending_write_agent_error_keeps_pending(env, monkeypatch):
    from hubspot_agent.persistence import store as _store
    from hubspot_agent.snapshot import snapshot_dir_for_portal

    action_id = "agerr01"
    _store(
        "123",
        action_id,
        {
            "agent_name": "objects",
            "request_text": "create contact",
            "intent": {"intent_type": "create", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1, "original_values": {}},
            "trace_id": "t",
            "batch_mode": "single",
            "proposed_payload": {"properties": {"firstname": "x"}},
            "required_confirmation": 1,
            "confirmed_count": None,
        },
    )

    async def _fail(*a, **k):
        return AgentResult(agent_name="objects", status="error", error_message="boom", retryable=True)

    monkeypatch.setattr("hubspot_agent.orchestrator.dispatch_agent", _fail)

    with pytest.raises(ExecuteError) as exc:
        await execute_pending_write(_portal(), action_id)
    assert exc.value.kind == "server"
    assert exc.value.retryable is True
    # Retryable: preview still on disk, snapshot dropped (nothing changed).
    assert _load_pending("123", action_id) is not None
    assert not (Path(snapshot_dir_for_portal("123")) / f"{action_id}.json").exists()


@pytest.mark.asyncio
async def test_execute_pending_write_tool_error_keeps_pending(env, monkeypatch):
    from hubspot_agent.persistence import store as _store
    from hubspot_agent.snapshot import snapshot_dir_for_portal

    action_id = "toolerr1"
    _store(
        "123",
        action_id,
        {
            "agent_name": None,
            "tool_name": "hubspot_create_object",
            "request_text": "tool hubspot_create_object",
            "intent": {"intent_type": "create", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1, "original_values": {}},
            "trace_id": "t",
            "batch_mode": "single",
            "proposed_payload": {"object_type": "contacts", "properties": {"firstname": "x"}},
            "required_confirmation": 1,
            "confirmed_count": None,
        },
    )

    async def _fail(tool_name, portal_id, client=None, **kw):
        return {"error": "hubspot said no"}

    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", _fail)

    with pytest.raises(ExecuteError) as exc:
        await execute_pending_write(_portal(), action_id)
    assert exc.value.kind == "server"
    assert exc.value.retryable is True
    assert _load_pending("123", action_id) is not None
    assert not (Path(snapshot_dir_for_portal("123")) / f"{action_id}.json").exists()


@pytest.mark.asyncio
async def test_execute_pending_write_create_captures_created_ids(env, monkeypatch):
    from hubspot_agent.persistence import store as _store
    from hubspot_agent.snapshot import load_undo_snapshot, snapshot_dir_for_portal

    action_id = "crtids1"
    _store(
        "123",
        action_id,
        {
            "agent_name": "objects",
            "request_text": "create contact",
            "intent": {"intent_type": "create", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1, "original_values": {}},
            "trace_id": "t",
            "batch_mode": "single",
            "proposed_payload": {"properties": {"firstname": "x"}},
            "required_confirmation": 1,
            "confirmed_count": None,
        },
    )

    async def _ok(*a, **k):
        return AgentResult(agent_name="objects", status="success", data={"result": {"id": "contact-999"}})

    monkeypatch.setattr("hubspot_agent.orchestrator.dispatch_agent", _ok)

    r = await execute_pending_write(_portal(), action_id)
    assert r.status == "success"
    assert r.created_ids == ["contact-999"]
    snap = load_undo_snapshot(snapshot_dir_for_portal("123"), action_id)
    assert snap is not None
    assert snap["metadata"]["created_ids"] == ["contact-999"]


@pytest.mark.asyncio
async def test_execute_pending_write_success_clears_pending_and_audits(env, monkeypatch):
    from hubspot_agent import audit
    from hubspot_agent.persistence import store as _store

    action_id = "okaudt1"
    _store(
        "123",
        action_id,
        {
            "agent_name": "objects",
            "request_text": "update contact",
            "intent": {"intent_type": "update", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1, "original_values": {"1": {"email": "old@example.com"}}},
            "trace_id": "t",
            "batch_mode": "single",
            "proposed_payload": {"object_type": "contacts", "object_id": "1", "properties": {"email": "new@example.com"}},
            "required_confirmation": 1,
            "confirmed_count": None,
            "informing_sources": [],
        },
    )

    async def _ok(*a, **k):
        return AgentResult(agent_name="objects", status="success", data={"message": "updated"})

    monkeypatch.setattr("hubspot_agent.orchestrator.dispatch_agent", _ok)

    r = await execute_pending_write(_portal(), action_id)
    assert r.status == "success"
    # Pending cleared only on success.
    assert _load_pending("123", action_id) is None
    entries = audit.get_recent_audits("123", limit=5)
    assert any(e["action"] == f"approve:{action_id}" for e in entries)


@pytest.mark.asyncio
async def test_handle_reject_clears(env):
    from hubspot_agent.persistence import store as _store

    _store("123", "rej1234", {
        "agent_name": None,
        "tool_name": "hubspot_create_object",
        "preview": {"risk_level": "medium"},
        "proposed_payload": {},
        "required_confirmation": 1,
        "confirmed_count": None,
    })
    out = await handle_reject(FakeClient(), None, _portal(), {"action_id": "rej1234"})
    assert out["ok"] is True
    assert out["data"]["rejected"] == "rej1234"
    assert _load_pending("123", "rej1234") is None


@pytest.mark.asyncio
async def test_handle_reject_not_found(env):
    with pytest.raises(HandlerError) as exc:
        await handle_reject(FakeClient(), None, _portal(), {"action_id": "nope0000"})
    assert exc.value.error["kind"] == "not_found"


# ---------------------------------------------------------------------------
# loop_* handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_loop_status_no_loop(env):
    with pytest.raises(HandlerError) as exc:
        await handle_loop_status(FakeClient(), None, _portal(), {})
    assert exc.value.error["kind"] == "not_found"


@pytest.mark.asyncio
async def test_handle_loop_status_shows_state(env):
    from hubspot_agent import loop_state

    loop_state.save(_make_loop_state())
    out = await handle_loop_status(FakeClient(), None, _portal(), {})
    assert out["ok"] is True
    assert out["data"]["goal"] == "Create two properties"
    assert out["data"]["current_step"] == 2
    assert out["data"]["total_steps"] == 2


@pytest.mark.asyncio
async def test_handle_loop_checkpoint_logs_and_saves(env):
    from hubspot_agent import loop_log, loop_state

    loop_state.save(_make_loop_state())
    out = await handle_loop_checkpoint(FakeClient(), None, _portal(), {})
    assert out["ok"] is True
    assert out["data"]["current_step"] == 2
    events = loop_log.get_recent("123", trace_id="trace-h", limit=50)
    assert any(e.get("event_type") == "loop_checkpoint" for e in events)


@pytest.mark.asyncio
async def test_handle_loop_abandon_clears(env):
    from hubspot_agent import loop_state

    loop_state.save(_make_loop_state())
    out = await handle_loop_abandon(FakeClient(), None, _portal(), {})
    assert out["ok"] is True
    assert out["data"]["abandoned"] is True
    assert loop_state.load("123") is None


@pytest.mark.asyncio
async def test_handle_loop_continue_defers(env):
    from hubspot_agent import loop_state

    loop_state.save(_make_loop_state())
    out = await handle_loop_continue(FakeClient(), None, _portal(), {})
    assert out["ok"] is True
    assert out["data"]["deferred"] is True
    assert out["data"]["trace_id"] == "trace-h"
    # State is NOT cleared by continue.
    assert loop_state.load("123") is not None


@pytest.mark.asyncio
async def test_handle_loop_log_returns_events(env):
    from hubspot_agent import loop_log, loop_state

    loop_state.save(_make_loop_state())
    loop_log.log_event("123", "trace-h", "step_started", {"step": 1})
    out = await handle_loop_log(FakeClient(), None, _portal(), {"limit": 5})
    assert out["ok"] is True
    assert any(e["event_type"] == "step_started" for e in out["data"]["events"])


def test_handler_error_shape():
    err = HandlerError("rate_limit", "slow down", retryable=True, retry_after=1.5, guidance="wait")
    assert err.error == {"kind": "rate_limit", "message": "slow down", "retryable": True, "retry_after": 1.5, "guidance": "wait"}


def test_handlers_registry_covers_methods():
    expected = {"tool", "approve", "reject", "loop_status", "loop_log", "loop_checkpoint", "loop_abandon", "loop_continue", "serve_stop"}
    assert expected <= set(handlers.HANDLERS)


# ---------------------------------------------------------------------------
# execute_pending_write silent-failure hardening (A/B/C/D)
# ---------------------------------------------------------------------------


def _store_create_pending(action_id: str, *, agent_name: str | None = None, tool_name: str | None = None) -> None:
    """Helper: persist a create-intent pending preview used by the hardening tests."""
    from hubspot_agent.persistence import store as _store

    _store(
        "123",
        action_id,
        {
            "agent_name": agent_name,
            "tool_name": tool_name,
            "request_text": "create contact",
            "intent": {"intent_type": "create", "target_object": "contacts", "risk_level": "medium"},
            "preview": {"risk_level": "medium", "impact_count": 1, "original_values": {}},
            "trace_id": "t",
            "batch_mode": "single",
            "proposed_payload": (
                {"properties": {"firstname": "x"}}
                if agent_name
                else {"object_type": "contacts", "properties": {"firstname": "x"}}
            ),
            "required_confirmation": 1,
            "confirmed_count": None,
        },
    )


@pytest.mark.asyncio
async def test_execute_pending_write_invoke_tool_raises_surfaces_retryable_and_drops_snapshot(env, monkeypatch):
    # A: a raw (non-ExecuteError) raise from invoke_tool must surface as a
    # retryable ExecuteError("server", ...), drop the undo snapshot, and leave
    # the pending preview on disk so the caller can retry.
    from hubspot_agent.snapshot import snapshot_dir_for_portal

    action_id = "rawr001"
    _store_create_pending(action_id, tool_name="hubspot_create_object")

    async def _boom(tool_name, portal_id, client=None, **kw):
        raise RuntimeError("network boom")

    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", _boom)

    with pytest.raises(ExecuteError) as exc:
        await execute_pending_write(_portal(), action_id)
    assert exc.value.kind == "server"
    assert exc.value.retryable is True
    assert "network boom" in exc.value.message
    # Pending still on disk (retryable, no clear).
    assert _load_pending("123", action_id) is not None
    # Snapshot dropped because nothing was changed to undo.
    assert not (Path(snapshot_dir_for_portal("123")) / f"{action_id}.json").exists()


@pytest.mark.asyncio
async def test_execute_pending_write_client_close_failure_does_not_mask_success(env, monkeypatch):
    # B: a failure in client.close() in the owned-client tool branch must NOT
    # turn a successful write into a failure (which would invite a duplicate
    # re-approve) nor mask a primary error.  Patch invoke_tool to return a
    # success payload and HubSpotClient.close to raise.
    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.snapshot import load_undo_snapshot, snapshot_dir_for_portal

    action_id = "close01"
    _store_create_pending(action_id, tool_name="hubspot_create_object")

    async def _ok(tool_name, portal_id, client=None, **kw):
        return {"id": "new-77", "properties": {"firstname": "x"}}

    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", _ok)

    async def _bad_close(self):
        raise RuntimeError("close blew up")

    monkeypatch.setattr(HubSpotClient, "close", _bad_close)

    r = await execute_pending_write(_portal(), action_id)
    # The write succeeded — close failure must not flip it to an error.
    assert r.status == "success"
    assert r.created_ids == ["new-77"]
    # Pending cleared (write committed); no duplicate-write invitation.
    assert _load_pending("123", action_id) is None
    # Snapshot retained with the created id (FR-17/18).
    snap = load_undo_snapshot(snapshot_dir_for_portal("123"), action_id)
    assert snap is not None
    assert snap["metadata"]["created_ids"] == ["new-77"]


@pytest.mark.asyncio
async def test_execute_pending_write_audit_failure_does_not_fail_the_write(env, monkeypatch):
    # C: audit.log_write runs after the write committed and pending was
    # cleared, so a failure there must not flip success to failure nor be
    # swallowed silently.  Surface via audit_failed=True on the ExecuteResult.
    action_id = "audt01"
    _store_create_pending(action_id, agent_name="objects")

    async def _ok(*a, **k):
        return AgentResult(agent_name="objects", status="success", data={"result": {"id": "c-1"}})

    monkeypatch.setattr("hubspot_agent.orchestrator.dispatch_agent", _ok)

    def _bad_audit(**kw):
        raise RuntimeError("audit disk full")

    monkeypatch.setattr("hubspot_agent.audit.log_write", _bad_audit)

    r = await execute_pending_write(_portal(), action_id)
    assert r.status == "success"
    assert r.created_ids == ["c-1"]
    assert r.audit_failed is True
    # Pending was cleared (write committed); re-approve would NOT duplicate.
    assert _load_pending("123", action_id) is None


@pytest.mark.asyncio
async def test_execute_pending_write_create_without_id_is_loud(env, monkeypatch, capsys):
    # D: a create that succeeds with NO id in the response must never silently
    # yield empty created_ids AND never invite a duplicate re-approve.  Chosen
    # semantics (see handlers.py comment): clear pending (write is done —
    # re-running would duplicate), KEEP the snapshot for manual inspection,
    # log loudly to stderr, and return empty created_ids as a loud signal.
    from hubspot_agent.snapshot import load_undo_snapshot, snapshot_dir_for_portal

    action_id = "noid01"
    _store_create_pending(action_id, agent_name="objects")

    async def _ok(*a, **k):
        # Create succeeded but the response carries no id.
        return AgentResult(agent_name="objects", status="success", data={"result": {}})

    monkeypatch.setattr("hubspot_agent.orchestrator.dispatch_agent", _ok)

    r = await execute_pending_write(_portal(), action_id)
    assert r.status == "success"
    # Pin the loud semantic: empty created_ids is the explicit signal, not a
    # silent default — the operator must treat empty-on-create as a warning.
    assert r.created_ids == []
    # Pending cleared: re-approve would duplicate the create, so it must NOT
    # be left retryable.
    assert _load_pending("123", action_id) is None
    # Snapshot retained for manual inspection / reconciliation.
    assert load_undo_snapshot(snapshot_dir_for_portal("123"), action_id) is not None
    # Loud warning emitted to stderr.
    captured = capsys.readouterr()
    assert "no created id found" in captured.err


# ---------------------------------------------------------------------------
# M5: the shared preview builder captures BOTH records for a merge, and the
# .delete scope makes the preview destructive.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_preview_fetches_both_records(respx_mock):
    import httpx

    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.handlers import _build_tool_preview

    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value=httpx.Response(200, json={"id": "1", "properties": {"email": "primary@example.com"}})
    )
    respx_mock.get("https://api.hubapi.com/crm/v3/objects/contacts/2").mock(
        return_value=httpx.Response(200, json={"id": "2", "properties": {"email": "dup@example.com"}})
    )
    preview = await _build_tool_preview(
        "hubspot_merge_objects",
        {"primary_object_id": "1", "object_id_to_merge": "2", "object_type": "contacts"},
        {"crm.objects.contacts.write", "crm.objects.contacts.delete"},
        c,
        "123",
    )
    assert preview.original_values == {
        "1": {"email": "primary@example.com"},
        "2": {"email": "dup@example.com"},
    }
    assert preview.risk_level == RiskLevel.DESTRUCTIVE
    # object_type rides in the preview input so HITL can see what's merged.
    assert preview.preview["input"]["object_type"] == "contacts"
    await c.close()
"""T6: `hubspot tool <name> [--input <json>|-]` dispatcher.

Reads route through ``invoke_tool`` and return JSON.  Writes route through
``safety.apply_write`` with a tool-level preview builder (no agent/runtime
fabrication, FR-5b).  Scope is resolved via ``scope_registry.get_required_scopes``.
Tool-initiated previews are executable via ``hubspot approve <id>``.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from hubspot_agent.cli import hubspot_command
from hubspot_agent.config import PortalConfig, save_portal_config
from hubspot_agent.models import PreviewResult, RiskLevel
from hubspot_agent.safety import ApplyWriteResult


def _bootstrap_portal(tmp_path, monkeypatch, *, scopes=None):
    """Redirect CONFIG_DIR to tmp_path and write a portal + .hubspot-portal file."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from hubspot_agent import cli, orchestrator

    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.orchestrator.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
    (tmp_path / ".hubspot-portal").write_text("123\n")
    save_portal_config(
        PortalConfig(portal_id="123", token="test-token", tier="Professional", scopes_granted=scopes)
    )
    return cli, orchestrator


def _fake_apply_write_result(tool_name):
    preview = PreviewResult(
        preview={"tool": tool_name, "input": {}, "message": f"Preview of {tool_name}"},
        impact_count=1,
        risk_level=RiskLevel.MEDIUM,
        original_values={},
        informing_sources=[],
    )
    return ApplyWriteResult(
        preview=preview,
        action_id="abcd1234",
        normalized_sources=[],
        preview_data={"tool_name": tool_name, "agent_name": None},
    )


# ---------------------------------------------------------------------------
# Arg parsing + unknown-tool handling
# ---------------------------------------------------------------------------


def test_tool_bare_returns_usage(tmp_path):
    out = hubspot_command("tool", working_dir=str(tmp_path))
    assert "Usage: /hubspot tool <name>" in out


def test_tool_unknown_lists_known_tools(tmp_path, monkeypatch):
    _bootstrap_portal(tmp_path, monkeypatch)
    out = hubspot_command("tool hubspot_bogus", working_dir=str(tmp_path))
    assert "Unknown tool: hubspot_bogus" in out
    assert "hubspot_get_object" in out  # known-tools listing


def test_tool_no_portal(tmp_path, monkeypatch):
    # No .hubspot-portal written.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from hubspot_agent import cli

    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    out = hubspot_command("tool hubspot_get_object", working_dir=str(tmp_path))
    assert "No default portal found" in out


def test_tool_input_reads_stdin(tmp_path, monkeypatch):
    cli, _ = _bootstrap_portal(tmp_path, monkeypatch)

    captured: dict = {}

    async def mock_invoke(tool_name, portal_id, **kwargs):
        captured.update(kwargs)
        captured["tool_name"] = tool_name
        return {"id": "1", "properties": {"foo": "bar"}}

    monkeypatch.setattr(cli, "invoke_tool", mock_invoke)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"object_type":"contacts","object_id":"1"}'))

    out = hubspot_command(
        "tool hubspot_get_object --input -", working_dir=str(tmp_path)
    )
    payload = json.loads(out)
    assert payload["id"] == "1"
    assert captured["object_type"] == "contacts"
    assert captured["object_id"] == "1"


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------


def test_tool_read_invokes_invoke_tool_and_returns_json(tmp_path, monkeypatch):
    cli, _ = _bootstrap_portal(tmp_path, monkeypatch)

    seen: dict = {}

    async def mock_invoke(tool_name, portal_id, **kwargs):
        seen["tool"] = tool_name
        seen["portal_id"] = portal_id
        seen["kwargs"] = kwargs
        return {"id": "42", "properties": {"firstname": "Izzy"}}

    monkeypatch.setattr(cli, "invoke_tool", mock_invoke)

    out = hubspot_command(
        'tool hubspot_get_object --input {"object_type":"contacts","object_id":"42"}',
        working_dir=str(tmp_path),
    )
    payload = json.loads(out)
    assert payload["id"] == "42"
    assert seen["tool"] == "hubspot_get_object"
    assert seen["kwargs"]["object_type"] == "contacts"
    assert seen["kwargs"]["object_id"] == "42"
    # client + portal_id are injected, not echoed from the input.
    assert "client" in seen["kwargs"]


def test_tool_read_custom_object_warms_schema(tmp_path, monkeypatch):
    # #5: the CLI tool read path must warm custom schemas for a custom
    # object_type on a cold cache (it does not go through handlers.handle_tool).
    cli, _ = _bootstrap_portal(tmp_path, monkeypatch)

    async def mock_invoke(tool_name, portal_id, **kwargs):
        return {"id": "42", "properties": {}}

    monkeypatch.setattr(cli, "invoke_tool", mock_invoke)

    discovered: list[bool] = []

    async def _fake_discover(portal_config):
        discovered.append(True)
        return ["custom_thing"]

    monkeypatch.setattr("hubspot_agent.cache.discover_custom_schemas", _fake_discover)

    out = hubspot_command(
        'tool hubspot_get_object --input {"object_type":"custom_thing","object_id":"42"}',
        working_dir=str(tmp_path),
    )
    assert json.loads(out)["id"] == "42"
    assert discovered == [True]  # CLI tool path triggered schema discovery


def test_tool_read_standard_object_skips_discovery(tmp_path, monkeypatch):
    # #5 idempotency: a built-in object_type must not trigger a /schemas fetch.
    cli, _ = _bootstrap_portal(tmp_path, monkeypatch)

    async def mock_invoke(tool_name, portal_id, **kwargs):
        return {"id": "42"}

    monkeypatch.setattr(cli, "invoke_tool", mock_invoke)

    async def _fake_discover(portal_config):
        raise AssertionError("standard object_type must not trigger discovery")

    monkeypatch.setattr("hubspot_agent.cache.discover_custom_schemas", _fake_discover)

    out = hubspot_command(
        'tool hubspot_get_object --input {"object_type":"contacts","object_id":"42"}',
        working_dir=str(tmp_path),
    )
    assert json.loads(out)["id"] == "42"


def test_tool_read_scope_blocked(tmp_path, monkeypatch):
    # Grant write but not read → read tool must be blocked.
    _bootstrap_portal(tmp_path, monkeypatch, scopes=["crm.objects.contacts.write"])
    out = hubspot_command(
        'tool hubspot_search_objects --input {"object_type":"contacts"}',
        working_dir=str(tmp_path),
    )
    assert "Missing HubSpot OAuth scopes" in out
    assert "crm.objects.contacts.read" in out


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------


def test_tool_write_routes_through_apply_write(tmp_path, monkeypatch):
    cli, _ = _bootstrap_portal(tmp_path, monkeypatch)

    captured: dict = {}

    async def fake_apply_write(*, client, portal_config, preview_builder, **kwargs):
        captured.update(kwargs)
        assert callable(preview_builder)
        return _fake_apply_write_result(kwargs.get("tool_name", "hubspot_create_object"))

    monkeypatch.setattr(cli, "_apply_write", fake_apply_write)

    out = hubspot_command(
        'tool hubspot_create_object --input {"object_type":"contacts","properties":{"firstname":"Izzy"}}',
        working_dir=str(tmp_path),
    )
    payload = json.loads(out)
    assert payload["status"] == "preview"
    assert payload["tool"] == "hubspot_create_object"
    assert payload["action_id"] == "abcd1234"
    # FR-5b: writes go through apply_write with NO agent.
    assert captured["agent_name"] is None
    assert captured["tool_name"] == "hubspot_create_object"
    assert captured["intent"].intent_type == "create"
    assert captured["intent"].target_object == "contacts"
    assert captured["proposed_payload"]["properties"]["firstname"] == "Izzy"


def test_tool_workflow_create_from_blueprint_routes_through_apply_write(tmp_path, monkeypatch):
    """Regression: hubspot_create_workflow_from_blueprint carries the bare
    {"automation"} scope (no .write suffix), so it only gates via WRITE_TOOLS
    membership. The CLI _handle_tool path must pass tool_name to _is_write_tool
    or the write bypasses HITL and POSTs directly. (The 0.2.0 HITL fix only
    reached the daemon path, handlers.py; this guards the CLI/in-process path.)"""
    cli, _ = _bootstrap_portal(tmp_path, monkeypatch)

    captured: dict = {}

    async def fake_apply_write(*, client, portal_config, preview_builder, **kwargs):
        captured.update(kwargs)
        return _fake_apply_write_result(kwargs.get("tool_name", "hubspot_create_workflow_from_blueprint"))

    monkeypatch.setattr(cli, "_apply_write", fake_apply_write)

    out = hubspot_command(
        'tool hubspot_create_workflow_from_blueprint --input {"blueprint_name":"welcome_email","params":{}}',
        working_dir=str(tmp_path),
    )
    payload = json.loads(out)
    assert payload["status"] == "preview"
    assert payload["tool"] == "hubspot_create_workflow_from_blueprint"
    assert payload["action_id"] == "abcd1234"
    # The write routed through apply_write (HITL), not invoke_tool direct (POST).
    assert captured["tool_name"] == "hubspot_create_workflow_from_blueprint"
    assert captured["agent_name"] is None
    assert captured["proposed_payload"]["blueprint_name"] == "welcome_email"


def test_tool_delete_classified_destructive(tmp_path, monkeypatch):
    cli, _ = _bootstrap_portal(tmp_path, monkeypatch)

    async def fake_apply_write(*, client, portal_config, preview_builder, **kwargs):
        assert kwargs["intent"].intent_type == "delete"
        preview = PreviewResult(
            preview={"tool": "hubspot_delete_object"},
            impact_count=1,
            risk_level=RiskLevel.DESTRUCTIVE,
            original_values={"42": {"firstname": "Izzy"}},
            informing_sources=[],
        )
        return ApplyWriteResult(
            preview=preview,
            action_id="deadbeef",
            normalized_sources=[],
            preview_data={},
        )

    monkeypatch.setattr(cli, "_apply_write", fake_apply_write)

    out = hubspot_command(
        'tool hubspot_delete_object --input {"object_type":"contacts","object_id":"42"}',
        working_dir=str(tmp_path),
    )
    payload = json.loads(out)
    assert payload["risk_level"] == "destructive"
    assert payload["original_values"] == {"42": {"firstname": "Izzy"}}


def test_tool_write_scope_blocked(tmp_path, monkeypatch):
    _bootstrap_portal(tmp_path, monkeypatch, scopes=["crm.objects.contacts.read"])
    out = hubspot_command(
        'tool hubspot_delete_object --input {"object_type":"contacts","object_id":"42"}',
        working_dir=str(tmp_path),
    )
    assert "Missing HubSpot OAuth scopes" in out
    assert "crm.objects.contacts.delete" in out


# ---------------------------------------------------------------------------
# Execute path: approve a tool-initiated preview
# ---------------------------------------------------------------------------


def test_approve_executes_tool_initiated_preview(tmp_path, monkeypatch):
    cli, _ = _bootstrap_portal(tmp_path, monkeypatch)
    # Let the real apply_write run so a pending preview is persisted; the store
    # binding writes under the redirected CONFIG_DIR (tmp_path).

    out = hubspot_command(
        'tool hubspot_create_object --input {"object_type":"contacts","properties":{"firstname":"Izzy"}}',
        working_dir=str(tmp_path),
    )
    preview_payload = json.loads(out)
    action_id = preview_payload["action_id"]

    # The preview must have been persisted (real store under tmp_path).
    from hubspot_agent.persistence import load as load_pending

    pending = load_pending("123", action_id)
    assert pending is not None
    assert pending["tool_name"] == "hubspot_create_object"
    assert pending["agent_name"] is None
    assert pending["intent"]["intent_type"] == "create"

    # Now execute via approve: invoke_tool must be called with the proposed payload.
    executed: dict = {}

    async def mock_invoke(tool_name, portal_id, **kwargs):
        executed["tool"] = tool_name
        executed["kwargs"] = kwargs
        return {"id": "999", "properties": kwargs.get("properties", {})}

    # execute_pending_write (handlers.py) looks up invoke_tool at module level
    # on hubspot_agent.handlers, so patch it there, not on cli.
    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", mock_invoke)

    result = hubspot_command(f"approve {action_id}", working_dir=str(tmp_path))
    assert "Approved and executed" in result
    assert executed["tool"] == "hubspot_create_object"
    assert executed["kwargs"]["properties"]["firstname"] == "Izzy"
    assert executed["kwargs"]["object_type"] == "contacts"


def test_cli_approve_soft_failure_keeps_preview(tmp_path, monkeypatch):
    """A soft tool failure during approve must NOT false-succeed or clear the
    preview — the preview stays on disk (retryable) and the snapshot is dropped
    (nothing changed to undo).  Pins the Phase C behavior change (CLI no longer
    clears-then-fails) against the shared execute_pending_write core.
    """
    _bootstrap_portal(tmp_path, monkeypatch)

    out = hubspot_command(
        'tool hubspot_create_object --input {"object_type":"contacts","properties":{"firstname":"Izzy"}}',
        working_dir=str(tmp_path),
    )
    action_id = json.loads(out)["action_id"]

    from hubspot_agent.persistence import load as load_pending
    from hubspot_agent.snapshot import snapshot_dir_for_portal

    assert load_pending("123", action_id) is not None

    async def mock_invoke(tool_name, portal_id, **kwargs):
        return {"error": "hubspot said no"}

    # execute_pending_write (handlers.py) looks up invoke_tool at module level.
    monkeypatch.setattr("hubspot_agent.handlers.invoke_tool", mock_invoke)

    result = hubspot_command(f"approve {action_id}", working_dir=str(tmp_path))
    # Soft failure surfaces a retryable server error, not a false success.
    assert "Approved and executed" not in result
    payload = json.loads(result)
    assert payload["error"]["kind"] == "server"
    assert payload["error"]["retryable"] is True
    # Preview still on disk (retryable); snapshot dropped (nothing changed).
    assert load_pending("123", action_id) is not None
    assert not (Path(snapshot_dir_for_portal("123")) / f"{action_id}.json").exists()
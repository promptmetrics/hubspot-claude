import json
from pathlib import Path

import httpx
import pytest

import hubspot_agent.agents  # noqa: F401 — populate tool registry
import hubspot_agent.blueprints.workflows as _registry
from hubspot_agent.agents.workflows import _build_workflows_preview, _execute_workflows, get_workflows_agent_prompt
from hubspot_agent.blueprints.workflows import get_blueprint, load_packaged_blueprints, register_blueprint, reload_blueprints
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig
from hubspot_agent.models import RiskLevel, TaskIntent
from hubspot_agent.tools import invoke_tool


@pytest.fixture(autouse=True)
def _restore_registry():
    """Promote mutates the process-global blueprint registry; restore it so
    later test files see shipped-only blueprints."""
    original = dict(_registry._BLUEPRINT_REGISTRY)
    yield
    _registry._BLUEPRINT_REGISTRY.clear()
    _registry._BLUEPRINT_REGISTRY.update(original)


def test_workflows_agent_prompt_has_correct_tools():
    prompt = get_workflows_agent_prompt()
    assert prompt.agent_name == "Workflows Agent"
    expected = [
        "hubspot_get_workflow",
        "hubspot_list_workflows",
        "hubspot_create_workflow",
        "hubspot_create_workflow_from_blueprint",
        "hubspot_update_workflow",
        "hubspot_enroll_workflow",
        "hubspot_toggle_workflow",
        "hubspot_extract_workflow_blueprint",
        "hubspot_parameterize_blueprint_draft",
        "hubspot_promote_blueprint_draft",
    ]
    assert sorted(prompt.tool_names) == sorted(expected)


@pytest.mark.asyncio
async def test_execute_update_does_get_then_put_with_revision(respx_mock):
    """V4 update must GET the current body/revisionId, merge edits, and PUT the whole."""
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    get_route = respx_mock.get("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "1",
                "revisionId": "r9",
                "name": "Old",
                "actions": [{"actionId": "a1"}],
            },
        )
    )
    put_route = respx_mock.put("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(200, json={"id": "1", "revisionId": "r10"})
    )

    intent = TaskIntent(
        intent_type="update",
        description="rename workflow",
        risk_level=RiskLevel.MEDIUM,
    )
    result = await _execute_workflows(
        agent_name="workflows",
        intent=intent,
        request_text="rename workflow 1 to Renamed",
        client=c,
        portal_id="123",
        proposed_payload={"workflow_id": "1", "updates": {"name": "Renamed"}},
    )

    assert result["status"] == "success"
    assert get_route.called
    assert put_route.called
    sent = json.loads(put_route.calls.last.request.content)
    assert sent["revisionId"] == "r9"  # pulled from the GET response
    assert sent["name"] == "Renamed"  # caller edit wins
    assert sent["actions"] == [{"actionId": "a1"}]  # untouched field survives merge
    assert "id" not in sent  # server-managed field stripped before PUT
    await c.close()


@pytest.mark.asyncio
async def test_execute_update_aborts_when_get_fails(respx_mock):
    """If the pre-update GET fails, do not issue a destructive PUT."""
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    put_route = respx_mock.put("https://api.hubapi.com/automation/v4/flows/1").mock(
        return_value=httpx.Response(200, json={"id": "1"})
    )

    intent = TaskIntent(
        intent_type="update",
        description="rename workflow",
        risk_level=RiskLevel.MEDIUM,
    )
    result = await _execute_workflows(
        agent_name="workflows",
        intent=intent,
        request_text="rename workflow 1",
        client=c,
        portal_id="123",
        proposed_payload={"workflow_id": "1", "updates": {"name": "Renamed"}},
    )

    assert result["status"] == "error"
    assert not put_route.called
    await c.close()


# ---------------------------------------------------------------------------
# HITL behavior change: the five workflow writes now gate (R6).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_tool_gates_workflow_create(env):
    """hubspot_create_workflow carries bare {"automation"} scope (no suffix),
    so it previously bypassed HITL. With WRITE_TOOLS it must route through
    apply_write and return a preview, not POST directly."""
    from hubspot_agent.handlers import handle_tool
    from hubspot_agent.persistence import load as _load_pending

    client = _FakeWorkflowClient()
    out = await handle_tool(
        client,
        None,
        _portal(),
        {"tool_name": "hubspot_create_workflow",
         "input": {"name": "X", "object_type": "contacts", "enrollment": {}, "actions": []}},
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["status"] == "preview"
    assert data["tool"] == "hubspot_create_workflow"
    assert data["action_id"]
    assert not client.posts  # the create did NOT happen (awaiting approval)
    pending = _load_pending("123", data["action_id"])
    assert pending is not None
    assert pending["tool_name"] == "hubspot_create_workflow"


@pytest.mark.asyncio
async def test_handle_tool_read_workflow_not_gated(env):
    """hubspot_get_workflow is a read: it invokes directly, no preview."""
    from hubspot_agent.handlers import handle_tool

    client = _FakeWorkflowClient()
    out = await handle_tool(
        client, None, _portal(),
        {"tool_name": "hubspot_get_workflow", "input": {"workflow_id": "42"}},
    )
    assert out["ok"] is True
    assert out["data"]["tool"] == "hubspot_get_workflow"
    assert client.gets and "automation/v4/flows/42" in client.gets[0]["url"]


# ---------------------------------------------------------------------------
# Learning-loop lifecycle: extract → parameterize → promote.
# ---------------------------------------------------------------------------

_FLAGGED_FLOW = {
    "id": "777", "name": "Flagged Emailer", "isEnabled": True,
    "objectTypeId": "0-1", "flowType": "CONTACT_FLOW", "type": "CONTACT_FLOW",
    "startActionId": "a1", "revisionId": "r1",
    "actions": [
        {"actionId": "a1", "actionTypeId": "0-4", "actionTypeVersion": 0,
         "type": "SINGLE_CONNECTION", "fields": {"content_id": "999"},
         "connection": {"actionId": None}},
    ],
    "enrollmentCriteria": {"type": "LIST_BASED", "listFilterBranch": {}},
}


def _portal(*, scopes=None):
    return PortalConfig(portal_id="123", token="test-token", tier="Professional", scopes_granted=scopes)


class _FakeWorkflowClient:
    """Fake warm client for the handler HITL tests (no real HTTP)."""

    def __init__(self):
        self.posts = []
        self.gets = []

    async def get(self, url, **kw):
        self.gets.append({"url": url, **kw})
        return _FakeResp({"id": "42"})

    async def post(self, url, **kw):
        self.posts.append({"url": url, **kw})
        return _FakeResp({"id": "new-1"})

    async def close(self):
        return None


class _FakeResp:
    def __init__(self, body):
        self.body = body


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    return tmp_path


def _mock_get_flow(respx_mock, flow_id, payload):
    respx_mock.get(f"https://api.hubapi.com/automation/v4/flows/{flow_id}").mock(
        return_value=httpx.Response(200, json=payload)
    )


@pytest.mark.asyncio
async def test_extract_writes_draft_logs_unknowns(respx_mock):
    _mock_get_flow(respx_mock, "777", _FLAGGED_FLOW)
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    out = await invoke_tool(
        "hubspot_extract_workflow_blueprint", "123", workflow_id="777", client=c, name="Flagged Emailer"
    )
    assert "error" not in out
    draft = Path(out["draft_path"])
    assert draft.is_file()
    data = json.loads(draft.read_text())
    assert data["name"] == "Flagged Emailer"
    assert data["source"]["origin"] == "extracted"
    assert data["source"]["portal_id"] == "123"
    assert data["source"]["workflow_id"] == "777"
    assert data["source"]["extracted_at"]
    assert any(f["kind"] == "content_id" and f["value"] == "999" for f in out["flags"])
    assert out["summary"]["object_type"] == "Contact-based"
    assert out["summary"]["n_actions"] == 1
    assert out["summary"]["enrollment_type"] == "LIST_BASED"
    await c.close()


@pytest.mark.asyncio
async def test_promote_refuses_on_unresolved_flags(respx_mock):
    _mock_get_flow(respx_mock, "777", _FLAGGED_FLOW)
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    await invoke_tool(
        "hubspot_extract_workflow_blueprint", "123", workflow_id="777", client=c, name="Flagged Emailer"
    )
    promoted = Path.home() / ".claude" / "hubspot" / "blueprints" / "flagged_emailer.json"
    draft = Path.home() / ".claude" / "hubspot" / "blueprints" / "drafts" / "flagged_emailer.json"
    out = await invoke_tool("hubspot_promote_blueprint_draft", "123", name="Flagged Emailer")
    assert "error" in out
    assert out.get("unresolved_flags")
    assert not promoted.exists()
    assert draft.is_file()  # draft retained
    await c.close()


@pytest.mark.asyncio
async def test_parameterize_then_promote_succeeds(respx_mock):
    _mock_get_flow(respx_mock, "777", _FLAGGED_FLOW)
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    await invoke_tool(
        "hubspot_extract_workflow_blueprint", "123", workflow_id="777", client=c, name="Flagged Emailer"
    )
    pout = await invoke_tool(
        "hubspot_parameterize_blueprint_draft", "123",
        name="Flagged Emailer",
        edits=[{"path": "spec.actions[0].fields.content_id", "param_name": "email_content_id"}],
    )
    assert "error" not in pout
    assert pout["remaining_flags"] == []
    draft_data = json.loads(Path(pout["draft_path"]).read_text())
    assert draft_data["spec"]["actions"][0]["fields"]["content_id"] == "{{param:email_content_id}}"
    assert "email_content_id" in draft_data["parameters"]
    assert draft_data["parameters"]["email_content_id"]["default"] == "999"

    out = await invoke_tool("hubspot_promote_blueprint_draft", "123", name="Flagged Emailer")
    assert "error" not in out
    assert out["origin"] == "user"
    promoted = Path(out["blueprint_path"])
    assert promoted.is_file()
    assert not Path(pout["draft_path"]).exists()  # draft moved
    bp = get_blueprint("Flagged Emailer")
    assert bp is not None and bp.origin == "user"
    await c.close()


@pytest.mark.asyncio
async def test_promote_overwrite_guard_and_force(respx_mock):
    _mock_get_flow(respx_mock, "777", _FLAGGED_FLOW)
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    await invoke_tool(
        "hubspot_extract_workflow_blueprint", "123", workflow_id="777", client=c, name="Flagged Emailer"
    )
    await invoke_tool(
        "hubspot_parameterize_blueprint_draft", "123", name="Flagged Emailer",
        edits=[{"path": "spec.actions[0].fields.content_id", "param_name": "email_content_id"}],
    )
    first = await invoke_tool("hubspot_promote_blueprint_draft", "123", name="Flagged Emailer")
    assert "error" not in first

    # Re-extract + parameterize to recreate the draft, then promote over the existing file.
    _mock_get_flow(respx_mock, "777", _FLAGGED_FLOW)
    await invoke_tool(
        "hubspot_extract_workflow_blueprint", "123", workflow_id="777", client=c, name="Flagged Emailer"
    )
    await invoke_tool(
        "hubspot_parameterize_blueprint_draft", "123", name="Flagged Emailer",
        edits=[{"path": "spec.actions[0].fields.content_id", "param_name": "email_content_id"}],
    )
    refused = await invoke_tool("hubspot_promote_blueprint_draft", "123", name="Flagged Emailer")
    assert "error" in refused and "already exists" in refused["error"]

    forced = await invoke_tool("hubspot_promote_blueprint_draft", "123", name="Flagged Emailer", force=True)
    assert "error" not in forced
    assert forced["origin"] == "user"
    await c.close()


@pytest.mark.asyncio
async def test_promote_shadows_shipped_name(respx_mock):
    _mock_get_flow(respx_mock, "777", _FLAGGED_FLOW)
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    await invoke_tool(
        "hubspot_extract_workflow_blueprint", "123", workflow_id="777", client=c, name="welcome_email"
    )
    await invoke_tool(
        "hubspot_parameterize_blueprint_draft", "123", name="welcome_email",
        edits=[{"path": "spec.actions[0].fields.content_id", "param_name": "email_content_id"}],
    )
    out = await invoke_tool("hubspot_promote_blueprint_draft", "123", name="welcome_email")
    assert "error" not in out
    assert out["shadowed_shipped"] is True
    assert get_blueprint("welcome_email").origin == "user"  # user overrides shipped
    await c.close()


# ---------------------------------------------------------------------------
# Preview create path: blueprint detection + proposed_payload carries blueprint_name.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preview_create_detects_blueprint_and_routes_execute(respx_mock):
    """Preview infers a blueprint from the request; execute routes to
    create_workflow_from_blueprint when proposed_payload carries blueprint_name."""
    intent = TaskIntent(
        intent_type="create", description="create a welcome_email workflow",
        risk_level=RiskLevel.MEDIUM,
    )
    preview = await _build_workflows_preview("workflows", intent, client=None, portal_id="123")
    assert preview.proposed_payload.get("blueprint_name") == "welcome_email"
    assert preview.preview["warnings"] == []  # shipped, no raw nodes, not cross-portal

    # Execute path: proposed_payload blueprint_name -> create_workflow_from_blueprint.
    respx_mock.post("https://api.hubapi.com/automation/v4/flows").mock(
        return_value=httpx.Response(200, json={"id": "new-flow"})
    )
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    result = await _execute_workflows(
        agent_name="workflows", intent=intent, request_text="create a welcome_email workflow",
        client=c, portal_id="123", proposed_payload=preview.proposed_payload,
    )
    assert result["status"] == "success"
    assert result["data"]["result"]["id"] == "new-flow"
    await c.close()


@pytest.mark.asyncio
async def test_preview_create_no_blueprint_falls_back_manual():
    intent = TaskIntent(
        intent_type="create", description="create a totally bespoke automation",
        risk_level=RiskLevel.MEDIUM,
    )
    preview = await _build_workflows_preview("workflows", intent, client=None, portal_id="123")
    assert "blueprint_name" not in preview.proposed_payload
    assert preview.proposed_payload["name"] == "create a totally bespoke automation"


# ---------------------------------------------------------------------------
# Fresh-process user-blueprint loading (regression for R9-worse).
# ---------------------------------------------------------------------------

def _write_user_blueprint(name: str, slug: str) -> Path:
    """Write a minimal, converter-safe user blueprint to the isolated home dir."""
    user_bp = {
        "format_version": 1, "name": name,
        "description": "set lead status (user blueprint)", "tags": [],
        "source": {"origin": "user"}, "notes": [], "flags": [], "parameters": {},
        "spec": {
            "ui_path": "Settings > Automation > Workflows > Create workflow",
            "object_type": "Contact-based",
            "enrollment": {
                "type": "LIST_BASED",
                "filter_branch": {
                    "filterBranches": [],
                    "filters": [
                        {"property": "lifecyclestage", "filterType": "PROPERTY",
                         "operation": {"operator": "IS_ANY_OF", "includeObjectsWithNoValueSet": False,
                                       "values": ["lead"], "operationType": "ENUMERATION"}},
                    ],
                    "filterBranchType": "AND", "filterBranchOperator": "AND",
                },
            },
            "actions": [
                {"ui_action": "Set property value",
                 "fields": {"Property": "hs_lead_status", "Value": "IN_PROGRESS"}},
            ],
            "prerequisites": [], "validation": [],
        },
    }
    user_dir = Path.home() / ".claude" / "hubspot" / "blueprints"
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{slug}.json"
    path.write_text(json.dumps(user_bp))
    return path


def _simulate_fresh_import() -> None:
    """A fresh process loads only packaged blueprints at import (by design, for
    test isolation). Reset the in-memory registry to that state so the create
    path must reload user blueprints from disk to find them."""
    _registry._BLUEPRINT_REGISTRY.clear()
    for bp in load_packaged_blueprints():
        register_blueprint(bp)


@pytest.mark.asyncio
async def test_create_reloads_user_blueprints_in_fresh_process(env, respx_mock):
    """Regression: a fresh process loads only packaged blueprints at import, so a
    user-promoted blueprint is absent from the registry until the tool layer
    reloads from disk. create_workflow_from_blueprint must reload and find it
    (else it returns 'Blueprint not found' even though the file is on disk)."""
    bp_name = "Fresh Process Lead Status"
    _write_user_blueprint(bp_name, "fresh_process_lead_status")

    _simulate_fresh_import()
    assert get_blueprint(bp_name) is None  # bug precondition: not in memory

    respx_mock.post("https://api.hubapi.com/automation/v4/flows").mock(
        return_value=httpx.Response(200, json={"id": "new-flow"})
    )
    c = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    out = await invoke_tool(
        "hubspot_create_workflow_from_blueprint", "123",
        blueprint_name=bp_name, client=c, params={},
    )
    assert "error" not in out, out
    assert out["id"] == "new-flow"
    await c.close()

    # Preview path reloads too: a request naming the user blueprint matches it
    # even when the in-memory registry was packaged-only at call time.
    _simulate_fresh_import()
    assert get_blueprint(bp_name) is None
    intent = TaskIntent(
        intent_type="create", description=f"create a {bp_name} workflow",
        risk_level=RiskLevel.MEDIUM,
    )
    preview = await _build_workflows_preview("workflows", intent, client=None, portal_id="123")
    assert preview.proposed_payload.get("blueprint_name") == bp_name

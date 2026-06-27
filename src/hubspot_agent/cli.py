from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path
from typing import Any

from hubspot_agent.app_credentials import load_app_credentials, save_app_credentials
from hubspot_agent.auth import exchange_code_for_token, get_authorization_url
from hubspot_agent.config import (
    CONFIG_DIR,
    PortalConfig,
    detect_default_portal,
    load_portal_config,
    save_portal_config,
)
from hubspot_agent.maintenance import _validate_portal_id
from hubspot_agent.agents import (
    get_agent_category,
    get_agent_emoji,
    get_agent_prompt,
    group_agents_by_category,
    list_agent_names,
)
from hubspot_agent.models import PreviewResult, RiskLevel, TaskIntent
from hubspot_agent.safety import apply_write as _apply_write
from hubspot_agent.scope_registry import get_required_scopes
from hubspot_agent.setup import REQUIRED_SCOPES
import asyncio

from hubspot_agent.models import BatchApprovalMode
from hubspot_agent.orchestrator import (
    check_dispatch_readiness,
    dispatch_agent,
    dispatch_agents_parallel,
    initialize_session,
    parse_batch_mode,
    route_request,
    run_loop,
    run_simple,
)
from hubspot_agent import loop_log, loop_state
from hubspot_agent.persistence import (
    clear as _clear_pending_preview,
    confirm as _confirm_pending_preview,
    list_pending as _list_pending_previews,
    load as _load_pending_preview,
)
from hubspot_agent.snapshot import (
    delete_undo_snapshot,
    load_undo_snapshot,
    snapshot_dir_for_portal,
)
from hubspot_agent.tools import invoke_tool, get_tool, list_tools
from hubspot_agent.trace import compute_status_aggregates, emit_trace, new_trace_id
from hubspot_agent import audit
from hubspot_agent.handlers import (
    ExecuteError,
    execute_pending_write,
    _WRITE_SCOPE_SUFFIXES,
    _is_write_tool,
    _tool_impact_count,
    _tool_intent_type,
    _tool_kwargs,
    _tool_risk_level,
)


def _run_async(async_fn, *args, **kwargs):
    """Run an async function from sync code, handling nested event loops."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_fn(*args, **kwargs))
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(lambda: asyncio.run(async_fn(*args, **kwargs))).result()


def _header(portal_id: str, tier: str = "unknown") -> str:
    return f"📍 Portal: {portal_id} ({tier})"


def _parse_flags(request: str) -> tuple[bool, str]:
    """Return (loop_flag_enabled, stripped_request)."""
    stripped = request.strip()
    if stripped.startswith("--loop "):
        return True, stripped[7:].strip()
    if stripped == "--loop":
        return True, ""
    return False, stripped


def hubspot_command(request: str, working_dir: str = ".", *, portal_id: str | None = None) -> str:
    loop_flag, request = _parse_flags(request)
    if not request:
        return "Usage: /hubspot [--loop] <request>"

    if request.lower().startswith("portal "):
        return _handle_portal_command(request[7:].strip(), working_dir)

    if request.lower() == "refresh":
        return _handle_refresh(working_dir)

    if request.lower() == "status":
        return _handle_status(working_dir)

    if request.lower().startswith("setup"):
        return _handle_setup(request[5:].strip(), working_dir)

    if request.lower().startswith("approve "):
        return _handle_approve(request[8:].strip(), working_dir)

    if request.lower() in ("y", "yes"):
        return _handle_approve_last(working_dir)

    if request.lower().startswith("reject "):
        return _handle_reject(request[7:].strip(), working_dir)

    if request.lower() in ("n", "no", "reject"):
        return _handle_reject_last(working_dir)

    if request.isdigit():
        return _handle_confirm(request, working_dir)

    if request.lower().startswith("confirm "):
        return _handle_confirm(request[8:].strip(), working_dir)

    if request.lower().startswith("undo"):
        subcommand = request[4:].strip()
        if subcommand.lower() == "list":
            return _handle_undo_list(working_dir)
        if subcommand:
            return _handle_undo(subcommand, working_dir)
        return "Usage: /hubspot undo <action_id> or /hubspot undo list"

    if request.lower() == "continue":
        return _handle_continue(working_dir)

    if request.lower() == "abandon":
        return _handle_abandon(working_dir)

    if request.lower().startswith("loop "):
        subcommand = request[5:].strip()
        if subcommand.lower() == "status":
            return _handle_loop_status(working_dir)
        if subcommand.lower() == "log":
            return _handle_loop_log(working_dir)
        if subcommand.lower() == "checkpoint":
            return _handle_loop_checkpoint(working_dir)
        if subcommand.lower() == "continue":
            return _handle_continue(working_dir)
        if subcommand.lower() == "abandon":
            return _handle_abandon(working_dir)
        return "Usage: /hubspot loop {status | log | checkpoint | continue | abandon}"

    if request.lower() == "route" or request.lower().startswith("route "):
        return _handle_route(request[6:].strip(), working_dir, portal_id)

    if request.lower() == "tool" or request.lower().startswith("tool "):
        return _handle_tool(request[5:].strip(), working_dir, portal_id)

    if request.lower() == "agents" or request.lower().startswith("agents "):
        return _handle_agents_list()

    if request.lower() == "tools" or request.lower().startswith("tools "):
        return _handle_tools_list()

    if request.lower() == "agent-prompt" or request.lower().startswith("agent-prompt "):
        return _handle_agent_prompt(request[13:].strip(), working_dir, portal_id)

    if portal_id is None:
        portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return (
            "No default portal found. Create a `.hubspot-portal` file in your working directory "
            "with your portal ID, or use `/hubspot portal switch <portal_id>`."
        )

    portal_config = load_portal_config(portal_id)
    if not portal_config:
        return (
            f"Portal {portal_id} found but no token configured. "
            f"Use `/hubspot portal auth {portal_id}` for OAuth, or "
            f"`/hubspot portal token {portal_id}` for a Private App token."
        )

    trace_id = new_trace_id()
    emit_trace(portal_id, "request_received", trace_id, {"request": request})

    _run_async(initialize_session, portal_id)

    batch_mode, cleaned_request = parse_batch_mode(request)
    agent_names = route_request(cleaned_request, portal_id=portal_id)
    if not agent_names:
        emit_trace(portal_id, "error", trace_id, {"error": "no matching agents", "request": request})
        return (
            f"{_header(portal_id, portal_config.tier)}\n\n"
            "I'm not sure which HubSpot domain this request belongs to. "
            "Could you rephrase or specify what you'd like to do (e.g., 'find contacts', 'create workflow')?"
        )

    # Use loop mode when explicitly requested or when multiple agents are involved.
    use_loop = loop_flag or len(agent_names) > 1
    if use_loop:
        emit_trace(portal_id, "route_decision", trace_id, {"agents": agent_names, "mode": "loop"})
        return _run_async(run_loop, cleaned_request, portal_config, working_dir, trace_id)

    emit_trace(portal_id, "route_decision", trace_id, {"agents": agent_names})

    readiness = _run_async(check_dispatch_readiness, agent_names, portal_config)
    if not readiness["ready"]:
        emit_trace(portal_id, "error", trace_id, {"error": readiness["decline_reason"]})
        return f"{_header(portal_id, portal_config.tier)}\n\n❌ {readiness['decline_reason']}"

    def _agent_label(name: str) -> str:
        return f"{get_agent_emoji(name)} {name}"

    routed_labels = [_agent_label(n) for n in agent_names]
    lines = [f"{_header(portal_id, portal_config.tier)}", f"**Routing to:** {', '.join(routed_labels)}", ""]

    if "associations" in agent_names and "objects" in agent_names:
        lines.append(
            "_This query spans multiple object types; results from each agent are shown below._"
        )
        lines.append("")

    results = _run_async(
        dispatch_agents_parallel,
        agent_names,
        cleaned_request,
        portal_config=portal_config,
        mode="preview",
        trace_id=trace_id,
        batch_mode=batch_mode,
    )
    for result in results:
        emoji = result.emoji or get_agent_emoji(result.agent_name)
        lines.append(f"### {emoji} {result.agent_name}")
        if result.status == "error":
            lines.append(f"❌ {result.error_message}")
        elif result.status == "preview":
            lines.append(f"⚠️  Preview (action: {result.data.get('action_id')})")
            risk = result.data.get("risk_level", "unknown")
            risk_badge = {"destructive": "🚨", "high": "⚠️", "medium": "⚠️", "low": ""}.get(risk, "")
            lines.append(f"{risk_badge} Risk: {risk}" if risk_badge else f"Risk: {risk}")
            lines.append(f"Impact: {result.data.get('impact_count', 'unknown')} records")
            preview_text = result.data.get("preview", "")
            if preview_text:
                lines.append(preview_text)
            sources = result.informing_sources or result.data.get("informing_sources", [])
            if sources:
                lines.append("")
                lines.append("**Sources:**")
                for src in sources:
                    tier = src.get("trust_tier", "unknown")
                    url = src.get("url", "")
                    title = src.get("title", url)
                    lines.append(f"- [{title}]({url}) — {tier}")
            lines.append("")
            lines.append("Approve with `y` or `approve <id>`, reject with `n`.")
        else:
            lines.append(result.data.get("message", ""))

    emit_trace(portal_id, "completion", trace_id, {"status": "preview_ready", "agents": agent_names, "batch_mode": batch_mode.value})
    return "\n".join(lines)


def _authenticate_portal_oauth(portal_id: str) -> dict[str, Any]:
    """Run OAuth authorization and return a structured result."""
    creds = load_app_credentials()
    if not creds:
        return {
            "success": False,
            "message": (
                "🔑 HubSpot app credentials needed.\n\n"
                "Save them with:\n"
                "```python\n"
                "from hubspot_agent.app_credentials import save_app_credentials\n"
                "save_app_credentials(client_id='your-client-id', client_secret='your-client-secret', app_id='your-app-id', region='us')  # use region='eu' for EU (app-eu1.hubspot.com) apps\n"
                "```\n\n"
                f"Then run: `/hubspot portal auth {portal_id}`"
            ),
        }

    try:
        url = get_authorization_url(portal_id, list(REQUIRED_SCOPES))
    except ValueError as exc:
        return {"success": False, "message": f"❌ {exc}"}

    lines = [
        f"🔐 OAuth Authorization for Portal {portal_id}",
        "",
        f"**Authorization URL:** {url}",
        "",
        "A browser window should open automatically. If not, copy the URL above.",
        "Waiting for callback on http://localhost:3000/oauth/callback ...",
    ]

    try:
        webbrowser.open(url)
    except Exception:
        pass

    return {
        "success": True,
        "message": (
            f"🔐 OAuth authorization started for portal {portal_id}.\n\n"
            f"**Authorization URL:** {url}\n\n"
            "A browser window should open automatically. If not, copy the URL above.\n"
            "After authorizing, exchange the code with:\n"
            "```python\n"
            f"from hubspot_agent.auth import exchange_code_for_token\n"
            f"await exchange_code_for_token('{portal_id}', '<paste-code-here>', '<paste-state-here>')\n"
            "```"
        ),
    }


def _handle_portal_auth(portal_id: str) -> str:
    return _authenticate_portal_oauth(portal_id)["message"]


def _handle_setup(args: str, working_dir: str) -> str:
    from hubspot_agent.setup import run_setup

    parts = args.split(maxsplit=2)
    if not parts:
        return "Usage: /hubspot setup <portal_id> [oauth | token <pat>]"

    portal_id = parts[0]
    try:
        _validate_portal_id(portal_id)
    except ValueError:
        return f"❌ Invalid portal ID: {portal_id}"

    method = parts[1].lower() if len(parts) > 1 else None
    token = parts[2] if len(parts) > 2 else None

    portal_file = Path(working_dir) / ".hubspot-portal"
    portal_file.write_text(f"{portal_id}\n")

    if method == "oauth":
        auth_result = _authenticate_portal_oauth(portal_id)
        if not auth_result["success"]:
            return auth_result["message"]
        try:
            result = _run_async(run_setup, portal_id)
        except Exception as exc:
            return f"❌ Setup failed: {exc}"
        return f"{auth_result['message']}\n\n{result['message']}"

    if method == "token" or method == "private_app":
        if not token:
            return f"Usage: /hubspot setup {portal_id} token <private-app-token>"
        save_portal_config(
            PortalConfig(portal_id=portal_id, token=token, auth_type="private_app")
        )

    try:
        result = _run_async(run_setup, portal_id)
    except Exception as exc:
        return f"❌ Setup failed: {exc}"
    return result["message"]


def _handle_portal_command(subcommand: str, working_dir: str) -> str:
    parts = subcommand.split(maxsplit=1)
    if not parts:
        return "Usage: /hubspot portal {auth <id> | token <id> | switch <id> | list}"

    action = parts[0].lower()

    if action == "auth":
        if len(parts) < 2:
            return "Usage: /hubspot portal auth <portal_id>"
        return _handle_portal_auth(parts[1].strip())

    if action == "token":
        if len(parts) < 2:
            return "Usage: /hubspot portal token <portal_id>"
        return _handle_portal_token(parts[1].strip())

    if action == "switch":
        if len(parts) < 2:
            return "Usage: /hubspot portal switch <portal_id>"
        return _handle_portal_switch(parts[1].strip(), working_dir)

    if action == "list":
        return _handle_portal_list()

    return f"Unknown portal command: {action}"


def _handle_portal_token(portal_id: str) -> str:
    return (
        f"🔑 Private App Token for Portal {portal_id}\n\n"
        "Save your token with:\n"
        "```python\n"
        "from hubspot_agent.config import PortalConfig, save_portal_config\n"
        f"save_portal_config(PortalConfig(portal_id='{portal_id}', token='pat-na1-...', auth_type='private_app'))\n"
        "```\n\n"
        "Or set the environment variable:\n"
        f"`export HUBSPOT_TOKEN_{portal_id}=pat-na1-...`"
    )


def _handle_portal_switch(portal_id: str, working_dir: str) -> str:
    portal_file = Path(working_dir) / ".hubspot-portal"
    portal_file.write_text(f"{portal_id}\n")

    config = load_portal_config(portal_id)
    if not config:
        return (
            f"Switched to portal {portal_id}, but no token is configured.\n"
            f"Use `/hubspot portal auth {portal_id}` for OAuth, or "
            f"`/hubspot portal token {portal_id}` for a Private App token."
        )

    return f"✅ Switched to portal {portal_id} ({config.tier})."


def _handle_portal_list() -> str:
    if not CONFIG_DIR.exists():
        return "No portals configured yet."

    entries: list[dict[str, Any]] = []
    for path in sorted(CONFIG_DIR.iterdir()):
        if path.suffix == ".json" and not path.name.startswith("app_credentials"):
            try:
                data = json.loads(path.read_text())
                entries.append({
                    "portal_id": data.get("portal_id", path.stem),
                    "auth_type": data.get("auth_type", "private_app"),
                    "tier": data.get("tier", "unknown"),
                    "expires_at": data.get("expires_at"),
                })
            except json.JSONDecodeError:
                continue
        elif path.suffix == ".token":
            entries.append({
                "portal_id": path.stem,
                "auth_type": "private_app",
                "tier": "unknown",
                "expires_at": None,
            })

    if not entries:
        return "No portals configured yet."

    lines = ["**Configured Portals**", ""]
    lines.append("| Portal ID | Auth Type | Tier | Expires |")
    lines.append("|-----------|-----------|------|---------|")
    for e in entries:
        expires = "N/A" if e["auth_type"] == "private_app" else _format_expiry(e.get("expires_at"))
        lines.append(f"| {e['portal_id']} | {e['auth_type']} | {e['tier']} | {expires} |")

    return "\n".join(lines)


def _format_expiry(expires_at: float | None) -> str:
    if not expires_at:
        return "unknown"
    import time
    remaining = int(expires_at - time.time())
    if remaining < 0:
        return "expired"
    hours = remaining // 3600
    return f"{hours}h"


def _handle_status(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found. Create a `.hubspot-portal` file to use status."

    portal_config = load_portal_config(portal_id)
    if not portal_config:
        return f"Portal {portal_id} has no token configured."

    from hubspot_agent.dispatch import list_execute_agents, list_preview_agents, list_reconcile_agents
    from hubspot_agent.persistence import list_pending

    agg = compute_status_aggregates(portal_id, window_hours=24)
    pending = list_pending(portal_id)
    preview_agents = list_preview_agents()
    execute_agents = list_execute_agents()
    reconcile_agents = list_reconcile_agents()

    lines = [
        f"📍 Portal: {portal_id} ({portal_config.tier})",
        "",
        "**Agents by Category**",
    ]

    def _category_block(title: str, agents: list[str]) -> list[str]:
        if not agents:
            return []
        groups = group_agents_by_category(agents)
        block: list[str] = [f"### {title}"]
        for category, names in groups.items():
            emoji = get_agent_emoji(names[0])
            block.append(f"- {emoji} **{category}**: {', '.join(names)}")
        return block

    lines.extend(_category_block("Preview ready", preview_agents))
    lines.extend(_category_block("Execute ready", execute_agents))
    lines.extend(_category_block("Reconcile ready", reconcile_agents))

    lines.extend([
        "",
        "**Pending approvals**",
        f"- {len(pending)} preview(s) awaiting approval",
        "",
        "**Last 24 Hours**",
        f"- Requests: {agg['total_requests']}",
        f"- Avg latency: {agg['avg_latency_ms']} ms",
        f"- Error rate: {agg['error_rate'] * 100:.1f}%",
        f"- Est. cost: ${agg['total_estimated_usd']:.4f}",
    ])
    if agg["tool_call_counts"]:
        lines.append("- Tool calls:")
        for tool_name, count in agg["tool_call_counts"].items():
            lines.append(f"  - {tool_name}: {count}")
    return "\n".join(lines)


def _handle_refresh(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found to refresh."

    _run_async(initialize_session, portal_id)
    return f"✅ Cache refreshed and schemas re-warmed for portal {portal_id}."


def _snapshot_dir_for_portal(portal_id: str) -> str:
    return snapshot_dir_for_portal(portal_id)


def _is_destructive_preview(preview_data: dict[str, Any]) -> bool:
    preview = preview_data.get("preview") or {}
    intent = preview_data.get("intent") or {}
    risk = preview.get("risk_level") or intent.get("risk_level")
    return risk == RiskLevel.DESTRUCTIVE.value


def _present_destructive_preview(action_id: str, impact_count: int) -> str:
    return (
        f"🚨 This action is destructive and will affect **{impact_count}** records.\n\n"
        f"To confirm, type one of:\n"
        f"- `approve {action_id} {impact_count}`\n"
        f"- `{impact_count}`\n"
        f"- `confirm {impact_count}`"
    )


def _error_json(
    kind: str, message: str, *, retryable: bool = False, retry_after=None, guidance: str | None = None
) -> str:
    """NFR-15 stable error contract: ``{"error":{kind,message,retryable,retry_after?,guidance?}}``."""
    error: dict[str, Any] = {"kind": kind, "message": message, "retryable": retryable}
    if retry_after is not None:
        error["retry_after"] = retry_after
    if guidance is not None:
        error["guidance"] = guidance
    return json.dumps({"error": error}, indent=2)


def _handle_approve(action_id: str, working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    portal_config = load_portal_config(portal_id)
    if not portal_config:
        return f"Portal {portal_id} has no token configured."

    # Accept "approve <id> <count>" as well as a bare action id.
    confirm_count: int | None = None
    parts = action_id.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        confirm_count = int(parts[-1])
        action_id = parts[0]

    # The full approve→execute contract (FR-19 gate, FR-17/18 undo, FR-17 audit,
    # retryable-on-failure) lives in execute_pending_write, shared with the
    # daemon handler.  client=None → the core builds a fresh HubSpotClient for
    # the tool branch; the agent branch builds its own inside dispatch_agent.
    try:
        result = _run_async(
            execute_pending_write, portal_config, action_id, confirm_count=confirm_count
        )
    except ExecuteError as exc:
        return _error_json(exc.kind, exc.message, retryable=exc.retryable, guidance=exc.guidance)
    except Exception as exc:
        # Any unexpected failure (async loop teardown, import error, etc.)
        # surfaces as structured error JSON, never a traceback.
        return _error_json("server", str(exc), retryable=True)

    # Surface a human-readable message: the agent branch carries its own
    # "message"; the tool branch stringifies the raw outcome as JSON.
    payload = result.data.get("data", {})
    message = payload.get("message") if isinstance(payload, dict) else None
    if not message:
        message = json.dumps(payload, default=str) if payload else ""
    if result.audit_failed:
        message += "\n⚠️ Audit log write failed — see stderr; the HubSpot write succeeded."
    return f"✅ Approved and executed action {action_id}.\n\n{message}"


def _handle_approve_last(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    files = _list_pending_previews(portal_id)
    if not files:
        return "No pending previews to approve."

    action_id = files[0].stem
    preview_data = _load_pending_preview(portal_id, action_id)
    if preview_data and _is_destructive_preview(preview_data):
        required = preview_data.get("required_confirmation", 0)
        return _present_destructive_preview(action_id, required)

    return _handle_approve(action_id, working_dir)


def _handle_confirm(count_str: str, working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    files = _list_pending_previews(portal_id)
    if not files:
        return "No pending previews to confirm."

    if not count_str.isdigit():
        return f"Invalid confirmation count: {count_str}"

    action_id = files[0].stem
    count = int(count_str)
    preview_data = _load_pending_preview(portal_id, action_id)
    if preview_data and _is_destructive_preview(preview_data):
        if not _confirm_pending_preview(portal_id, action_id, count):
            required = preview_data.get("required_confirmation", 0)
            return _present_destructive_preview(action_id, required)

    return _handle_approve(action_id, working_dir)


async def _undo_action(snapshot: dict[str, Any], portal_id: str, portal_config) -> str:
    from hubspot_agent.client import HubSpotClient

    metadata = snapshot.get("metadata", {})
    intent_type = metadata.get("intent_type")
    object_type = metadata.get("target_object")

    if intent_type == "delete":
        return "❌ Deletes are not undoable through HubSpot."

    if not metadata.get("undoable", False):
        return "❌ This action is not undoable."

    client = HubSpotClient(portal_config)
    try:
        if intent_type == "update":
            original_values = snapshot.get("original_values", {})
            if not original_values:
                return "❌ No original values recorded; cannot undo update."
            for object_id, properties in original_values.items():
                await invoke_tool(
                    "hubspot_update_object",
                    portal_id,
                    object_id=str(object_id),
                    object_type=str(object_type),
                    properties=properties,
                    client=client,
                )
            return f"✅ Restored {len(original_values)} {object_type or 'record(s)'} to their original values."

        if intent_type == "create":
            created_ids = metadata.get("created_ids", [])
            if not created_ids:
                return "❌ No created IDs recorded; cannot undo create."
            for object_id in created_ids:
                await invoke_tool(
                    "hubspot_delete_object",
                    portal_id,
                    object_id=str(object_id),
                    object_type=str(object_type),
                    client=client,
                )
            return f"✅ Deleted {len(created_ids)} created {object_type or 'record(s)'} to undo the create."

        return "❌ Unknown action type; cannot undo."
    finally:
        await client.close()


def _handle_undo(action_id: str, working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    portal_config = load_portal_config(portal_id)
    if not portal_config:
        return f"Portal {portal_id} has no token configured."

    snapshot = load_undo_snapshot(_snapshot_dir_for_portal(portal_id), action_id)
    if not snapshot:
        return f"No undo snapshot found for action {action_id}."

    result = _run_async(_undo_action, snapshot, portal_id, portal_config)
    delete_undo_snapshot(_snapshot_dir_for_portal(portal_id), action_id)

    audit.log_write(
        portal_id=portal_id,
        action=f"undo:{action_id}",
        agent=snapshot.get("metadata", {}).get("intent_type", "unknown"),
        result_summary={"message": result},
    )

    return result


def _handle_undo_list(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    snapshot_dir = Path(_snapshot_dir_for_portal(portal_id))
    if not snapshot_dir.exists():
        return "No undo snapshots available."

    files = sorted(snapshot_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "No undo snapshots available."

    lines = ["**Undoable actions**", ""]
    for file_path in files:
        try:
            snapshot = json.loads(file_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        metadata = snapshot.get("metadata", {})
        action_id = snapshot.get("action_id", file_path.stem)
        intent_type = metadata.get("intent_type", "unknown")
        target = metadata.get("target_object", "unknown")
        undoable = metadata.get("undoable", False)
        lines.append(
            f"- `{action_id}` — {intent_type} on {target} "
            f"({'undoable' if undoable else 'not undoable'})"
        )

    return "\n".join(lines)


def _handle_reject(action_id: str, working_dir: str) -> str:
    """``hubspot reject <id>`` — clear one pending preview by ID (FR-19/§7 step 4)."""
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."
    action_id = action_id.split()[0] if action_id else ""
    if not action_id:
        return _handle_reject_last(working_dir)
    preview_data = _load_pending_preview(portal_id, action_id)
    if not preview_data:
        return f"No pending preview found with ID {action_id}."
    _clear_pending_preview(portal_id, action_id)
    agent = preview_data.get("agent_name") or preview_data.get("tool_name") or "action"
    return f"❌ Rejected preview {action_id} for {agent}."


def _handle_reject_last(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    files = _list_pending_previews(portal_id)
    if not files:
        return "No pending previews to reject."

    action_id = files[0].stem
    preview_data = _load_pending_preview(portal_id, action_id)
    _clear_pending_preview(portal_id, action_id)

    if preview_data:
        return f"❌ Rejected preview {action_id} for {preview_data['agent_name']}."

    return "No pending previews to reject."


def _handle_continue(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    portal_config = load_portal_config(portal_id)
    if not portal_config:
        return f"Portal {portal_id} has no token configured."

    state = loop_state.load(portal_id)
    if state is None:
        return "No active loop to continue."
    if loop_state.is_stale(state):
        loop_state.clear(portal_id)
        return "The previous loop has expired. Start a new request."

    trace_id = state.trace_id
    return _run_async(run_loop, state.request_text, portal_config, working_dir, trace_id)


def _handle_abandon(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    state = loop_state.load(portal_id)
    if state is None:
        return "No active loop to abandon."

    loop_log.log_event(portal_id, state.trace_id, "loop_abandoned", {
        "current_step": state.current_step,
        "status": state.status,
    })
    loop_state.clear(portal_id)
    return f"✅ Abandoned active loop for portal {portal_id}."


def _handle_loop_status(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    state = loop_state.load(portal_id)
    if state is None:
        return "No active loop for this portal."

    lines = [
        f"**Loop status for portal {portal_id}**",
        f"- Goal: {state.plan.goal}",
        f"- Status: {state.status}",
        f"- Step: {state.current_step + 1} of {len(state.plan.steps)}",
        f"- Iterations: {state.iterations}",
    ]
    if state.last_error:
        lines.append(f"- Last error: {state.last_error}")
    return "\n".join(lines)


def _handle_loop_log(working_dir: str, limit: int = 20) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    state = loop_state.load(portal_id)
    trace_id = state.trace_id if state else None
    events = loop_log.get_recent(portal_id, trace_id=trace_id, limit=limit)
    if not events:
        return "No loop log entries for this portal."

    lines = [f"**Recent loop log for portal {portal_id}**", ""]
    for event in reversed(events):
        lines.append(
            f"- `{event.get('timestamp')}` {event.get('event_type')}: "
            f"{event.get('payload', {})}"
        )
    return "\n".join(lines)


def _handle_loop_checkpoint(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    state = loop_state.load(portal_id)
    if state is None:
        return "No active loop to checkpoint."

    loop_log.log_event(portal_id, state.trace_id, "loop_checkpoint", {
        "current_step": state.current_step,
        "status": state.status,
        "iterations": state.iterations,
    })
    loop_state.save(state)
    return f"✅ Checkpointed loop for portal {portal_id} at step {state.current_step + 1} of {len(state.plan.steps)}."


def _handle_route(request_text: str, working_dir: str, portal_id: str | None) -> str:
    """Route a request to agent(s) and emit a frozen-shape JSON ``{agents, rationale}``.

    Wraps ``route_request`` (keyword routing).  Portal resolution is best-effort:
    routing works without a portal, but a known portal enables custom-object
    fast-path detection inside ``route_request``.
    """
    if not request_text:
        return json.dumps(
            {"agents": [], "rationale": "empty request; no agents routed"}, indent=2
        )
    if portal_id is None:
        portal_id = detect_default_portal(working_dir)
    agents = route_request(request_text, portal_id=portal_id)
    if not agents:
        rationale = "no keyword match; no agents routed"
    elif len(agents) == 1:
        rationale = f"keyword routing selected agent: {agents[0]}"
    else:
        rationale = (
            f"keyword routing selected {len(agents)} agents in dependency order: "
            f"{', '.join(agents)}"
        )
    return json.dumps({"agents": agents, "rationale": rationale}, indent=2)


# ---------------------------------------------------------------------------
# hubspot tool <name> [--input <json>|-]  (T6)
# ---------------------------------------------------------------------------


def _split_input_flag(args: str) -> tuple[str, str]:
    """Split ``<name> [--input <json>|-]`` into (name, raw_input)."""
    marker = " --input "
    idx = args.find(marker)
    if idx != -1:
        return args[:idx], args[idx + len(marker):]
    marker = " --input="
    idx = args.find(marker)
    if idx != -1:
        return args[:idx], args[idx + len(marker):]
    return args, ""


def _parse_tool_args(args: str) -> tuple[str, dict[str, Any]]:
    if not args:
        raise ValueError("tool name required")
    name, raw = _split_input_flag(args)
    name = name.strip()
    if not name:
        raise ValueError("tool name required")
    if not raw:
        return name, {}
    if raw.strip() == "-":
        raw = sys.stdin.read()
    raw = raw.strip()
    if not raw:
        return name, {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid --input JSON ({exc.msg})") from exc
    if not isinstance(payload, dict):
        raise ValueError("--input must be a JSON object")
    return name, payload


def _tool_scope_error(tool_name: str, missing: list[str]) -> str:
    lines = [f"Missing HubSpot OAuth scopes for tool {tool_name}:"]
    for scope in missing:
        lines.append(f"- {scope}")
    return "\n".join(lines)


async def _capture_original_values(
    tool_name: str, tool_input: dict[str, Any], client, portal_id: str
) -> dict[str, Any]:
    """Best-effort fetch of current state for update/delete so undo can restore it."""
    if tool_name not in ("hubspot_update_object", "hubspot_delete_object"):
        return {}
    object_id = tool_input.get("object_id")
    object_type = tool_input.get("object_type")
    if not object_id or not object_type:
        return {}
    try:
        result = await invoke_tool(
            "hubspot_get_object",
            portal_id,
            object_id=str(object_id),
            object_type=str(object_type),
            client=client,
        )
    except Exception:
        return {}
    if not isinstance(result, dict) or result.get("error") or "id" not in result:
        return {}
    return {str(result["id"]): result.get("properties", {})}


async def _build_tool_preview(
    tool_name: str,
    tool_input: dict[str, Any],
    required_scopes: set[str],
    client,
    portal_id: str,
) -> PreviewResult:
    risk = _tool_risk_level(required_scopes)
    original_values = await _capture_original_values(tool_name, tool_input, client, portal_id)
    return PreviewResult(
        preview={"tool": tool_name, "input": tool_input, "message": f"Preview of {tool_name}"},
        impact_count=_tool_impact_count(tool_name, tool_input),
        risk_level=risk,
        original_values=original_values,
        informing_sources=[],
    )


async def _tool_read(tool_name, portal_id, portal_config, tool_input):
    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.cache import ensure_custom_schema_cached

    await ensure_custom_schema_cached(portal_config, tool_input.get("object_type") if isinstance(tool_input, dict) else None)
    client = HubSpotClient(portal_config)
    try:
        result = await invoke_tool(tool_name, portal_id, client=client, **_tool_kwargs(tool_input))
        return json.dumps(result, indent=2, default=str)
    finally:
        await client.close()


async def _tool_write(tool_name, portal_id, portal_config, tool_input, required_scopes):
    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.cache import ensure_custom_schema_cached

    await ensure_custom_schema_cached(portal_config, tool_input.get("object_type") if isinstance(tool_input, dict) else None)
    risk = _tool_risk_level(required_scopes)
    intent = TaskIntent(
        intent_type=_tool_intent_type(tool_name),
        target_object=tool_input.get("object_type") if isinstance(tool_input, dict) else None,
        description=f"tool {tool_name}",
        risk_level=risk,
    )
    client = HubSpotClient(portal_config)
    try:
        aw = await _apply_write(
            client=client,
            portal_config=portal_config,
            preview_builder=lambda c: _build_tool_preview(
                tool_name, tool_input, required_scopes, c, portal_id
            ),
            agent_name=None,
            tool_name=tool_name,
            intent=intent,
            request_text=f"tool {tool_name}",
            proposed_payload=tool_input,
        )
        return json.dumps(
            {
                "status": "preview",
                "tool": tool_name,
                "action_id": aw.action_id,
                "preview": aw.preview.preview,
                "risk_level": aw.preview.risk_level.value,
                "impact_count": aw.preview.impact_count,
                "original_values": aw.preview.original_values,
                "required_confirmation": aw.preview.impact_count,
            },
            indent=2,
            default=str,
        )
    finally:
        await client.close()


def _handle_tool(args: str, working_dir: str, portal_id: str | None) -> str:
    """``hubspot tool <name> [--input <json>|-]`` — direct tool dispatch.

    Reads run through ``invoke_tool`` and return JSON.  Writes route through
    ``safety.apply_write`` with a tool-level preview builder (no agent/runtime
    fabrication, FR-5b); scope is resolved via ``scope_registry.get_required_scopes``.
    """
    try:
        tool_name, tool_input = _parse_tool_args(args)
    except ValueError as exc:
        return f"Usage: /hubspot tool <name> [--input <json>|-]\n  error: {exc}"

    if get_tool(tool_name) is None:
        known = ", ".join(sorted(t.name for t in list_tools()))
        return f"Unknown tool: {tool_name}. Known tools: {known}"

    if portal_id is None:
        portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return (
            "No default portal found. Create a `.hubspot-portal` file in your working directory "
            "with your portal ID, or use `--portal <portal_id>`."
        )
    portal_config = load_portal_config(portal_id)
    if not portal_config:
        return (
            f"Portal {portal_id} found but no token configured. "
            f"Use `/hubspot portal auth {portal_id}` or `/hubspot portal token {portal_id}`."
        )

    target_object = tool_input.get("object_type") if isinstance(tool_input, dict) else None
    required = get_required_scopes([tool_name], target_object=target_object)

    if portal_config.scopes_granted:
        missing = sorted(required - set(portal_config.scopes_granted))
        if missing:
            return _tool_scope_error(tool_name, missing)

    if _is_write_tool(required):
        return _run_async(_tool_write, tool_name, portal_id, portal_config, tool_input, required)
    return _run_async(_tool_read, tool_name, portal_id, portal_config, tool_input)


# ---------------------------------------------------------------------------
# hubspot agents list / tools list / agent-prompt <name>  (T7)
# ---------------------------------------------------------------------------


def _handle_agents_list() -> str:
    """Enumerate the agent registry as JSON ``{count, agents:[{name,category,emoji}]}``."""
    entries = [
        {"name": name, "category": get_agent_category(name), "emoji": get_agent_emoji(name)}
        for name in sorted(list_agent_names())
    ]
    return json.dumps({"count": len(entries), "agents": entries}, indent=2)


def _handle_tools_list() -> str:
    """Enumerate the tool registry as JSON ``{count, tools:[{name,description,async}]}``."""
    entries = [
        {"name": t.name, "description": t.description, "async": t.is_async}
        for t in sorted(list_tools(), key=lambda x: x.name)
    ]
    return json.dumps({"count": len(entries), "tools": entries}, indent=2)


def _handle_agent_prompt(name: str, working_dir: str, portal_id: str | None) -> str:
    """Emit the system prompt + tool set for one agent (catalog introspection)."""
    if not name:
        return "Usage: /hubspot agent-prompt <name>"
    portal_config = None
    if portal_id is None:
        portal_id = detect_default_portal(working_dir)
    if portal_id:
        portal_config = load_portal_config(portal_id)
    prompt = get_agent_prompt(name, portal_config)
    if prompt is None:
        known = ", ".join(sorted(list_agent_names()))
        return f"Unknown agent: {name}. Known agents: {known}"
    return json.dumps(
        {
            "name": name,
            "agent_name": prompt.agent_name,
            "domain_description": prompt.domain_description,
            "tool_names": prompt.tool_names,
            "system_prompt": prompt.system_prompt,
        },
        indent=2,
    )


def _strip_global_flags(argv: list[str]) -> tuple[list[str], str | None, str | None]:
    """Remove top-level --working-dir / --portal flags from argv.

    Only standalone argv tokens (or ``--flag=value`` forms) are matched, so a
    flag-like substring inside a quoted ``--input`` JSON value is never touched.
    Returns ``(remaining_tokens, working_dir, portal_id)``.
    """
    remaining: list[str] = []
    working_dir: str | None = None
    portal_id: str | None = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--working-dir" and i + 1 < len(argv):
            working_dir = argv[i + 1]
            i += 2
            continue
        if tok.startswith("--working-dir="):
            working_dir = tok[len("--working-dir=") :]
            i += 1
            continue
        if tok == "--portal" and i + 1 < len(argv):
            portal_id = argv[i + 1]
            i += 2
            continue
        if tok.startswith("--portal="):
            portal_id = tok[len("--portal=") :]
            i += 1
            continue
        remaining.append(tok)
        i += 1
    return remaining, working_dir, portal_id


def main() -> None:
    """Console-script entrypoint: ``hubspot <request> [--working-dir <dir>] [--portal <id>]``."""
    import sys

    remaining, working_dir, portal_id = _strip_global_flags(list(sys.argv[1:]))
    if working_dir is None:
        working_dir = "."
    if portal_id is not None:
        try:
            _validate_portal_id(portal_id)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(2)
    request = " ".join(remaining)
    print(hubspot_command(request, working_dir, portal_id=portal_id))



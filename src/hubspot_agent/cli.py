from __future__ import annotations

import json
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
from hubspot_agent.models import AgentResult
from hubspot_agent.setup import REQUIRED_SCOPES
import asyncio

from hubspot_agent.models import BatchApprovalMode
from hubspot_agent.orchestrator import (
    _clear_pending_preview,
    _load_pending_preview,
    _list_pending_previews,
    check_dispatch_readiness,
    dispatch_agent,
    dispatch_agents_parallel,
    initialize_session,
    parse_batch_mode,
    route_request,
)
from hubspot_agent.trace import compute_status_aggregates, emit_trace, new_trace_id


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


def hubspot_command(request: str, working_dir: str = ".") -> str:
    request = request.strip()
    if not request:
        return "Usage: /hubspot <request>"

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

    if request.lower() in ("n", "no", "reject"):
        return _handle_reject_last(working_dir)

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

    emit_trace(portal_id, "route_decision", trace_id, {"agents": agent_names})

    readiness = _run_async(check_dispatch_readiness, agent_names, portal_config)
    if not readiness["ready"]:
        emit_trace(portal_id, "error", trace_id, {"error": readiness["decline_reason"]})
        return f"{_header(portal_id, portal_config.tier)}\n\n❌ {readiness['decline_reason']}"

    lines = [f"{_header(portal_id, portal_config.tier)}", f"**Routing to:** {', '.join(agent_names)}", ""]

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
        lines.append(f"### {result.agent_name}")
        if result.status == "error":
            lines.append(f"❌ {result.error_message}")
        elif result.status == "preview":
            lines.append(f"⚠️  Preview (action: {result.data.get('action_id')})")
            lines.append(f"Risk: {result.data.get('risk_level', 'unknown')}")
            lines.append(f"Impact: {result.data.get('impact_count', 'unknown')} records")
            preview_text = result.data.get("preview", "")
            if preview_text:
                lines.append(preview_text)
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
                "save_app_credentials(client_id='your-client-id', client_secret='your-client-secret', app_id='your-app-id')\n"
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

    agg = compute_status_aggregates(portal_id, window_hours=24)
    lines = [
        f"📍 Portal: {portal_id} ({portal_config.tier})",
        "",
        "**Last 24 Hours**",
        f"- Requests: {agg['total_requests']}",
        f"- Avg latency: {agg['avg_latency_ms']} ms",
        f"- Error rate: {agg['error_rate'] * 100:.1f}%",
        f"- Est. cost: ${agg['total_estimated_usd']:.4f}",
    ]
    if agg["tool_call_counts"]:
        lines.append("- Tool calls:")
        for tool_name, count in agg["tool_call_counts"].items():
            lines.append(f"  - {tool_name}: {count}")
    return "\n".join(lines)


def _handle_refresh(working_dir: str) -> str:
    from hubspot_agent.cache import SchemaCache

    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found to refresh."

    cache = SchemaCache(portal_id)
    cache.refresh_all()
    return f"Cache refreshed for portal {portal_id}."


def _handle_approve(action_id: str, working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    portal_config = load_portal_config(portal_id)
    if not portal_config:
        return f"Portal {portal_id} has no token configured."

    preview_data = _load_pending_preview(portal_id, action_id)
    if not preview_data:
        return f"No pending preview found with ID {action_id}."

    result = _run_async(
        dispatch_agent,
        preview_data["agent_name"],
        preview_data["request_text"],
        portal_config=portal_config,
        mode="execute",
        trace_id=preview_data.get("trace_id"),
        batch_mode=BatchApprovalMode(preview_data.get("batch_mode", "single")),
        proposed_payload=preview_data.get("proposed_payload"),
    )

    _clear_pending_preview(portal_id, action_id)

    if result.status == "error":
        return f"❌ Execution failed: {result.error_message}"

    return f"✅ Approved and executed action {action_id}.\n\n{result.data.get('message', '')}"


def _handle_approve_last(working_dir: str) -> str:
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found."

    files = _list_pending_previews(portal_id)
    if not files:
        return "No pending previews to approve."

    action_id = files[0].stem
    return _handle_approve(action_id, working_dir)


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



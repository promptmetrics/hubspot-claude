from __future__ import annotations

from typing import Any

from hubspot_agent.config import detect_default_portal, load_portal_config
from hubspot_agent.models import AgentResult
from hubspot_agent.orchestrator import dispatch_agent, route_request, run_loop


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


def hubspot_command(request: str, working_dir: str = ".") -> str:
    loop_flag, request = _parse_flags(request)
    if not request:
        return "Usage: /hubspot [--loop] <request>"

    # Portal management commands
    if request.lower().startswith("portal "):
        return _handle_portal_command(request[7:].strip(), working_dir)

    if request.lower() == "refresh":
        return _handle_refresh(working_dir)

    # Default: route to orchestrator
    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return (
            "No default portal found. Create a `.hubspot-portal` file in your working directory "
            "with your portal ID, or use `/hubspot portal switch <portal_id>`."
        )

    portal_config = load_portal_config(portal_id)
    if not portal_config:
        return f"Portal {portal_id} found but no token configured. Set HUBSPOT_TOKEN_{portal_id} or save a token file."

    agent_names = route_request(request)
    if not agent_names:
        return (
            f"{_header(portal_id, portal_config.tier)}\n\n"
            "I'm not sure which HubSpot domain this request belongs to. "
            "Could you rephrase or specify what you'd like to do (e.g., 'find contacts', 'create workflow')?"
        )

    # Use loop mode when explicitly requested or when multiple agents are involved.
    use_loop = loop_flag or len(agent_names) > 1
    if use_loop:
        trace_id = f"cli-{portal_id}-{hash(request) & 0xFFFFFFFF}"
        return run_loop(request, portal_config, working_dir, trace_id)

    lines = [f"{_header(portal_id, portal_config.tier)}", f"**Routing to:** {', '.join(agent_names)}", ""]

    for agent_name in agent_names:
        result = dispatch_agent(agent_name, request, portal_config=portal_config, mode="preview")
        lines.append(f"### {result.agent_name}")
        if result.status == "error":
            lines.append(f"❌ {result.error_message}")
        else:
            lines.append(result.data.get("full_prompt", "").split("User request:")[1].split("\n")[0] if "User request:" in result.data.get("full_prompt", "") else "")

    return "\n".join(lines)


def _handle_portal_command(subcommand: str, working_dir: str) -> str:
    parts = subcommand.split(maxsplit=1)
    if not parts:
        return "Usage: /hubspot portal {switch <id> | list}"

    action = parts[0].lower()
    if action == "switch":
        if len(parts) < 2:
            return "Usage: /hubspot portal switch <portal_id>"
        portal_id = parts[1].strip()
        return f"Switched to portal {portal_id}."

    if action == "list":
        return "Configured portals: (not yet implemented — use `.hubspot-portal` files)"

    return f"Unknown portal command: {action}"


def _handle_refresh(working_dir: str) -> str:
    from hubspot_agent.cache import SchemaCache

    portal_id = detect_default_portal(working_dir)
    if not portal_id:
        return "No default portal found to refresh."

    cache = SchemaCache(portal_id)
    cache.refresh_all()
    return f"Cache refreshed for portal {portal_id}."

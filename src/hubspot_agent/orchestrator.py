from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from hubspot_agent.agents.analytics import get_analytics_agent_prompt
from hubspot_agent.agents.associations import get_associations_agent_prompt
from hubspot_agent.agents.engagements import get_engagements_agent_prompt
from hubspot_agent.agents.hygiene import get_hygiene_agent_prompt
from hubspot_agent.agents.lists import get_lists_agent_prompt
from hubspot_agent.agents.objects import get_objects_agent_prompt
from hubspot_agent.agents.pipelines import get_pipelines_agent_prompt
from hubspot_agent.agents.properties import get_properties_agent_prompt
from hubspot_agent.agents.raw_api import get_raw_api_agent_prompt
from hubspot_agent.agents.users import get_users_agent_prompt
from hubspot_agent.agents.workflows import get_workflows_agent_prompt
from hubspot_agent.config import PortalConfig
from hubspot_agent.agent_dispatch import build_triage_prompt, spawn_agent
from hubspot_agent.models import AgentResult, LoopPlan, PreviewResult, RiskLevel, StepArtifact
from hubspot_agent.planning import parse_plan, plan_to_markdown, validate_plan
from hubspot_agent.sequential_dispatch import execute_plan
from hubspot_agent.snapshot import save_undo_snapshot

# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_AGENT_KEYWORDS: dict[str, list[str]] = {
    "objects": ["contact", "company", "deal", "ticket", "record"],
    "properties": ["property", "field", "schema", "custom field"],
    "workflows": ["workflow", "automation", "enroll", "trigger"],
    "lists": ["list", "segment", "add to list"],
    "pipelines": ["pipeline", "stage", "move to"],
    "users": ["user", "permission", "team", "owner", "onboard"],
    "hygiene": ["duplicate", "merge", "dedup", "clean"],
    "analytics": ["report", "metric", "analytics", "how many"],
    "associations": ["associate", "link", "relationship", "related to"],
    "engagements": ["note", "task", "email", "meeting", "call", "activity", "log"],
    "raw_api": ["raw api", "custom endpoint", "direct api", "not covered", "escape hatch"],
}

_STATIC_DEPENDENCIES: dict[str, list[str]] = {
    "workflows": ["properties"],
    "lists": ["objects"],
    "engagements": ["objects"],
}

_AGENT_GETTERS: dict[str, Any] = {
    "objects": get_objects_agent_prompt,
    "properties": get_properties_agent_prompt,
    "workflows": get_workflows_agent_prompt,
    "lists": get_lists_agent_prompt,
    "pipelines": get_pipelines_agent_prompt,
    "users": get_users_agent_prompt,
    "hygiene": get_hygiene_agent_prompt,
    "analytics": get_analytics_agent_prompt,
    "associations": get_associations_agent_prompt,
    "engagements": get_engagements_agent_prompt,
    "raw_api": get_raw_api_agent_prompt,
}


def route_request(request_text: str) -> list[str]:
    text = request_text.lower()
    scored: dict[str, int] = {}

    for agent, keywords in _AGENT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text:
                score += 1
        if score > 0:
            scored[agent] = score

    if not scored:
        return []

    primary = sorted(scored, key=lambda a: scored[a], reverse=True)

    # Dependency ordering
    ordered: list[str] = []
    for agent in primary:
        deps = _STATIC_DEPENDENCIES.get(agent, [])
        for dep in deps:
            if dep in scored and dep not in ordered:
                ordered.append(dep)
        if agent not in ordered:
            ordered.append(agent)

    return ordered


# ---------------------------------------------------------------------------
# Scope validation
# ---------------------------------------------------------------------------


def validate_scopes(
    agent_names: list[str], portal_scopes: list[str]
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    portal_scope_set = set(portal_scopes)

    for name in agent_names:
        getter = _AGENT_GETTERS.get(name)
        if getter is None:
            continue
        prompt = getter()
        required: set[str] = set()
        for tname in prompt.tool_names:
            from hubspot_agent.tools import get_tool
            tool_def = get_tool(tname)
            if tool_def and hasattr(tool_def.func, "__defaults__"):
                # expected_scopes is typically the last kwarg default
                import inspect
                sig = inspect.signature(tool_def.func)
                for param in sig.parameters.values():
                    if param.name == "expected_scopes" and param.default is not inspect.Parameter.empty:
                        if isinstance(param.default, list):
                            required.update(param.default)
            # fallback: look at closure cell defaults
            if tool_def and hasattr(tool_def.func, "__wrapped__"):
                import inspect
                sig = inspect.signature(tool_def.func)
                for param in sig.parameters.values():
                    if param.name == "expected_scopes" and param.default is not inspect.Parameter.empty:
                        if isinstance(param.default, list):
                            required.update(param.default)

        missing_for_agent = sorted(required - portal_scope_set)
        if missing_for_agent:
            missing[name] = missing_for_agent

    return missing


# ---------------------------------------------------------------------------
# HITL approval
# ---------------------------------------------------------------------------


def needs_approval(risk_level: RiskLevel) -> bool:
    return risk_level != RiskLevel.LOW


def present_preview(result: PreviewResult, mode: str = "summary") -> str:
    lines = [
        f"### Proposed Change ({result.risk_level.value.upper()})",
        f"- **Impact:** {result.impact_count} records",
    ]
    if mode == "details" and result.preview:
        lines.append("- **Affected records:**")
        for item in result.preview.get("affected", []):
            lines.append(f"  - ID: {item.get('id')} | Name: {item.get('name', 'N/A')}")
        lines.append(f"- **Exact API call:** POST {result.proposed_payload.get('endpoint', 'N/A')}")
        lines.append("- **Backup advised:** This action cannot be undone.")
    elif result.preview:
        lines.append("- **Preview:**")
        for key, value in result.preview.items():
            lines.append(f"  - {key}: {value}")
    if result.risk_level == RiskLevel.DESTRUCTIVE:
        lines.append(f"\n**Destructive action.** Type `{result.impact_count}` to confirm, or `details` for full record list.")
    else:
        lines.append("\nApprove? (y/n/details)")
    return "\n".join(lines)


def store_preview_for_execution(
    portal_id: str,
    action_id: str,
    result: PreviewResult,
) -> Path:
    snapshot_dir = Path.home() / ".claude" / "hubspot" / portal_id / "undo_snapshots"
    return save_undo_snapshot(str(snapshot_dir), action_id, result.original_values)


# ---------------------------------------------------------------------------
# Dispatch helpers
# ---------------------------------------------------------------------------


def dispatch_agent(
    agent_name: str,
    user_request: str,
    portal_config: PortalConfig | None = None,
    mode: str = "preview",
    payload: dict[str, Any] | None = None,
) -> AgentResult:
    getter = _AGENT_GETTERS.get(agent_name)
    if getter is None:
        return AgentResult(
            agent_name=agent_name,
            status="error",
            error_message=f"Unknown agent: {agent_name}",
        )

    prompt = getter(portal_config)
    full_prompt_parts = [prompt.system_prompt, f"\nUser request: {user_request}", f"\nMode: {mode}"]

    if mode == "execute" and payload is not None:
        full_prompt_parts.append(f"\nExecute the following payload:\n```json\n{json.dumps(payload, indent=2)}\n```")

    full_prompt = "\n".join(full_prompt_parts)

    return AgentResult(
        agent_name=agent_name,
        status="preview" if mode == "preview" else "ready",
        data={"system_prompt": prompt.system_prompt, "full_prompt": full_prompt, "tool_names": prompt.tool_names},
    )


# ---------------------------------------------------------------------------
# Post-timeout reconciliation
# ---------------------------------------------------------------------------


def reconcile_after_timeout(
    portal_id: str,
    expected_action: str,
    expected_payload: dict[str, Any],
) -> dict[str, Any]:
    action_id = str(uuid.uuid4())[:8]
    return {
        "action_id": action_id,
        "portal_id": portal_id,
        "expected_action": expected_action,
        "expected_payload": expected_payload,
        "reconciliation_needed": True,
        "instruction": (
            f"A previous write operation timed out. "
            f"Dispatch HygieneAgent to verify state for action '{expected_action}'. "
            f"Compare expected payload against actual HubSpot state and report discrepancies."
        ),
    }


# ---------------------------------------------------------------------------
# Loop orchestration
# ---------------------------------------------------------------------------


def _build_capability_matrix(portal_config: PortalConfig | None) -> dict[str, bool]:
    if portal_config is None:
        return {}
    return {
        "objects": True,
        "properties": True,
        "workflows": portal_config.tier in {"Professional", "Enterprise"},
        "lists": True,
        "pipelines": True,
        "users": True,
        "hygiene": True,
        "analytics": True,
        "associations": True,
        "engagements": True,
        "raw_api": True,
    }


def _is_clarifying_response(raw: str) -> bool:
    """Heuristic: if the triage response is not valid JSON, treat it as clarifying questions."""
    if not raw or raw.strip().startswith("["):
        return True
    parsed = parse_plan(raw)
    return parsed is None


def run_loop(
    request_text: str,
    portal_config: PortalConfig,
    working_dir: str,
    trace_id: str,
    approve_callback: Any = None,
) -> str:
    """Run the closed-loop planner/executor/verifier for a multi-step HubSpot request.

    Returns a Markdown summary or clarifying question.
    """
    # Triage
    triage_prompt = build_triage_prompt(request_text, portal_config)
    triage_raw = spawn_agent("triage", triage_prompt, context={"working_dir": working_dir})

    if _is_clarifying_response(triage_raw):
        return (
            f"📍 Portal: {portal_config.portal_id} ({portal_config.tier})\n\n"
            f"I need a bit more clarity before I can plan this:\n\n{triage_raw.strip()}"
        )

    plan = parse_plan(triage_raw)
    if plan is None:
        return (
            f"📍 Portal: {portal_config.portal_id} ({portal_config.tier})\n\n"
            f"I could not build a plan from that request. Could you rephrase?"
        )

    # Validate plan against capabilities
    capability_matrix = _build_capability_matrix(portal_config)
    validation_errors = validate_plan(plan, capability_matrix)
    if validation_errors:
        return (
            f"📍 Portal: {portal_config.portal_id} ({portal_config.tier})\n\n"
            f"The generated plan cannot be executed:\n"
            + "\n".join(f"- {e}" for e in validation_errors)
            + "\n\nPlease adjust your request or upgrade the portal capabilities."
        )

    # Execute sequentially
    try:
        artifacts = execute_plan(
            plan,
            request_text,
            portal_config,
            trace_id,
            approve_callback=approve_callback,
        )
    except RuntimeError as exc:
        return (
            f"📍 Portal: {portal_config.portal_id} ({portal_config.tier})\n\n"
            f"Execution stopped: {exc}"
        )

    summary_lines = [
        f"📍 Portal: {portal_config.portal_id} ({portal_config.tier})",
        f"**Goal:** {plan.goal}",
        "",
        "### Plan executed",
        plan_to_markdown(plan),
        "",
        "### Artifacts",
    ]
    for artifact in artifacts:
        summary_lines.append(f"- Step {artifact.step_number} ({artifact.agent}): {artifact.outputs}")
        if artifact.warnings:
            summary_lines.append(f"  - warnings: {artifact.warnings}")

    return "\n".join(summary_lines)


def run_simple(
    request_text: str,
    portal_config: PortalConfig,
) -> list[AgentResult]:
    """Backwards-compatible flat dispatch for single-domain requests.

    Returns a list of AgentResult objects (one per routed agent).
    """
    agent_names = route_request(request_text)
    results: list[AgentResult] = []
    for agent_name in agent_names:
        result = dispatch_agent(agent_name, request_text, portal_config=portal_config, mode="preview")
        results.append(result)
    return results

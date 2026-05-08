from __future__ import annotations

import asyncio
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
from hubspot_agent.capabilities import (
    CapabilityMatrix,
    capability_explanation,
    probe_portal,
    validate_capabilities,
)
from hubspot_agent.config import PortalConfig
from hubspot_agent.models import AgentResult, BatchApprovalMode, PreviewResult, RiskLevel
from hubspot_agent.research import classify_url
from hubspot_agent.cache import warm_standard_schemas
from hubspot_agent.config import load_portal_config
from hubspot_agent.maintenance import run_maintenance
from hubspot_agent.snapshot import save_undo_snapshot
from hubspot_agent.ledger import ActionLedger
from hubspot_agent.trace import emit_trace
from hubspot_agent.preview import format_preview
from hubspot_agent.reflection import reflect_on_write
from hubspot_agent.routing import (
    apply_routing_overrides,
    build_routing_overrides_context,
    load_routing_overrides,
)


async def initialize_session(portal_id: str) -> None:
    try:
        await asyncio.wait_for(run_maintenance(portal_id), timeout=10.0)
    except asyncio.TimeoutError:
        pass
    portal_config = load_portal_config(portal_id)
    if portal_config is not None:
        try:
            await asyncio.wait_for(warm_standard_schemas(portal_config), timeout=15.0)
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

# Fast-path keywords for the top 5 most common requests to avoid LLM latency
# for simple reads.  Everything else routes through the LLM reasoning prompt.
_FAST_PATH_KEYWORDS: dict[str, list[str]] = {
    "objects": ["contact", "company", "deal", "ticket"],
    "properties": ["property", "field", "schema", "custom field"],
    "workflows": ["workflow", "automation", "enroll", "trigger"],
    "lists": ["list", "segment", "add to list"],
    "engagements": ["note", "task", "meeting", "call", "activity", "log"],
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

_AGENT_DESCRIPTIONS: dict[str, str] = {
    name: getter().domain_description
    for name, getter in _AGENT_GETTERS.items()
}


def _order_with_dependencies(agent_names: list[str]) -> list[str]:
    ordered: list[str] = []
    for agent in agent_names:
        deps = _STATIC_DEPENDENCIES.get(agent, [])
        for dep in deps:
            if dep in agent_names and dep not in ordered:
                ordered.append(dep)
        if agent not in ordered:
            ordered.append(agent)
    return ordered


def _fast_path_route(
    request_text: str, overrides: dict[str, Any] | None = None
) -> list[str] | None:
    """Keyword fast-path for top 5 common requests. Returns None if no clear match."""
    text = apply_routing_overrides(request_text.lower(), overrides or {})
    scored: dict[str, int] = {}
    for agent, keywords in _FAST_PATH_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scored[agent] = score
    # Apply agent overrides from routing configuration
    agent_overrides: dict[str, list[str]] = (overrides or {}).get("agent_overrides", {})
    for pattern, agents in agent_overrides.items():
        if pattern.lower() in text:
            for agent in agents:
                scored[agent] = scored.get(agent, 0) + 1
    if not scored:
        return None
    primary = sorted(scored, key=lambda a: scored[a], reverse=True)
    if len(primary) == 1:
        return _order_with_dependencies(primary)
    if scored[primary[0]] >= 2 * scored.get(primary[1], 0):
        return _order_with_dependencies(primary)
    return None


def build_routing_prompt(request_text: str, portal_id: str | None = None) -> str:
    template_path = Path(__file__).parent / "prompts" / "routing.txt"
    template = template_path.read_text()
    descriptions = "\n".join(
        f"- {name}: {desc}" for name, desc in _AGENT_DESCRIPTIONS.items()
    )
    prompt = (
        template.replace("{{agent_descriptions}}", descriptions)
        .replace("{{request_text}}", request_text)
    )
    overrides = load_routing_overrides(portal_id) if portal_id else {}
    context = build_routing_overrides_context(overrides)
    if context:
        prompt += f"\n\n{context}"
    return prompt


def parse_llm_routing_response(response: str) -> list[str]:
    """Parse an LLM routing response into a list of agent names."""
    try:
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            parsed = json.loads(response[start:end])
            if isinstance(parsed, list):
                valid = [a for a in parsed if a in _AGENT_DESCRIPTIONS]
                return _order_with_dependencies(valid)
        parsed = json.loads(response)
        if isinstance(parsed, list):
            valid = [a for a in parsed if a in _AGENT_DESCRIPTIONS]
            return _order_with_dependencies(valid)
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def route_request(
    request_text: str,
    llm_response: str | None = None,
    portal_id: str | None = None,
) -> list[str]:
    """Route a request to appropriate agents.

    If *llm_response* is provided it is parsed directly (the caller has
    already reasoned about routing).  Otherwise a fast-path keyword match
    is attempted for the top 5 common requests; if that is ambiguous an
    empty list is returned so the caller can fall back to LLM reasoning.
    """
    overrides = load_routing_overrides(portal_id) if portal_id else {}
    if llm_response is not None:
        return parse_llm_routing_response(llm_response)
    fast_path = _fast_path_route(request_text, overrides)
    if fast_path is not None:
        return fast_path
    return []


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
# Capability validation
# ---------------------------------------------------------------------------


async def check_dispatch_readiness(
    agent_names: list[str],
    portal_config: PortalConfig,
) -> dict[str, Any]:
    """Validate scopes and capabilities before dispatching agents.

    Returns a dict with:
      - 'missing_scopes': dict[str, list[str]] — per-agent missing scopes
      - 'missing_capabilities': dict[str, list[str]] — per-agent missing features
      - 'ready': bool — True if nothing blocks dispatch
      - 'decline_reason': str | None — human-readable explanation if not ready
    """
    scope_result = validate_scopes(agent_names, portal_config.scopes_granted or [])
    matrix = await probe_portal(portal_config)
    capability_result = validate_capabilities(agent_names, matrix)

    ready = not scope_result and not capability_result
    decline_reason: str | None = None
    if not ready:
        parts: list[str] = []
        if capability_result:
            for agent, features in capability_result.items():
                for feature in features:
                    parts.append(capability_explanation(feature))
        if scope_result:
            for agent, scopes in scope_result.items():
                parts.append(f"{agent} requires scopes: {', '.join(scopes)}")
        decline_reason = "Cannot dispatch: " + "; ".join(parts)

    return {
        "missing_scopes": scope_result,
        "missing_capabilities": capability_result,
        "ready": ready,
        "decline_reason": decline_reason,
    }


# ---------------------------------------------------------------------------
# HITL approval
# ---------------------------------------------------------------------------


def needs_approval(risk_level: RiskLevel) -> bool:
    return risk_level != RiskLevel.LOW


def parse_batch_mode(request_text: str) -> tuple[BatchApprovalMode, str]:
    """Extract batch approval mode from request text and return (mode, cleaned_text)."""
    text = request_text.strip().lower()
    if "--pattern" in text:
        return BatchApprovalMode.PATTERN, request_text.replace("--pattern", "").strip()
    if "--batch" in text:
        return BatchApprovalMode.BATCH, request_text.replace("--batch", "").strip()
    return BatchApprovalMode.SINGLE, request_text


def normalize_informing_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize informing_sources using URL classification.

    Overrides any entry whose self-reported (source, trust_tier) disagrees
    with the URL-derived classification, except it never upgrades a
    self-reported 'community-accepted' to 'official' based on URL alone.
    """
    normalized: list[dict[str, Any]] = []
    for entry in sources:
        url = entry.get("url", "")
        url_source, url_tier = classify_url(url)
        reported_source = entry.get("source", "")
        reported_tier = entry.get("trust_tier", "")
        # If URL says official, force source/tier to official
        if url_source == "official":
            entry["source"] = "official"
            entry["trust_tier"] = "official"
        else:
            # URL says community.  Preserve richer sub-agent context unless
            # the agent claimed something impossible (e.g. official on a
            # non-official domain).
            if reported_source == "official":
                entry["source"] = url_source
                # Downgrade tier but keep accepted-answer context if present
                if reported_tier == "community-accepted":
                    entry["trust_tier"] = "community-accepted"
                else:
                    entry["trust_tier"] = url_tier
            # If agent said community and URL says community, trust the agent
            # unless it claimed a tier we can't justify from the URL.
            if reported_source == "community" and reported_tier == "official":
                entry["trust_tier"] = url_tier
        normalized.append(entry)
    return normalized


def present_preview(result: PreviewResult, mode: str = "summary") -> str:
    lines = [
        f"### Proposed Change ({result.risk_level.value.upper()})",
        f"- **Impact:** {result.impact_count} records",
    ]
    if mode == "diff":
        old_records = result.original_values.get("records", [])
        new_records = result.proposed_payload.get("records", [])
        if old_records and new_records:
            lines.append(format_preview(old_records, new_records, result.impact_count, mode="diff"))
        elif result.preview:
            lines.append("- **Preview:**")
            for key, value in result.preview.items():
                lines.append(f"  - {key}: {value}")
    elif mode == "details" and result.preview:
        lines.append("- **Affected records:**")
        for item in result.preview.get("affected", []):
            lines.append(f"  - ID: {item.get('id')} | Name: {item.get('name', 'N/A')}")
        lines.append(f"- **Exact API call:** POST {result.proposed_payload.get('endpoint', 'N/A')}")
        lines.append("- **Backup advised:** This action cannot be undone.")
    elif result.preview:
        lines.append("- **Preview:**")
        for key, value in result.preview.items():
            lines.append(f"  - {key}: {value}")
    if result.informing_sources:
        lines.append("\n**Informed by:**")
        for src in normalize_informing_sources(result.informing_sources):
            tier_label = src.get("trust_tier", "")
            title = src.get("title", "Untitled")
            url = src.get("url", "")
            if tier_label == "official":
                lines.append(f"- [Official: {title}]({url})")
            else:
                display_tier = tier_label.replace("-", " ")
                lines.append(f"- [{display_tier.title()}: {title}]({url})")

    if result.batch_mode == BatchApprovalMode.BATCH:
        lines.append("\n**Batch mode:** Approve this full plan once to execute all steps.")
        lines.append("Approve entire plan? (y/n)")
    elif result.batch_mode == BatchApprovalMode.PATTERN:
        lines.append(f"\n**Pattern mode:** Approve a sample of {result.pattern_sample_size} records; the rest will auto-execute with the same pattern.")
        lines.append("Approve sample? (y/n)")
    elif result.risk_level == RiskLevel.DESTRUCTIVE:
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
    trace_id: str | None = None,
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE,
) -> AgentResult:
    getter = _AGENT_GETTERS.get(agent_name)
    if getter is None:
        if trace_id and portal_config:
            emit_trace(
                portal_config.portal_id,
                "error",
                trace_id,
                {"agent": agent_name, "error": f"Unknown agent: {agent_name}"},
            )
        return AgentResult(
            agent_name=agent_name,
            status="error",
            error_message=f"Unknown agent: {agent_name}",
        )

    action_id = str(uuid.uuid4())[:8]
    portal_id = portal_config.portal_id if portal_config else None

    # Idempotency check for writes
    if mode == "execute" and payload is not None and portal_config is not None:
        ledger = ActionLedger(portal_config.portal_id)
        action_label = user_request.strip().splitlines()[0][:120]
        duplicate = ledger.find_similar_in_flight(agent_name, action_label, payload)
        if duplicate is not None:
            if trace_id:
                emit_trace(
                    portal_config.portal_id,
                    "error",
                    trace_id,
                    {"agent": agent_name, "error": "duplicate action", "duplicate_action_id": duplicate.get("action_id")},
                )
            return AgentResult(
                agent_name=agent_name,
                status="duplicate",
                error_message=(
                    f"Similar action already in flight (started at {duplicate.get('timestamp')}). "
                    f"Wait for it to complete or cancel before retrying."
                ),
                data={"duplicate_action_id": duplicate.get("action_id")},
            )
        ledger.start_action(action_id, agent_name, action_label, payload)

    if trace_id and portal_id:
        emit_trace(
            portal_id,
            "tool_call",
            trace_id,
            {"agent": agent_name, "mode": mode, "action_id": action_id, "batch_mode": batch_mode.value},
        )

    prompt = getter(portal_config)
    full_prompt_parts = [
        prompt.system_prompt,
        f"\nUser request: {user_request}",
        f"\nMode: {mode}",
    ]

    if batch_mode != BatchApprovalMode.SINGLE:
        full_prompt_parts.append(f"\nBatch approval mode: {batch_mode.value}")
        if batch_mode == BatchApprovalMode.PATTERN:
            full_prompt_parts.append("When generating a preview, include a sample of records for approval; remaining records will auto-execute if the sample is approved.")
        elif batch_mode == BatchApprovalMode.BATCH:
            full_prompt_parts.append("The user has opted to approve the full plan in one go. Present a concise summary of all changes.")

    if mode == "execute" and payload is not None:
        full_prompt_parts.append(f"\nExecute the following payload:\n```json\n{json.dumps(payload, indent=2)}\n```")

    full_prompt = "\n".join(full_prompt_parts)

    data: dict[str, Any] = {
        "system_prompt": prompt.system_prompt,
        "full_prompt": full_prompt,
        "tool_names": prompt.tool_names,
        "batch_mode": batch_mode.value,
    }
    if mode == "execute" and payload is not None:
        data["action_id"] = action_id

    # Phase A gap #1: record_action_completion should be called after the
    # actual write succeeds in the execute flow. It is NOT called here
    # because dispatch_agent only builds the prompt; execution happens
    # in the LLM layer. When Phase B builds the full execute flow, wire
    # record_action_completion(portal_config.portal_id, action_id, result)
    # after successful tool execution.

    return AgentResult(
        agent_name=agent_name,
        status="preview" if mode == "preview" else "ready",
        data=data,
    )


async def dispatch_agents_parallel(
    agent_names: list[str],
    user_request: str,
    portal_config: PortalConfig | None = None,
    mode: str = "preview",
    trace_id: str | None = None,
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE,
) -> list[AgentResult]:
    """Dispatch multiple agents in parallel for read-only operations.

    Preview-mode agents are independent and safe to run concurrently.
    Execute-mode agents remain serial for HITL safety.
    """
    if mode == "execute":
        # Serial dispatch for write operations
        return [
            dispatch_agent(
                name,
                user_request,
                portal_config=portal_config,
                mode=mode,
                trace_id=trace_id,
                batch_mode=batch_mode,
            )
            for name in agent_names
        ]

    coros = [
        asyncio.to_thread(
            dispatch_agent,
            name,
            user_request,
            portal_config=portal_config,
            mode=mode,
            trace_id=trace_id,
            batch_mode=batch_mode,
        )
        for name in agent_names
    ]
    return await asyncio.gather(*coros)


def dispatch_correction(
    agent_name: str,
    user_request: str,
    original_result: AgentResult,
    corrected_payload: dict[str, Any],
    correction_reason: str,
    portal_config: PortalConfig | None = None,
    trace_id: str | None = None,
) -> AgentResult:
    """Re-dispatch an agent with a self-corrected payload for HITL approval.

    Builds a preview-mode prompt that surfaces the original error, the
    correction reason, and the corrected payload so the user can approve
    the fix before execution.
    """
    getter = _AGENT_GETTERS.get(agent_name)
    if getter is None:
        return AgentResult(
            agent_name=agent_name,
            status="error",
            error_message=f"Unknown agent: {agent_name}",
        )

    action_id = str(uuid.uuid4())[:8]
    portal_id = portal_config.portal_id if portal_config else None

    if trace_id and portal_id:
        emit_trace(
            portal_id,
            "tool_call",
            trace_id,
            {
                "agent": agent_name,
                "mode": "correction",
                "action_id": action_id,
                "correction_reason": correction_reason,
            },
        )

    prompt = getter(portal_config)
    original_error = original_result.error_message or "Unknown error"
    full_prompt_parts = [
        prompt.system_prompt,
        f"\nUser request: {user_request}",
        f"\nMode: preview (self-correction)",
        f"\nThe previous attempt failed with:\n```\n{original_error}\n```",
        f"\nCorrection reason: {correction_reason}",
        f"\nProposed corrected payload:\n```json\n{json.dumps(corrected_payload, indent=2)}\n```",
    ]
    full_prompt = "\n".join(full_prompt_parts)

    data: dict[str, Any] = {
        "system_prompt": prompt.system_prompt,
        "full_prompt": full_prompt,
        "tool_names": prompt.tool_names,
        "action_id": action_id,
        "corrected_payload": corrected_payload,
        "correction_reason": correction_reason,
    }

    return AgentResult(
        agent_name=agent_name,
        status="corrected",
        data=data,
        corrected_payload=corrected_payload,
        correction_reason=correction_reason,
    )


def record_action_completion(portal_id: str, action_id: str, result: dict[str, Any]) -> None:
    ledger = ActionLedger(portal_id)
    ledger.complete_action(action_id, result)


# ---------------------------------------------------------------------------
# Post-action reflection
# ---------------------------------------------------------------------------


async def verify_write_result(
    portal_config: PortalConfig,
    object_type: str,
    object_id: str,
    expected_properties: dict[str, Any],
) -> dict[str, Any]:
    """Re-fetch a resource after a write and verify field-level match.

    Returns a dict suitable for attaching to ``AgentResult.reflection``.
    """
    result = await reflect_on_write(
        portal_config,
        object_type=object_type,
        object_id=object_id,
        expected_properties=expected_properties,
    )
    return result.to_dict()


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

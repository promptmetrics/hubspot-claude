from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from hubspot_agent.capabilities import CapabilityMatrix, probe_portal, validate_capabilities
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import CONFIG_DIR, load_portal_config
from hubspot_agent.dispatch import get_execute_dispatch, get_preview_builder, get_reconcile_dispatch
from hubspot_agent.models import AgentResult, BatchApprovalMode, LoopPlan, PreviewResult, RiskLevel, StepArtifact, TaskIntent
from hubspot_agent.persistence import clear as _clear_pending_preview
from hubspot_agent.persistence import list_pending as _list_pending_previews
from hubspot_agent.persistence import load as _load_pending_preview
from hubspot_agent.persistence import store as _store_pending_preview
from hubspot_agent.preview import format_preview
from hubspot_agent.research import classify_url
from hubspot_agent.tools import invoke_tool

# Loop engineering imports (Group 1)
from hubspot_agent.agent_dispatch import build_triage_prompt, spawn_agent
from hubspot_agent.planning import parse_plan, plan_to_markdown, validate_plan
from hubspot_agent.sequential_dispatch import execute_plan
from hubspot_agent.validation import format_scope_error, validate_scopes


def _normalize_informing_sources(sources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Validate and correct trust-tier assignments from sub-agents.

    Sub-agents are expected to assign trust_tier using richer context
    (accepted-answer flag, employee badge, post age). This function
    catches obvious URL-vs-tier mismatches so the orchestrator can
    override misreported tiers before they reach the user or audit log.
    """
    if not sources:
        return []
    normalized: list[dict[str, Any]] = []
    for src in sources:
        url = src.get("url", "")
        inferred_source, inferred_tier = classify_url(url)
        reported_tier = src.get("trust_tier", inferred_tier)
        # If the reported tier contradicts what the URL alone supports,
        # downgrade to the safest tier the URL can justify.
        if inferred_source == "official" and reported_tier != "official":
            # URL is official but agent said otherwise — fix it
            corrected_tier = "official"
        elif inferred_source == "community" and reported_tier == "official":
            # Agent claimed official but URL is community — downgrade
            corrected_tier = "community-unverified"
        else:
            corrected_tier = reported_tier
        normalized.append(
            {
                "source": inferred_source,
                "trust_tier": corrected_tier,
                "title": src.get("title", ""),
                "url": url,
                "last_updated": src.get("last_updated"),
            }
        )
    return normalized


async def initialize_session(portal_id: str) -> None:
    """Warm schema cache and reap expired pending previews for a portal."""
    from hubspot_agent.cache import warm_standard_schemas, discover_custom_schemas
    from hubspot_agent.config import load_portal_config
    from hubspot_agent.persistence import reap_expired

    portal_config = load_portal_config(portal_id)
    if portal_config is None:
        raise RuntimeError(f"No config for portal {portal_id}")

    await warm_standard_schemas(portal_config)
    await discover_custom_schemas(portal_config)
    reap_expired(portal_id, max_age_hours=24)


def parse_batch_mode(request: str) -> tuple[BatchApprovalMode, str]:
    """Parse batch approval mode keywords from request text."""
    text = request.lower()
    if "--batch" in text or "approve all" in text:
        return BatchApprovalMode.BATCH, request.replace("--batch", "").replace("approve all", "").strip()
    return BatchApprovalMode.SINGLE, request


_DEPENDENCY_GRAPH: dict[str, list[str]] = {
    "properties": ["workflows"],
    "objects": ["lists", "engagements"],
    "workflows": ["lists"],
}


_SEQUENTIAL_TRIGGERS = [" and ", " then ", " followed by "]


def _order_by_dependencies(agents: list[str]) -> list[str]:
    """Return agents in dependency order (prerequisites first)."""
    ordered: list[str] = []
    remaining = set(agents)
    while remaining:
        ready = {
            a for a in remaining
            if not any(dep in remaining for dep in _DEPENDENCY_GRAPH.get(a, []))
        }
        if not ready:
            ready = {remaining.pop()}
        for a in sorted(ready):
            ordered.append(a)
            remaining.discard(a)
    return ordered


def route_request(request_text: str, portal_id: str | None = None) -> list[str]:
    """Keyword-based routing with conjunction detection."""
    text = request_text.lower()
    scores: dict[str, int] = {}

    keywords = {
        "objects": ["contact", "company", "deal", "ticket", "lead", "object", "record", "find", "search", "get", "create", "update", "delete", "merge", "custom object"],
        "properties": ["property", "field", "schema", "label", "type", "group", "required"],
        "workflows": ["workflow", "automation", "enroll", "trigger", "action", "delay", "branch", "blueprint"],
        "lists": ["list", "segment", "membership", "static list", "active list", "filter"],
        "pipelines": ["pipeline", "stage", "deal stage", "ticket pipeline", "move to"],
        "users": ["user", "team", "permission", "role", "owner", "assign"],
        "hygiene": ["duplicate", "clean", "merge", "deduplicate", "stale", "missing", "data quality"],
        "analytics": ["report", "dashboard", "metric", "analytics", "funnel", "conversion", "pipeline report"],
        "associations": ["associate", "link", "relationship", "related", "linked", "connection", "associated with", "linked to", "related to"],
        "engagements": ["call", "email", "meeting", "note", "task", "activity", "log"],
        "custom_objects": ["custom object", "custom schema", "object schema"],
        "service": ["ticket pipeline", "knowledge base", "kb article", "feedback survey", "service automation"],
        "raw_api": ["api", "endpoint", "curl", "raw", "crm/v3", "hubspot api"],
    }

    for agent, words in keywords.items():
        for word in words:
            if word in text:
                scores[agent] = scores.get(agent, 0) + 1

    if not scores:
        return []

    best = sorted(scores, key=lambda k: scores[k], reverse=True)
    primary_score = scores[best[0]]

    # Cross-object association detection: if two object types appear with association language
    _OBJECT_TYPES = {"contact", "contacts", "company", "companies", "deal", "deals", "ticket", "tickets"}
    _ASSOC_PHRASES = {"associated with", "linked to", "related to", "at", "for"}
    found_objs = {obj for obj in _OBJECT_TYPES if obj in text}
    has_assoc_phrase = any(phrase in text for phrase in _ASSOC_PHRASES)
    if len(found_objs) >= 2 and has_assoc_phrase:
        # Force both associations + objects when cross-object language is detected
        forced_agents = ["objects", "associations"]
        return _order_by_dependencies(forced_agents)

    # Conjunction detection: if "and" links two high-scoring distinct domains
    has_conjunction = any(trigger in text for trigger in _SEQUENTIAL_TRIGGERS)
    if has_conjunction and len(best) >= 2:
        secondary_score = scores.get(best[1], 0)
        if secondary_score > 0 and primary_score < 2 * secondary_score:
            agents = [best[0], best[1]]
            return _order_by_dependencies(agents)

    if len(best) > 1 and primary_score >= 2 * scores.get(best[1], 0):
        return [best[0]]
    if len(best) > 1 and scores.get(best[1], 0) > 0:
        return _order_by_dependencies([best[0], best[1]])
    return [best[0]]


def _fast_path_route(request_text: str, portal_id: str | None = None) -> list[str] | None:
    """Stub: fast-path keyword routing for Phase 0."""
    text = request_text.lower()

    if portal_id:
        from hubspot_agent.cache import SchemaCache
        cache = SchemaCache(portal_id)
        for custom_name in cache.list_custom_object_names():
            if custom_name.lower() in text:
                return ["objects"]
    else:
        return None

    keywords = {
        "objects": ["contact", "company", "deal", "ticket", "lead", "object", "record", "find", "search", "get", "create", "update", "delete", "merge"],
        "properties": ["property", "field", "schema", "label", "type", "group", "required"],
        "workflows": ["workflow", "automation", "enroll", "trigger", "action", "delay", "branch", "blueprint"],
        "lists": ["list", "segment", "membership", "static list", "active list", "filter"],
        "pipelines": ["pipeline", "stage", "deal stage", "ticket pipeline", "move to"],
        "users": ["user", "team", "permission", "role", "owner", "assign"],
        "hygiene": ["duplicate", "clean", "merge", "deduplicate", "stale", "missing", "data quality"],
        "analytics": ["report", "dashboard", "metric", "analytics", "funnel", "conversion", "pipeline report"],
        "associations": ["associate", "link", "relationship", "related", "linked", "connection"],
        "engagements": ["call", "email", "meeting", "note", "task", "activity", "log"],
        "service": ["ticket pipeline", "knowledge base", "kb article", "feedback survey", "service automation"],
        "raw_api": ["api", "endpoint", "curl", "raw", "crm/v3", "hubspot api"],
    }

    scores: dict[str, int] = {}
    for agent, words in keywords.items():
        for word in words:
            if word in text:
                scores[agent] = scores.get(agent, 0) + 1

    if not scores:
        return None

    best = sorted(scores, key=lambda k: scores[k], reverse=True)
    primary_score = scores[best[0]]
    if len(best) > 1 and primary_score >= 2 * scores.get(best[1], 0):
        return [best[0]]
    if len(best) > 1 and scores.get(best[1], 0) > 0:
        return [best[0], best[1]]
    return [best[0]]


def build_routing_prompt(request_text: str, portal_id: str | None = None) -> str:
    """Stub: routing prompt for Phase 0."""
    return f"Route request: {request_text}"


def parse_llm_routing_response(response: str) -> list[str]:
    """Stub: parse LLM routing response for Phase 0."""
    return [line.strip() for line in response.split(",") if line.strip()]


async def check_dispatch_readiness(agent_names: list[str], portal_config) -> dict[str, Any]:
    """Stub: check if portal supports requested agents."""
    matrix = await probe_portal(portal_config)
    blocked = validate_capabilities(agent_names, matrix)
    if not blocked:
        return {"ready": True}
    reasons = [f"{agent}: {', '.join(missing)}" for agent, missing in blocked.items()]
    return {"ready": False, "decline_reason": "; ".join(reasons)}


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

_SEARCH_WORDS = {"find", "search", "get", "list", "show", "retrieve", "lookup", "query"}
_CREATE_WORDS = {"create", "add", "new", "insert", "build", "make"}
_UPDATE_WORDS = {"update", "change", "edit", "modify", "set", "rename", "patch"}
_DELETE_WORDS = {"delete", "remove", "destroy", "drop", "clear", "purge"}

_OBJ_MAP = {
    "contact": "contacts", "contacts": "contacts",
    "company": "companies", "companies": "companies",
    "deal": "deals", "deals": "deals",
    "ticket": "tickets", "tickets": "tickets",
}

_STOP_WORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and", "or",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "must", "shall", "can", "need", "dare", "ought", "used",
    "find", "search", "get", "show", "list", "create", "add", "new", "update",
    "change", "edit", "modify", "delete", "remove", "contact", "company", "deal",
    "ticket", "contacts", "companies", "deals", "tickets",
}


def _parse_agent_intent(agent_name: str, request_text: str) -> TaskIntent:
    text = request_text.lower()

    if any(w in text for w in _SEARCH_WORDS):
        intent_type = "search"
    elif any(w in text for w in _CREATE_WORDS):
        intent_type = "create"
    elif any(w in text for w in _UPDATE_WORDS):
        intent_type = "update"
    elif any(w in text for w in _DELETE_WORDS):
        intent_type = "delete"
    else:
        intent_type = "unknown"

    target_object = None
    if agent_name == "objects":
        for keyword, obj_type in _OBJ_MAP.items():
            if keyword in text:
                target_object = obj_type
                break

    risk_map = {
        "search": RiskLevel.LOW,
        "create": RiskLevel.MEDIUM,
        "update": RiskLevel.MEDIUM,
        "delete": RiskLevel.DESTRUCTIVE,
        "unknown": RiskLevel.LOW,
    }

    impact = 1 if intent_type in ("create", "update", "delete") else None

    return TaskIntent(
        intent_type=intent_type,
        target_object=target_object,
        description=request_text,
        risk_level=risk_map.get(intent_type, RiskLevel.LOW),
        estimated_impact=impact,
    )


def _extract_search_term(intent: TaskIntent) -> str:
    words = [
        w.strip(".,;:!?")
        for w in intent.description.lower().split()
        if w.strip(".,;:!?") not in _STOP_WORDS and len(w.strip(".,;:!?")) > 2
    ]
    return " ".join(words[:3]) if words else "*"


# ---------------------------------------------------------------------------
# Preview engine
# ---------------------------------------------------------------------------

async def _fallback_preview(
    agent_name: str,
    intent: TaskIntent,
    client: HubSpotClient,
    portal_id: str,
) -> PreviewResult:
    """Generic preview when no agent-specific preview builder is registered."""
    return PreviewResult(
        preview={"message": f"{intent.intent_type} operation on {agent_name}"},
        impact_count=intent.estimated_impact or 1,
        risk_level=intent.risk_level,
    )


async def _build_preview_for_intent(
    agent_name: str,
    intent: TaskIntent,
    client: HubSpotClient,
    portal_id: str,
) -> PreviewResult:
    builder = get_preview_builder(agent_name)
    if builder is not None:
        return await builder(agent_name, intent, client, portal_id)
    return await _fallback_preview(agent_name, intent, client, portal_id)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def dispatch_agent(
    agent_name: str,
    request_text: str,
    portal_config,
    mode: str = "preview",
    trace_id: str | None = None,
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE,
    proposed_payload: dict[str, Any] | None = None,
) -> AgentResult:
    """Dispatch a single agent with preview or execute mode."""
    from hubspot_agent.agents import get_agent_category, get_agent_emoji, get_agent_prompt

    prompt = get_agent_prompt(agent_name, portal_config)
    if prompt is None:
        return AgentResult(
            agent_name=agent_name,
            status="error",
            error_message=f"Unknown agent: {agent_name}",
            category=get_agent_category(agent_name),
            emoji=get_agent_emoji(agent_name),
        )

    intent = _parse_agent_intent(agent_name, request_text)

    # Scope validation (Group 2). Skip if no scope list is recorded.
    if portal_config.scopes_granted:
        blocked = validate_scopes(
            [agent_name], portal_config.scopes_granted, target_object=intent.target_object
        )
        if blocked:
            return AgentResult(
                agent_name=agent_name,
                status="error",
                error_message=format_scope_error(blocked),
                category=get_agent_category(agent_name),
                emoji=get_agent_emoji(agent_name),
            )

    client = HubSpotClient(portal_config)

    try:
        if mode == "preview":
            preview = await _build_preview_for_intent(
                agent_name, intent, client, portal_config.portal_id
            )

            action_id = str(uuid.uuid4())[:8]
            normalized_sources = _normalize_informing_sources(preview.informing_sources)
            preview_data = {
                "agent_name": agent_name,
                "request_text": request_text,
                "intent": intent.model_dump(mode="json"),
                "preview": preview.model_dump(mode="json"),
                "trace_id": trace_id,
                "batch_mode": batch_mode.value,
                "proposed_payload": proposed_payload or {},
                "informing_sources": normalized_sources,
                "required_confirmation": preview.impact_count,
                "confirmed_count": None,
            }
            _store_pending_preview(portal_config.portal_id, action_id, preview_data)

            # Build preview text from the agent's preview dict
            if "message" in preview.preview:
                preview_text = preview.preview["message"]
            elif "records" in preview.preview:
                record_count = len(preview.preview["records"])
                preview_text = f"Found {record_count} records"
                if record_count > 0:
                    ids = [str(r.get("id", "?")) for r in preview.preview["records"][:5]]
                    preview_text += f" (IDs: {', '.join(ids)})"
                    if record_count > 5:
                        preview_text += f" and {record_count - 5} more"
            elif "error" in preview.preview:
                preview_text = f"Error: {preview.preview['error']}"
            else:
                preview_text = format_preview(
                    old_records=[],
                    new_records=[],
                    impact_count=preview.impact_count,
                    mode="summary",
                )

            return AgentResult(
                agent_name=agent_name,
                status="preview",
                data={
                    "action_id": action_id,
                    "preview": preview_text,
                    "risk_level": preview.risk_level.value,
                    "impact_type": intent.intent_type,
                    "target_object": intent.target_object,
                    "impact_count": preview.impact_count,
                    "original_values": preview.original_values,
                    "full_prompt": prompt.system_prompt,
                },
                informing_sources=normalized_sources,
                category=get_agent_category(agent_name),
                emoji=get_agent_emoji(agent_name),
            )

        # Execute mode
        execute_fn = get_execute_dispatch(agent_name)
        if execute_fn is not None:
            result_data = await execute_fn(
                agent_name, intent, request_text, client, portal_config.portal_id, proposed_payload
            )
            if result_data.get("status") == "error":
                return AgentResult(
                    agent_name=agent_name,
                    status="error",
                    error_message=result_data.get("message", "Execution failed"),
                    category=get_agent_category(agent_name),
                    emoji=get_agent_emoji(agent_name),
                )
            if result_data.get("status") == "corrected":
                return AgentResult(
                    agent_name=agent_name,
                    status="corrected",
                    data=result_data.get("data", {}),
                    corrected_payload=result_data.get("corrected_payload"),
                    correction_reason=result_data.get("correction_reason"),
                    category=get_agent_category(agent_name),
                    emoji=get_agent_emoji(agent_name),
                )
            return AgentResult(
                agent_name=agent_name,
                status="success",
                data=result_data.get("data", {"message": result_data.get("message", "")}),
                category=get_agent_category(agent_name),
                emoji=get_agent_emoji(agent_name),
            )

        return AgentResult(
            agent_name=agent_name,
            status="success",
            data={"message": f"Executed {agent_name} for: {request_text}"},
            category=get_agent_category(agent_name),
            emoji=get_agent_emoji(agent_name),
        )
    finally:
        await client.close()


async def dispatch_agents_parallel(
    agent_names: list[str],
    request_text: str,
    portal_config,
    mode: str = "preview",
    trace_id: str | None = None,
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE,
    proposed_payload: dict[str, Any] | None = None,
) -> list[AgentResult]:
    """Dispatch multiple agents concurrently."""
    coros = [
        dispatch_agent(
            name,
            request_text,
            portal_config,
            mode=mode,
            trace_id=trace_id,
            batch_mode=batch_mode,
            proposed_payload=proposed_payload,
        )
        for name in agent_names
    ]
    return await asyncio.gather(*coros)


# ---------------------------------------------------------------------------
# Post-timeout reconciliation
# ---------------------------------------------------------------------------

async def reconcile_after_timeout(
    portal_id: str,
    agent_name: str,
    request_text: str,
    expected_payload: dict[str, Any],
    portal_config,
) -> dict[str, Any]:
    """Verify what was actually applied after a write-operation timeout.

    Dispatches a lightweight read to compare expected vs actual state and
    reports discrepancies. Used only for writes (create, update, delete).
    """
    client = HubSpotClient(portal_config)
    try:
        intent = _parse_agent_intent(agent_name, request_text)

        reconcile_fn = get_reconcile_dispatch(agent_name)
        if reconcile_fn is not None:
            return await reconcile_fn(
                agent_name, intent, request_text, client, portal_id, expected_payload
            )

        return {
            "status": "unknown",
            "message": f"Reconciliation not implemented for agent {agent_name}.",
            "expected": expected_payload,
            "actual": None,
        }
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Loop orchestration (Group 1)
# ---------------------------------------------------------------------------


def _build_loop_capability_matrix(portal_config) -> dict[str, bool]:
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


async def run_loop(
    request_text: str,
    portal_config,
    working_dir: str,
    trace_id: str,
    approve_callback: Any = None,
) -> str:
    """Run the closed-loop planner/executor/verifier for a multi-step HubSpot request."""
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

    capability_matrix = _build_loop_capability_matrix(portal_config)
    validation_errors = validate_plan(plan, capability_matrix)
    if validation_errors:
        return (
            f"📍 Portal: {portal_config.portal_id} ({portal_config.tier})\n\n"
            f"The generated plan cannot be executed:\n"
            + "\n".join(f"- {e}" for e in validation_errors)
            + "\n\nPlease adjust your request or upgrade the portal capabilities."
        )

    try:
        artifacts = await execute_plan(
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


async def run_simple(
    request_text: str,
    portal_config,
) -> list[AgentResult]:
    """Backwards-compatible flat dispatch for single-domain requests."""
    agent_names = route_request(request_text)
    results: list[AgentResult] = []
    for agent_name in agent_names:
        result = await dispatch_agent(agent_name, request_text, portal_config=portal_config, mode="preview")
        results.append(result)
    return results

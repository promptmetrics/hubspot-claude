from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from hubspot_agent.capabilities import CapabilityMatrix, probe_portal, validate_capabilities
from hubspot_agent.client import HubSpotClient, get_last_rate_state
from hubspot_agent.errors import HubSpotError, RateLimitError
from hubspot_agent.config import CONFIG_DIR, load_portal_config
from hubspot_agent.dispatch import get_execute_dispatch, get_preview_builder, get_reconcile_dispatch
from hubspot_agent.models import AgentResult, BatchApprovalMode, LoopPlan, PreviewResult, RiskLevel, StepArtifact, TaskIntent, VerificationResult
from hubspot_agent.persistence import clear as _clear_pending_preview
from hubspot_agent.persistence import list_pending as _list_pending_previews
from hubspot_agent.persistence import load as _load_pending_preview
from hubspot_agent.persistence import store as _store_pending_preview
from hubspot_agent.preview import format_preview
from hubspot_agent.safety import ScopeBlocked, apply_write, normalize_informing_sources as _normalize_informing_sources
from hubspot_agent.tools import invoke_tool

# Loop engineering imports (Group 1)
from hubspot_agent.planning import parse_verification_result, plan_to_markdown, validate_plan
from hubspot_agent.sequential_dispatch import (
    _build_step_request,
    _capture_artifacts,
    _resolve_artifacts,
    is_write_step,
)
from hubspot_agent.snapshot import load_undo_snapshot, snapshot_dir_for_portal
from hubspot_agent.validation import format_scope_error, validate_scopes
from hubspot_agent.loop_controller import LoopController
from hubspot_agent import audit, cron, loop_log, loop_state, schedule_store
from hubspot_agent.policy import load_approval_policy
from hubspot_agent.trace import new_trace_id


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
    if "--pattern" in text:
        return BatchApprovalMode.PATTERN, request.replace("--pattern", "").strip()
    if "--batch" in text or "approve all" in text:
        return BatchApprovalMode.BATCH, request.replace("--batch", "").replace("approve all", "").strip()
    return BatchApprovalMode.SINGLE, request


_SEQUENTIAL_TRIGGERS = [" and ", " then ", " followed by "]

# Lazy cache of word-boundary regexes for route scoring. Populated on first
# `route_request` call via `_compiled_route_patterns()`.
_ROUTE_PATTERNS: dict[str, list[re.Pattern[str]]] = {}


def _compiled_route_patterns() -> dict[str, list[re.Pattern[str]]]:
    """Lazily build and cache word-boundary regexes for every agent's route terms.

    Deferred to first call (not module load) to keep orchestrator import light
    and avoid any import-cycle with the ``hubspot_agent.agents`` package.
    """
    if not _ROUTE_PATTERNS:
        from hubspot_agent.agents import _AGENT_ROUTE_TERMS
        for agent, terms in _AGENT_ROUTE_TERMS.items():
            _ROUTE_PATTERNS[agent] = [
                re.compile(rf"\b{re.escape(term)}\b") for term in terms
            ]
    return _ROUTE_PATTERNS


def route_request(request_text: str, portal_id: str | None = None) -> list[str]:
    """Keyword-based routing with conjunction detection.

    Scores every agent in ``_AGENT_ROUTE_TERMS`` (all 44 specialists) using
    word-boundary regex, so ``"stage"`` no longer matches inside ``"stages"``
    and a bare ``"create"``/``"find"`` (kept out of every domain term list) cannot
    win a route on its own. Cross-object association requires an explicit
    association verb plus ≥2 object nouns — ``"at"``/``"for"`` were dropped from
    the association phrases so innocuous phrasing no longer forces associations.
    """
    text = request_text.lower()
    scores: dict[str, int] = {}
    for agent, patterns in _compiled_route_patterns().items():
        for pat in patterns:
            if pat.search(text):
                scores[agent] = scores.get(agent, 0) + 1

    # Portal custom object types: a cached custom type name (e.g. "pets") is a
    # record noun, so a request like "find all pets" routes to the objects agent
    # rather than falling through to []. Lazy + guarded so a missing/cold cache
    # or absent portal_id never breaks routing.
    if portal_id:
        try:
            from hubspot_agent.cache import SchemaCache
            for ct in SchemaCache(portal_id).list_custom_object_names():
                if ct and re.search(rf"\b{re.escape(ct.lower())}\b", text):
                    scores["objects"] = scores.get("objects", 0) + 1
        except (OSError, ValueError, KeyError):
            # Cold/missing/malformed-cache graceful degradation: degrade to
            # term-only scoring rather than breaking routing. Narrowed on
            # purpose — OSError covers FileNotFoundError, ValueError covers
            # json.JSONDecodeError, KeyError covers absent schema keys. A
            # TypeError/AttributeError/ImportError here is a real bug in the
            # cache layer and must surface, not silently route to [].
            pass

    if not scores:
        return []

    best = sorted(scores, key=lambda k: scores[k], reverse=True)
    primary_score = scores[best[0]]

    # Cross-object association: ≥2 object nouns + an explicit association verb.
    # "record(s)" are included so "link records to companies" still fires.
    _OBJECT_TYPES = {"contact", "contacts", "company", "companies", "deal", "deals",
                     "ticket", "tickets", "record", "records"}
    _ASSOC_PHRASES = ["associated with", "linked to", "related to", "associate",
                      "associate with", "link", "link to", "relate", "relate to"]
    found_objs = {obj for obj in _OBJECT_TYPES if re.search(rf"\b{re.escape(obj)}\b", text)}
    # Word-boundary match the verbs too — bare substring ``in`` would let
    # "relate" match inside "correlate" and force associations for a non-association
    # analytics request. Multi-word phrases ("associated with") still match cleanly.
    has_assoc_phrase = any(
        re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in _ASSOC_PHRASES
    )
    if len(found_objs) >= 2 and has_assoc_phrase:
        return sorted(["objects", "associations"])

    # Conjunction detection: if "and"/"then"/"followed by" links two high-scoring distinct domains
    has_conjunction = any(trigger in text for trigger in _SEQUENTIAL_TRIGGERS)
    if has_conjunction and len(best) >= 2:
        secondary_score = scores.get(best[1], 0)
        if secondary_score > 0 and primary_score < 2 * secondary_score:
            return sorted([best[0], best[1]])

    if len(best) > 1 and primary_score >= 2 * scores.get(best[1], 0):
        return [best[0]]
    if len(best) > 1 and scores.get(best[1], 0) > 0:
        return sorted([best[0], best[1]])
    return [best[0]]


# DEAD CODE — NFR-13: Phase-0 routing stubs.  Not called from any production
# path — routing now goes through ``route_request`` and the ``hubspot route``
# CLI.  Retained importable because tests/test_routing_regression.py and
# tests/test_custom_objects.py import these symbols; do not delete.
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
# END DEAD CODE — NFR-13 (Phase-0 routing stubs)


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


def _has_boundary_word(text: str, words: set[str]) -> bool:
    """True if any word appears as a whole word in ``text``.

    Substring matching (``w in text``) mis-classified tokens like ``"renewal"``
    → create (contains ``"new"``) and ``"created"`` → create (contains
    ``"create"``).  ``\\b``-anchored matching makes ``new`` not match
    ``renewal``/``renew`` and ``create`` not match ``created``, so a write lands
    on the intended record instead of a fuzzy ``records[0]`` (bug 2).
    """
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)

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

    # Priority: search → delete → update → create.  Reads first (a read must
    # never masquerade as a write), then destructive verbs before non-destructive
    # so a phrase carrying both (e.g. "delete the renewal") fails safe into the
    # destructive count gate instead of being reclassified as a create via
    # "new".  Word-boundary matching (see ``_has_boundary_word``) prevents
    # substring false-positives like "renewal"→create or "created"→create.
    if _has_boundary_word(text, _SEARCH_WORDS):
        intent_type = "search"
    elif _has_boundary_word(text, _DELETE_WORDS):
        intent_type = "delete"
    elif _has_boundary_word(text, _UPDATE_WORDS):
        intent_type = "update"
    elif _has_boundary_word(text, _CREATE_WORDS):
        intent_type = "create"
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
    loop_step_number: int | None = None,
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
            try:
                aw = await apply_write(
                    client=client,
                    portal_config=portal_config,
                    preview_builder=lambda c: _build_preview_for_intent(
                        agent_name, intent, c, portal_config.portal_id
                    ),
                    agent_name=agent_name,
                    intent=intent,
                    request_text=request_text,
                    trace_id=trace_id,
                    batch_mode=batch_mode,
                    proposed_payload=proposed_payload,
                    loop_step_number=loop_step_number,
                )
            except ScopeBlocked as exc:
                return AgentResult(
                    agent_name=agent_name,
                    status="error",
                    error_message=format_scope_error(exc.blocked),
                    category=get_agent_category(agent_name),
                    emoji=get_agent_emoji(agent_name),
                )
            preview = aw.preview
            action_id = aw.action_id
            normalized_sources = aw.normalized_sources

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
                    # ``intent_type`` (not ``impact_type``): the durable-loop
                    # executor reads this key to decide undoability and to record
                    # created IDs.  ``proposed_payload`` carries the persisted
                    # write body so the loop's execute pass sends the intended
                    # payload instead of an empty dict.
                    "intent_type": intent.intent_type,
                    "target_object": intent.target_object,
                    "impact_count": preview.impact_count,
                    "original_values": preview.original_values,
                    "proposed_payload": aw.preview_data.get("proposed_payload", {}),
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

        # No execute handler registered for this agent.  Previously this
        # fabricated ``status="success"`` with a fake message — a write that
        # never happened would be reported as done, and (on the approve path)
        # an undo snapshot would reference a mutation that never occurred.
        # Return an error instead so a handler-less agent can never masquerade
        # as a completed write.  (Handler-less agents are all read-only:
        # analytics, forecasts, audit_logs, etc.; a plan that routes a write to
        # one is rejected at plan-validation time in ``validate_plan``.)
        return AgentResult(
            agent_name=agent_name,
            status="error",
            error_message=(
                f"Agent '{agent_name}' has no execute handler; it cannot perform writes. "
                f"This agent is read-only."
            ),
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


def _format_loop_result(
    portal_config,
    state: loop_state.LoopState,
    final_message: str,
) -> str:
    """Render the final loop result for the user."""
    summary_lines = [
        f"📍 Portal: {portal_config.portal_id} ({portal_config.tier})",
        f"**Goal:** {state.plan.goal}",
        "",
        f"**Status:** {state.status}",
        "",
        "### Plan executed",
        plan_to_markdown(state.plan),
        "",
        "### Artifacts",
    ]
    for artifact in state.artifacts:
        summary_lines.append(f"- Step {artifact.step_number} ({artifact.agent}): {artifact.outputs}")
        if artifact.warnings:
            summary_lines.append(f"  - warnings: {artifact.warnings}")
    summary_lines.extend(["", final_message])
    return "\n".join(summary_lines)


# ---------------------------------------------------------------------------
# Durable loop: deferred-approval state machine
#
# The loop plans (Claude, in-session), executes deterministically (Python),
# pauses at each write for a real ``approve``, resumes on ``loop continue``, and
# verifies with a Claude-supplied verdict.  Statuses:
#
#   running               actively driving; between CLI calls this means
#                          "ready to drive the next step".
#   awaiting_approval      paused at a write step; ``pending_action_id`` names
#                          the preview the human must ``approve``.  Exempt from
#                          the staleness reaper (loop_state.is_stale).
#   awaiting_verification  a write executed; waiting for Claude to re-read the
#                          records and supply a VerificationResult via
#                          ``loop verify``.  Also staleness-exempt.
#   stopped                a proxy budget (max_steps / max_api_calls) was
#                          exhausted mid-run; terminal, halted for review.
#   completed/failed/escalate/stop   terminal; cleared or halted.
#
# The safety-critical execute path (handlers.execute_pending_write, run by
# ``hubspot approve``) stays fully decoupled from this orchestrator — resume
# reads only the persisted pending record, undo snapshot, and audit log.
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = frozenset({"completed", "failed", "escalate", "stop", "stopped"})

# A step needs a HITL pause if it is a write by action-verb OR the plan marked
# it medium/high/destructive risk.  Keying on risk too closes the gap where a
# destructive step phrased with a verb outside ``is_write_step``'s set (e.g.
# "purge"/"archive"/"deactivate"/"remove") would otherwise be treated as a read
# and executed with no approval.  Fail safe: an over-cautious pause on a
# misclassified read is harmless; skipping approval on a real write is not.
_APPROVAL_RISK_LEVELS = frozenset({RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.DESTRUCTIVE})


def _requires_approval(step) -> bool:
    return is_write_step(step) or step.risk_level in _APPROVAL_RISK_LEVELS


def _loop_header(portal_config) -> str:
    return f"📍 Portal: {portal_config.portal_id} ({portal_config.tier})"


def _needs_plan_message(portal_config) -> str:
    return (
        f"{_loop_header(portal_config)}\n\n"
        "This request needs a plan before the durable loop can run. "
        "Produce a `LoopPlan` JSON for the goal, then start the loop with:\n\n"
        "```\n"
        "hubspot loop start --plan '<LoopPlan JSON>'\n"
        "```"
    )


def _format_pause_message(portal_config, state: loop_state.LoopState, preview: AgentResult) -> str:
    step = state.plan.steps[state.current_step]
    data = preview.data
    action_id = data.get("action_id")
    risk = data.get("risk_level", "unknown")
    impact = data.get("impact_count", "unknown")
    lines = [
        _loop_header(portal_config),
        f"**Goal:** {state.plan.goal}",
        "",
        f"⏸️  Loop paused at step {step.step_number} of {len(state.plan.steps)} "
        f"({step.agent}) — approval required before this write.",
        "",
        f"⚠️  Preview (action: {action_id})",
        f"Risk: {risk}  ·  Impact: {impact} record(s)",
    ]
    preview_text = data.get("preview")
    if preview_text:
        lines.append(str(preview_text))
    approve_cmd = (
        f"hubspot approve {action_id} {impact}"
        if risk == RiskLevel.DESTRUCTIVE.value
        else f"hubspot approve {action_id}"
    )
    lines.extend([
        "",
        "To continue the loop:",
        f"1. `{approve_cmd}`  (or reject with `hubspot reject {action_id}`)",
        "2. `hubspot loop continue`",
    ])
    return "\n".join(lines)


def _prompt_for_verification_message(portal_config, state: loop_state.LoopState) -> str:
    step = state.plan.steps[state.current_step]
    return (
        f"{_loop_header(portal_config)}\n\n"
        f"✅ Step {step.step_number} ({step.agent}) executed. "
        "Re-read the affected record(s) to confirm the change landed, then report the result:\n\n"
        "```\n"
        "hubspot loop verify --result '<VerificationResult JSON>'\n"
        "```"
    )


def _artifact_from_snapshot(portal_id: str, action_id: str, step) -> StepArtifact:
    """Build a StepArtifact for a write that executed out-of-band via ``approve``.

    Reads the undo snapshot (written by ``execute_pending_write``) for the
    created IDs and target object; the loop never re-touches the execute path.
    """
    snapshot = load_undo_snapshot(snapshot_dir_for_portal(portal_id), action_id) or {}
    metadata = snapshot.get("metadata", {}) if isinstance(snapshot, dict) else {}
    created_ids = [str(c) for c in metadata.get("created_ids", []) if c]

    outputs: dict[str, Any] = {}
    if created_ids:
        outputs["created_ids"] = list(created_ids)
        # Surface the first created id under the step's declared artifact key
        # (e.g. ``property_id``) so downstream steps can resolve it.
        for key in step.expected_artifact_keys:
            outputs[key] = created_ids[0]
            break
    return StepArtifact(
        step_number=step.step_number,
        agent=step.agent,
        outputs=outputs,
        created_ids=created_ids,
    )


_PLACEHOLDER_RE = re.compile(r"^\s*\{\{\s*(\w+)\s*\}\}\s*$")


def _resolve_tool_placeholders(tool_input: Any, resolved: dict[str, Any]) -> Any:
    """Substitute ``{{key}}`` placeholders in ``tool_input`` from artifact outputs.

    Whole-value substitution only (``object_id: "{{contact_id}}"``): a string
    that is exactly ``{{key}}`` is replaced by ``resolved[key]``.  Dicts and
    lists are recursed.  Raises ``KeyError(key)`` for a placeholder whose key is
    not in ``resolved`` so the caller fails the step before any write persists.
    """
    if isinstance(tool_input, dict):
        return {k: _resolve_tool_placeholders(v, resolved) for k, v in tool_input.items()}
    if isinstance(tool_input, list):
        return [_resolve_tool_placeholders(v, resolved) for v in tool_input]
    if isinstance(tool_input, str):
        match = _PLACEHOLDER_RE.match(tool_input)
        if match:
            key = match.group(1)
            if key not in resolved:
                raise KeyError(key)
            return resolved[key]
    return tool_input


def _capture_tool_artifact(data: dict[str, Any], step) -> StepArtifact:
    """Build a StepArtifact from an inline-executed read tool's response.

    ``data`` is ``handle_tool``'s ``{"tool": ..., "result": ...}``.  The raw
    result is captured under ``"result"``; if it carries a record id and the
    step declared ``expected_artifact_keys``, the first id is surfaced under
    that key so downstream ``{{key}}`` placeholders can resolve it.  Reads never
    create records, so ``created_ids`` stays empty (the create-escalate guard in
    ``loop_verify`` keys off ``created_ids`` and must not fire for a read).
    """
    result = data.get("result")
    outputs: dict[str, Any] = {"result": result}
    first_id: str | None = None
    if isinstance(result, list):
        for rec in result:
            if isinstance(rec, dict) and rec.get("id"):
                first_id = str(rec["id"])
                break
    elif isinstance(result, dict) and result.get("id"):
        first_id = str(result["id"])
    if first_id and step.expected_artifact_keys:
        for key in step.expected_artifact_keys:
            outputs[key] = first_id
            break
    return StepArtifact(
        step_number=step.step_number,
        agent=step.agent,
        outputs=outputs,
        created_ids=[],
    )


async def _run_loop_tool_step(
    portal_config, state: loop_state.LoopState, step, tool_input: dict[str, Any]
) -> dict[str, Any]:
    """Execute one verbatim-tool loop step via ``handle_tool``.

    Returns one of:
    - ``{"kind": "preview", "action_id", "preview"}`` — write tool paused at
      approval; the pending record carries ``tool_name`` and the verbatim
      ``tool_input`` so ``execute_pending_write``'s tool branch replays it
      exactly (no fuzzy ``records[0]`` re-search).
    - ``{"kind": "read", "artifact"}`` — read tool executed inline.
    - ``{"kind": "failed", "error"}`` — a handler/preview failure.
    """
    from hubspot_agent.handlers import HandlerError, build_fresh_client_cache, handle_tool

    client, cache = await build_fresh_client_cache(portal_config)
    try:
        params = {
            "tool_name": step.tool_name,
            "input": tool_input,
            "trace_id": state.trace_id,
            "loop_step_number": step.step_number,
            "batch_mode": "single",
        }
        try:
            resp = await handle_tool(client, cache, portal_config, params)
        except HandlerError as exc:
            # A retryable handler error (transient server/rate blip on a
            # read/preview build) is re-raised so the loop's per-step retry
            # budget can back off and re-run the whole step.  A terminal error
            # still returns the fail outcome for immediate fail-and-stop.
            if exc.error.get("retryable"):
                raise
            return {"kind": "failed", "error": exc.error.get("message", "tool call failed")}
        data = resp.get("data", {})
        if data.get("status") == "preview":
            preview = AgentResult(
                agent_name=step.agent,
                status="preview",
                data={
                    "action_id": data.get("action_id"),
                    "risk_level": data.get("risk_level", "medium"),
                    "impact_count": data.get("impact_count", 1),
                    "preview": f"Tool {step.tool_name} — preview of the verbatim payload.",
                    "target_object": tool_input.get("object_type"),
                },
            )
            return {"kind": "preview", "action_id": data["action_id"], "preview": preview}
        artifact = _capture_tool_artifact(data, step)
        return {"kind": "read", "artifact": artifact}
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Back-pressure (Phase 3 PR-B): per-step retry with backoff + proactive pacing.
#
# ONLY read/preview execution is retried/paced — the write mutation happens
# out-of-band at ``hubspot approve`` (execute_pending_write), which _drive_loop
# never touches.  A write step still pauses at ``awaiting_approval``; it is
# never auto-retried.
# ---------------------------------------------------------------------------

# Total attempts for a transient read/preview step (1 initial + retries).
_READ_RETRY_BUDGET = 3
# Cap on any single backoff/pacing sleep — reuse the client's Retry-After cap so
# a misconfigured server signal cannot hang the loop.
_BACKPRESSURE_CAP_SECONDS = HubSpotClient._MAX_RETRY_AFTER_SECONDS
# Pace before the next step once the server says this few requests remain in the
# current interval.  A small constant (the parse helper does not surface the
# interval max), erring toward pacing early.
_RATE_LIMIT_LOW_WATERMARK = 10


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


# Indirection so tests can spy on / stub the sleep without real waits.  Resolved
# by module-global name at call time, so ``monkeypatch.setattr`` on this symbol
# takes effect inside the helpers below.
_sleep = _default_sleep


def _is_transient_error(exc: BaseException) -> bool:
    """Classify an exception raised by a read/preview step as transient.

    Transient (worth retrying): rate limits, HubSpot 5xx, network/timeout
    faults, and handler/execute errors explicitly flagged ``retryable``.
    Everything else (validation, not-found, scope, auth, unexpected) is terminal
    and fails the step immediately, as today.
    """
    from hubspot_agent.handlers import ExecuteError, HandlerError

    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, HubSpotError):
        return exc.status_code is not None and exc.status_code >= 500
    if isinstance(exc, ExecuteError):
        return exc.retryable
    if isinstance(exc, HandlerError):
        return bool(exc.error.get("retryable"))
    if isinstance(exc, httpx.TransportError):
        # Covers timeouts, connect/read errors, and other transport faults.
        return True
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    return False


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Server-suggested backoff for a transient error, if any."""
    from hubspot_agent.handlers import HandlerError

    if isinstance(exc, RateLimitError):
        return float(exc.retry_after) if exc.retry_after is not None else None
    if isinstance(exc, HandlerError):
        ra = exc.error.get("retry_after")
        return float(ra) if ra is not None else None
    return None


async def _execute_read_step_with_retry(coro_factory, portal_id: str, trace_id: str, step_number: int):
    """Run a read/preview step coroutine, retrying transient failures.

    ``coro_factory`` is a zero-arg callable returning a fresh awaitable per
    attempt (each attempt builds its own client).  Retries up to
    ``_READ_RETRY_BUDGET`` total attempts with exponential backoff, honoring a
    server ``Retry-After``/``retry_after`` when present (capped).  A terminal
    (non-transient) error raises immediately.  After the budget is exhausted the
    last transient error is re-raised so the caller falls through to the
    existing fail-and-stop.  NEVER used for the write-approval path.
    """
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except Exception as exc:
            if not _is_transient_error(exc) or attempt >= _READ_RETRY_BUDGET - 1:
                raise
            attempt += 1
            server_backoff = _retry_after_seconds(exc)
            if server_backoff is not None:
                delay = min(server_backoff, _BACKPRESSURE_CAP_SECONDS)
            else:
                delay = min(2.0 ** (attempt - 1), _BACKPRESSURE_CAP_SECONDS)
            loop_log.log_event(portal_id, trace_id, "step_retry", {
                "step_number": step_number,
                "attempt": attempt,
                "error": str(exc),
                "sleep_seconds": delay,
            })
            await _sleep(delay)


def _capture_rate_state(state: loop_state.LoopState, portal_id: str) -> None:
    """Fold the client's last-seen rate signal into the (persisted) loop state."""
    remaining, reset_at = get_last_rate_state(portal_id)
    if remaining is not None:
        state.rate_remaining = remaining
    if reset_at is not None:
        state.rate_reset_at = reset_at


async def _pace_if_needed(state: loop_state.LoopState, portal_id: str) -> None:
    """Sleep before the next step when the server signals low remaining quota.

    Reads the persisted ``rate_remaining``/``rate_reset_at`` (updated after the
    previous step).  Fresh loops (no observed header) never pace.  The sleep is
    bounded by ``_BACKPRESSURE_CAP_SECONDS`` and goes through the injectable
    ``_sleep`` so tests assert the decision without waiting.
    """
    remaining = state.rate_remaining
    reset_at = state.rate_reset_at
    if remaining is None or remaining > _RATE_LIMIT_LOW_WATERMARK or reset_at is None:
        return
    sleep_for = min(max(reset_at - time.time(), 0.0), _BACKPRESSURE_CAP_SECONDS)
    if sleep_for <= 0:
        return
    loop_log.log_event(portal_id, state.trace_id, "paced", {
        "remaining": remaining,
        "sleep_seconds": sleep_for,
    })
    await _sleep(sleep_for)


async def _drive_loop(portal_config, state: loop_state.LoopState, working_dir: str) -> str:
    """Advance the loop from ``current_step`` until a write pause or completion.

    Read steps execute immediately (no approval).  A write step builds a
    preview, persists a pending action, parks the loop at ``awaiting_approval``,
    and returns — nothing is mutated until the human runs ``hubspot approve``.
    """
    portal_id = portal_config.portal_id
    plan = state.plan

    while state.current_step < len(plan.steps):
        # Proxy-budget back-pressure (Phase 3 PR-A): hard-stop a runaway loop
        # BEFORE executing another step — enforced per-step, not only at the
        # post-write verify checkpoint.  A missing budget field defaults (never
        # "unlimited"), so this always fires.
        if state.step_count >= plan.max_steps or state.api_call_count >= plan.max_api_calls:
            which = "max_steps" if state.step_count >= plan.max_steps else "max_api_calls"
            state.status = "stopped"
            state.last_error = f"budget exhausted: {which}"
            loop_state.save(state)
            loop_log.log_event(portal_id, state.trace_id, "budget_exhausted", {
                "which": which,
                "step_count": state.step_count,
                "api_call_count": state.api_call_count,
                "max_steps": plan.max_steps,
                "max_api_calls": plan.max_api_calls,
            })
            return _format_loop_result(
                portal_config,
                state,
                f"Loop stopped: proxy budget exhausted ({which}).",
            )

        # Back-pressure pacing (PR-B): if the previous step's response said the
        # rate-limit interval is nearly spent, sleep until it resets before
        # issuing the next step's reads.  No-op on a fresh loop (no header yet).
        await _pace_if_needed(state, portal_id)

        step = plan.steps[state.current_step]
        # Count this step against the proxy budget.  The loop makes no LLM
        # calls, so api_call_count is an approximation: +1 per executed step
        # (each step issues >=1 HubSpot request via its handler/agent).  A write
        # step is counted once here on the pause iteration and is not re-entered
        # on approve→continue, so it is not double-counted.
        state.step_count += 1
        state.api_call_count += 1
        resolved = _resolve_artifacts(step, {a.step_number: a for a in state.artifacts})
        step_request = _build_step_request(step, state.request_text, resolved)
        loop_log.log_event(portal_id, state.trace_id, "step_started", {
            "step_number": step.step_number,
            "agent": step.agent,
            "action": step.action,
        })

        # Safety invariant (scheduled runs never mutate unattended): a scheduled
        # plan MUST be fully concrete — every step carries ``tool_name`` and runs
        # the verbatim-tool branch below, which stages writes as pending previews.
        # The free-text agent branches (preview-pause and, critically, the
        # ``mode="execute"`` low-risk branch) can classify a step as a read via
        # ``is_write_step`` yet execute it as a write via ``_parse_agent_intent``
        # — an unattended mutation with no approval.  Refuse to run a free-text
        # step in scheduled mode rather than reach that path.  (schedule ``add``
        # rejects non-concrete plans up front; this is defense-in-depth.)
        if state.run_mode == "scheduled" and step.tool_name is None:
            state.status = "failed"
            state.last_error = (
                f"Scheduled plans must be concrete tool-path plans; step "
                f"{step.step_number} has no tool_name. Free-text agent steps "
                f"are refused unattended (they could mutate without approval)."
            )
            loop_state.save(state)
            loop_log.log_event(portal_id, state.trace_id, "step_failed", {
                "step_number": step.step_number,
                "error": state.last_error,
            })
            return _format_loop_result(
                portal_config,
                state,
                f"Execution stopped at step {step.step_number}: {state.last_error}",
            )

        # Verbatim tool path (PR 2 / bug 2): a step with ``tool_name`` executes
        # the exact ``tool_input`` through ``handle_tool`` instead of free-text
        # agent dispatch, so a write lands on the named record — never a fuzzy
        # ``records[0]``.  Placeholder resolution failures and handler/preview
        # errors fail the step without persisting a pending write.
        if step.tool_name is not None:
            try:
                resolved_input = _resolve_tool_placeholders(step.tool_input, resolved)
            except KeyError as missing:
                state.status = "failed"
                state.last_error = (
                    f"Unresolvable placeholder {{{{{missing}}}}} in step "
                    f"{step.step_number} tool_input (no artifact supplies it)."
                )
                loop_state.save(state)
                loop_log.log_event(portal_id, state.trace_id, "step_failed", {
                    "step_number": step.step_number,
                    "error": state.last_error,
                })
                return _format_loop_result(
                    portal_config,
                    state,
                    f"Execution stopped at step {step.step_number}: {state.last_error}",
                )

            try:
                outcome = await _execute_read_step_with_retry(
                    lambda: _run_loop_tool_step(portal_config, state, step, resolved_input),
                    portal_id, state.trace_id, step.step_number,
                )
            except Exception as exc:
                # Transient budget exhausted, or a terminal error while building
                # the tool preview / running the read tool → fail-and-stop.  No
                # write was persisted, so nothing to roll back.
                state.status = "failed"
                state.last_error = str(exc)
                loop_state.save(state)
                loop_log.log_event(portal_id, state.trace_id, "step_failed", {
                    "step_number": step.step_number,
                    "error": state.last_error,
                })
                return _format_loop_result(
                    portal_config,
                    state,
                    f"Execution stopped at step {step.step_number}: {state.last_error}",
                )
            if outcome["kind"] == "failed":
                state.status = "failed"
                state.last_error = outcome["error"]
                loop_state.save(state)
                loop_log.log_event(portal_id, state.trace_id, "step_failed", {
                    "step_number": step.step_number,
                    "error": outcome["error"],
                })
                return _format_loop_result(
                    portal_config,
                    state,
                    f"Execution stopped at step {step.step_number}: {outcome['error']}",
                )
            if outcome["kind"] == "preview":
                _capture_rate_state(state, portal_id)
                if state.run_mode == "scheduled":
                    state.staged_action_ids.append(outcome["action_id"])
                    state.current_step += 1
                    loop_state.save(state)
                    loop_log.log_event(portal_id, state.trace_id, "write_staged", {
                        "step_number": step.step_number,
                        "action_id": outcome["action_id"],
                    })
                    continue
                state.pending_action_id = outcome["action_id"]
                state.status = "awaiting_approval"
                loop_state.save(state)
                loop_log.log_event(portal_id, state.trace_id, "awaiting_approval", {
                    "step_number": step.step_number,
                    "action_id": state.pending_action_id,
                })
                return _format_pause_message(portal_config, state, outcome["preview"])
            # Read tool executed inline → capture artifact, advance, continue.
            artifact = outcome["artifact"]
            state.artifacts.append(artifact)
            _capture_rate_state(state, portal_id)
            state.current_step += 1
            loop_state.save(state)
            loop_log.log_event(portal_id, state.trace_id, "step_completed", {
                "step_number": step.step_number,
                "outputs": artifact.outputs,
            })
            continue

        if _requires_approval(step):
            # Retry only the PREVIEW build (a read) on a transient blip.  The
            # write itself is never executed here — it pauses for approval.
            try:
                preview = await _execute_read_step_with_retry(
                    lambda: dispatch_agent(
                        step.agent,
                        step_request,
                        portal_config,
                        mode="preview",
                        trace_id=state.trace_id,
                        loop_step_number=step.step_number,
                    ),
                    portal_id, state.trace_id, step.step_number,
                )
            except Exception as exc:
                state.status = "failed"
                state.last_error = str(exc)
                loop_state.save(state)
                loop_log.log_event(portal_id, state.trace_id, "step_failed", {
                    "step_number": step.step_number,
                    "error": state.last_error,
                })
                return _format_loop_result(
                    portal_config,
                    state,
                    f"Execution stopped at step {step.step_number}: {state.last_error}",
                )
            if preview.status == "error":
                state.status = "failed"
                state.last_error = preview.error_message
                loop_state.save(state)
                loop_log.log_event(portal_id, state.trace_id, "step_failed", {
                    "step_number": step.step_number,
                    "error": preview.error_message,
                })
                return _format_loop_result(
                    portal_config,
                    state,
                    f"Execution stopped at step {step.step_number}: {preview.error_message}",
                )
            _capture_rate_state(state, portal_id)
            action_id = preview.data.get("action_id")
            if state.run_mode == "scheduled":
                state.staged_action_ids.append(action_id)
                state.current_step += 1
                loop_state.save(state)
                loop_log.log_event(portal_id, state.trace_id, "write_staged", {
                    "step_number": step.step_number,
                    "action_id": action_id,
                })
                continue
            state.pending_action_id = action_id
            state.status = "awaiting_approval"
            loop_state.save(state)
            loop_log.log_event(portal_id, state.trace_id, "awaiting_approval", {
                "step_number": step.step_number,
                "action_id": state.pending_action_id,
            })
            return _format_pause_message(portal_config, state, preview)

        # Low-risk read step (no write verb, low/no risk): execute directly,
        # capture the artifact, advance — no approval needed.  Retry a transient
        # blip; a terminal error (or exhausted budget) fails-and-stops.
        try:
            result = await _execute_read_step_with_retry(
                lambda: dispatch_agent(
                    step.agent,
                    step_request,
                    portal_config,
                    mode="execute",
                    trace_id=state.trace_id,
                ),
                portal_id, state.trace_id, step.step_number,
            )
        except Exception as exc:
            state.status = "failed"
            state.last_error = str(exc)
            loop_state.save(state)
            loop_log.log_event(portal_id, state.trace_id, "step_failed", {
                "step_number": step.step_number,
                "error": state.last_error,
            })
            return _format_loop_result(
                portal_config,
                state,
                f"Execution stopped at step {step.step_number}: {state.last_error}",
            )
        if result.status == "error":
            state.status = "failed"
            state.last_error = result.error_message
            loop_state.save(state)
            loop_log.log_event(portal_id, state.trace_id, "step_failed", {
                "step_number": step.step_number,
                "error": result.error_message,
            })
            return _format_loop_result(
                portal_config,
                state,
                f"Execution stopped at step {step.step_number}: {result.error_message}",
            )
        artifact = _capture_artifacts(result, step)
        state.artifacts.append(artifact)
        _capture_rate_state(state, portal_id)
        state.current_step += 1
        loop_state.save(state)
        loop_log.log_event(portal_id, state.trace_id, "step_completed", {
            "step_number": step.step_number,
            "outputs": artifact.outputs,
        })

    state.status = "completed"
    loop_state.save(state)
    loop_log.log_event(portal_id, state.trace_id, "loop_completed", {
        "iterations": state.iterations,
        "steps_completed": state.current_step,
    })
    result = _format_loop_result(portal_config, state, "Loop completed successfully.")
    if state.run_mode == "scheduled":
        loop_state.clear_run(state)
    else:
        loop_state.clear(portal_id)
    return result


async def _resume_awaiting_approval(portal_config, state: loop_state.LoopState, working_dir: str) -> str:
    """Resume a loop parked at a write step, disambiguating the pending action.

    Reads only shared artifacts (pending record, audit log, undo snapshot) — no
    coupling to the execute path:

    - pending still on disk  → still awaiting → re-emit the ``approve`` prompt.
    - pending gone + audit has ``approve:<id>`` → executed → capture artifact,
      move to ``awaiting_verification``.
    - pending gone + no approve entry → rejected/cancelled → stop the loop.
    """
    portal_id = portal_config.portal_id
    action_id = state.pending_action_id
    step = state.plan.steps[state.current_step]

    if action_id and _load_pending_preview(portal_id, action_id) is not None:
        return (
            f"{_loop_header(portal_config)}\n\n"
            f"⏸️  Step {step.step_number} ({step.agent}) is still awaiting approval. "
            f"Run `hubspot approve {action_id}` (then `hubspot loop continue`), "
            f"or `hubspot reject {action_id}` to stop the loop."
        )

    audits = audit.get_recent_audits(portal_id, limit=200)
    approved = any(a.get("action") == f"approve:{action_id}" for a in audits)

    if approved:
        artifact = _artifact_from_snapshot(portal_id, action_id, step)
        # Replace any prior artifact for this step (e.g. from a retry) so the
        # step_number keying stays 1:1.
        state.artifacts = [a for a in state.artifacts if a.step_number != step.step_number]
        state.artifacts.append(artifact)
        state.status = "awaiting_verification"
        loop_state.save(state)
        loop_log.log_event(portal_id, state.trace_id, "write_executed", {
            "step_number": step.step_number,
            "action_id": action_id,
            "created_ids": artifact.created_ids,
        })
        return _prompt_for_verification_message(portal_config, state)

    # Pending gone and never approved → treat as rejected/cancelled.
    state.status = "stop"
    loop_state.save(state)
    loop_log.log_event(portal_id, state.trace_id, "write_rejected", {
        "step_number": step.step_number,
        "action_id": action_id,
    })
    return _format_loop_result(
        portal_config,
        state,
        f"Loop stopped: the pending write for step {step.step_number} was rejected or cancelled.",
    )


async def _drive_loop_guarded(portal_config, state: loop_state.LoopState, working_dir: str) -> str:
    """Fail-safe wrapper around ``_drive_loop``.

    The tool layer returns error dicts rather than raising, so ``_drive_loop``
    handles expected failures itself — but an unexpected raise (pydantic,
    artifact resolution, disk) must not leave the on-disk state parked as
    ``running``, where the next ``loop continue`` would resume straight into
    the same crash.  Park it as ``failed`` with the error recorded instead.
    """
    try:
        return await _drive_loop(portal_config, state, working_dir)
    except Exception as exc:
        state.status = "failed"
        state.last_error = str(exc)
        loop_state.save(state)
        loop_log.log_event(state.portal_id, state.trace_id, "loop_crashed", {"error": str(exc)})
        return _format_loop_result(portal_config, state, f"Loop crashed: {exc}")


async def run_loop(
    request_text: str,
    portal_config,
    working_dir: str,
    trace_id: str,
    plan: LoopPlan | None = None,
) -> str:
    """Run or resume the durable loop.

    - With an existing non-terminal ``LoopState``: resume it (drive, or handle a
      pending approval / awaiting verification).
    - With a Claude-supplied ``plan`` and no existing state: validate, persist a
      fresh ``LoopState``, and drive until the first write pause or completion.
    - With neither: return guidance to produce a plan and run ``loop start``.

    Writes never execute here — a write step pauses at ``awaiting_approval`` and
    is applied out-of-band by ``hubspot approve`` (the unchanged safety path).
    """
    portal_id = portal_config.portal_id
    existing_state = loop_state.load(portal_id)

    if existing_state is not None:
        if existing_state.status in _TERMINAL_STATUSES or loop_state.is_stale(existing_state):
            loop_state.clear(portal_id)
            existing_state = None

    if existing_state is not None:
        state = existing_state
        if state.status == "awaiting_approval":
            return await _resume_awaiting_approval(portal_config, state, working_dir)
        if state.status == "awaiting_verification":
            return _prompt_for_verification_message(portal_config, state)
        loop_log.log_event(portal_id, state.trace_id, "loop_resumed", {
            "current_step": state.current_step,
            "iterations": state.iterations,
        })
        return await _drive_loop_guarded(portal_config, state, working_dir)

    # No existing loop — a plan is required (Claude does triage, not Python).
    if plan is None:
        return _needs_plan_message(portal_config)

    validation_errors = validate_plan(plan, _build_loop_capability_matrix(portal_config))
    if validation_errors:
        return (
            f"{_loop_header(portal_config)}\n\n"
            "The plan cannot be executed:\n"
            + "\n".join(f"- {e}" for e in validation_errors)
            + "\n\nAdjust the plan or upgrade the portal capabilities."
        )

    state = loop_state.LoopState(
        portal_id=portal_id,
        request_text=request_text or plan.goal,
        trace_id=trace_id,
        plan=plan,
    )
    loop_log.log_event(portal_id, trace_id, "loop_started", {
        "goal": plan.goal,
        "step_count": len(plan.steps),
    })
    return await _drive_loop_guarded(portal_config, state, working_dir)


async def run_scheduled_due(portal_config, working_dir: str, *, now: datetime | None = None) -> str:
    """Timer entry point (Phase 4): run every schedule that is due, staging writes.

    For each stored schedule, in order:
      1. Overlap/expiry gate — if the prior batch is still ``running``/``pending``,
         expire it once older than ``schedule_queue_ttl_days`` (clear its queued
         previews, mark ``expired`` → eligible again) or else SKIP this fire.
      2. Due gate — ``cron.is_due(cron, last_run_at, now)``; not due → skip.
      3. Run — replay the stored plan through ``_drive_loop`` in scheduled mode
         (reads inline, every write staged as a pending preview, nothing mutated),
         stamp each staged preview with its schedule provenance, and record the
         batch (``pending`` if writes queued, else ``done``).

    No Claude / no LLM at run time; the plan is replayed deterministically.  Each
    schedule is isolated in try/except so one failure never aborts the sweep.
    """
    portal_id = portal_config.portal_id
    now = now or datetime.now(timezone.utc)
    ttl_days = load_approval_policy(portal_id).schedule_queue_ttl_days

    results: list[str] = []
    for schedule in schedule_store.list_schedules(portal_id):
        trace_id = new_trace_id()
        try:
            results.append(
                await _run_one_schedule(portal_config, schedule, now, ttl_days, trace_id, working_dir)
            )
        except Exception as exc:  # one schedule's failure must not abort the sweep
            schedule_store.set_last_batch(portal_id, schedule.id, {
                "run_at": now.isoformat(),
                "status": "failed",
                "pending_action_ids": [],
                "summary": f"run failed: {exc}",
            })
            loop_log.log_event(portal_id, trace_id, "schedule_failed", {
                "schedule_id": schedule.id,
                "error": str(exc),
            })
            results.append(f'- "{schedule.name}" ({schedule.id}): failed — {exc}')

    if not results:
        return f"No schedules registered for portal {portal_id}."
    return f"Scheduled sweep @ {now.isoformat()}:\n" + "\n".join(results)


async def _run_one_schedule(portal_config, schedule, now: datetime, ttl_days: int, trace_id: str, working_dir: str) -> str:
    """Evaluate one schedule's gates and run it if due.  Returns a summary line."""
    portal_id = portal_config.portal_id
    name, sid = schedule.name, schedule.id

    # 1. Overlap / expiry gate.
    #
    # "Still pending" is derived from disk, NOT the stored status string: a
    # queued preview that the operator has approved or rejected no longer exists
    # (the approve/reject path clears it and never touches ``last_batch``).  So a
    # daily schedule un-freezes as soon as its batch is resolved — we only skip
    # while previews genuinely remain unapproved, and only until the queue TTL.
    last_batch = schedule.last_batch
    if last_batch and last_batch.get("status") in ("running", "pending"):
        batch_ids = last_batch.get("pending_action_ids") or []
        still_pending = [aid for aid in batch_ids if _load_pending_preview(portal_id, aid) is not None]
        if still_pending:
            run_at_s = last_batch.get("run_at")
            expired = True
            if run_at_s:
                expired = (now - datetime.fromisoformat(run_at_s)) >= timedelta(days=ttl_days)
            if not expired:
                loop_log.log_event(portal_id, trace_id, "schedule_skipped", {
                    "schedule_id": sid,
                    "reason": "prior batch pending",
                    "remaining": len(still_pending),
                })
                return f'- "{name}" ({sid}): skipped (prior batch pending, {len(still_pending)} unreviewed)'
            # TTL exceeded: drop the still-queued previews, mark expired → eligible.
            for aid in still_pending:
                _clear_pending_preview(portal_id, aid)
            schedule_store.set_last_batch(portal_id, sid, {**last_batch, "status": "expired"})
            loop_log.log_event(portal_id, trace_id, "batch_expired", {
                "schedule_id": sid,
                "cleared": len(still_pending),
            })
        # else: every queued preview was approved/rejected — the batch is
        # resolved; fall through to the due gate so the schedule runs normally.

    # 2. Due gate.
    if not cron.is_due(schedule.cron, schedule.last_run_at, now):
        return f'- "{name}" ({sid}): skipped (not due)'

    # 3. Run — mark the batch running, replay the stored plan in scheduled mode.
    schedule_store.set_last_batch(portal_id, sid, {
        "run_at": now.isoformat(),
        "status": "running",
        "pending_action_ids": [],
    })
    state = loop_state.LoopState(
        portal_id=portal_id,
        request_text=name,
        trace_id=trace_id,
        plan=LoopPlan.model_validate(schedule.plan),
        run_mode="scheduled",
        state_key=sid,
    )
    loop_log.log_event(portal_id, trace_id, "schedule_run_started", {
        "schedule_id": sid,
        "step_count": len(state.plan.steps),
    })
    await _drive_loop(portal_config, state, working_dir)
    staged = list(state.staged_action_ids)

    # Provenance: stamp each staged preview so approval + status can attribute it.
    for aid in staged:
        preview_data = _load_pending_preview(portal_id, aid)
        if preview_data is None:
            continue
        preview_data["origin"] = {
            "schedule_id": sid,
            "schedule_name": name,
            "run_at": now.isoformat(),
        }
        _store_pending_preview(portal_id, aid, preview_data)

    # Record the batch outcome and advance the schedule's clock.
    summary = f"{len(staged)} write(s) staged" if staged else "nothing to stage"
    schedule_store.set_last_batch(portal_id, sid, {
        "run_at": now.isoformat(),
        "status": "pending" if staged else "done",
        "pending_action_ids": staged,
        "summary": summary,
    })
    schedule_store.set_last_run(portal_id, sid, now)
    loop_state.clear_run(state)
    loop_log.log_event(portal_id, trace_id, "schedule_run_completed", {
        "schedule_id": sid,
        "staged": len(staged),
        "loop_status": state.status,
    })
    return f'- "{name}" ({sid}): ran, {summary}'


async def loop_verify(
    result_json: str,
    portal_config,
    working_dir: str,
) -> str:
    """Consume a Claude-supplied VerificationResult for a paused-after-write loop.

    Feeds the verdict to ``LoopController.next_action``:
    - proceed  → advance past the verified write and drive to the next pause.
    - retry    → drop the step's artifact, re-drive the same step (re-previews,
      re-pauses for a fresh approval).  Bounded by the controller's iteration /
      plateau / error-budget guards.
    - escalate/stop → halt for human review.
    """
    portal_id = portal_config.portal_id
    state = loop_state.load(portal_id)
    if state is None:
        return "No active loop for this portal."
    if state.status != "awaiting_verification":
        return (
            f"{_loop_header(portal_config)}\n\n"
            f"No write is awaiting verification (loop status: {state.status})."
        )

    verification = parse_verification_result(result_json)
    if verification is None:
        return (
            f"{_loop_header(portal_config)}\n\n"
            "Could not parse the verification result. Provide a VerificationResult JSON "
            "with a `status` of verified / mismatch / partial / error."
        )

    step = state.plan.steps[state.current_step]
    controller = LoopController(
        max_iterations=state.plan.max_iterations,
        verification_plateau=state.plan.verification_plateau,
        error_budget=state.plan.error_budget,
        max_steps=state.plan.max_steps,
        max_api_calls=state.plan.max_api_calls,
    )
    decision = controller.next_action(state, verification=verification)
    loop_log.log_event(portal_id, state.trace_id, "verification", {
        "step_number": step.step_number,
        "decision": decision.action,
        "status": verification.status.value,
        "message": verification.message,
    })

    if decision.action == "proceed":
        state.current_step += 1
        state.status = "running"
        state.pending_action_id = None
        loop_state.save(state)
        return await _drive_loop_guarded(portal_config, state, working_dir)

    if decision.action == "retry":
        # A retry re-drives the same step, which re-previews and (after another
        # approval) re-executes it.  For a step whose committed write CREATED
        # records, re-executing would create duplicates — HubSpot creates are
        # not idempotent.  Escalate for human review instead of silently
        # duplicating.  (Updates/deletes carry no created_ids and re-drive
        # safely.)
        step_artifact = next((a for a in state.artifacts if a.step_number == step.step_number), None)
        if step_artifact and step_artifact.created_ids:
            state.status = "escalate"
            state.pending_action_id = None
            loop_state.save(state)
            loop_log.log_event(portal_id, state.trace_id, "escalate", {
                "step_number": step.step_number,
                "reason": "verification failed after a create; retry would duplicate records",
                "created_ids": step_artifact.created_ids,
            })
            return _format_loop_result(
                portal_config,
                state,
                f"Loop halted: step {step.step_number} created {step_artifact.created_ids} but "
                f"verification failed. Retrying would create duplicate records, so this needs "
                f"human review (fix or undo the created record(s), then start a new loop).",
            )
        controller.record_iteration(state)
        state.artifacts = [a for a in state.artifacts if a.step_number != step.step_number]
        state.status = "running"
        state.pending_action_id = None
        loop_state.save(state)
        loop_log.log_event(portal_id, state.trace_id, "retry", {
            "step_number": step.step_number,
            "reason": decision.reason,
            "iteration": state.iterations,
        })
        return await _drive_loop_guarded(portal_config, state, working_dir)

    # escalate / stop
    state.status = decision.action
    state.pending_action_id = None
    loop_state.save(state)
    return _format_loop_result(portal_config, state, f"Loop halted: {decision.reason}")


# DEAD CODE — NFR-13: flat single-domain dispatch, superseded by the durable
# ``run_loop`` path (cli.py calls run_loop, not run_simple).  Retained
# importable: cli.py imports it and tests/test_orchestrator_loop.py exercises
# it; do not delete.
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
# END DEAD CODE — NFR-13 (run_simple)

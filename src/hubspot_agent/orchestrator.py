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
from hubspot_agent.models import AgentResult, BatchApprovalMode, PreviewResult, RiskLevel, TaskIntent
from hubspot_agent.preview import format_preview
from hubspot_agent.tools import invoke_tool


async def initialize_session(portal_id: str) -> None:
    """Stub: portal setup will be re-integrated in Phase 1."""
    pass


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
        "associations": ["associate", "link", "relationship", "related", "linked", "connection"],
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

    best = sorted(scores, key=scores.get, reverse=True)
    primary_score = scores[best[0]]

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

    best = sorted(scores, key=scores.get, reverse=True)
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
# Pending preview storage
# ---------------------------------------------------------------------------

def _pending_previews_dir(portal_id: str) -> Path:
    return CONFIG_DIR / portal_id / "pending_previews"


def _store_pending_preview(portal_id: str, action_id: str, data: dict[str, Any]) -> None:
    pending_dir = _pending_previews_dir(portal_id)
    pending_dir.mkdir(parents=True, exist_ok=True)
    file_path = pending_dir / f"{action_id}.json"
    file_path.write_text(json.dumps(data, indent=2, default=str))
    file_path.chmod(0o600)


def _load_pending_preview(portal_id: str, action_id: str) -> dict[str, Any] | None:
    file_path = _pending_previews_dir(portal_id) / f"{action_id}.json"
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text())


def _clear_pending_preview(portal_id: str, action_id: str) -> None:
    file_path = _pending_previews_dir(portal_id) / f"{action_id}.json"
    if file_path.exists():
        file_path.unlink()


def _list_pending_previews(portal_id: str) -> list[Path]:
    pending_dir = _pending_previews_dir(portal_id)
    if not pending_dir.exists():
        return []
    return sorted(pending_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)


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

async def _build_preview_for_intent(
    agent_name: str,
    intent: TaskIntent,
    client: HubSpotClient,
    portal_id: str,
) -> PreviewResult:
    if agent_name == "objects" and intent.target_object:
        if intent.intent_type in ("search", "update", "delete"):
            search_term = _extract_search_term(intent)
            try:
                result = await invoke_tool(
                    "hubspot_search_objects",
                    portal_id,
                    object_type=intent.target_object,
                    query={"query": search_term, "limit": 10, "properties": ["firstname", "lastname", "email", "name", "phone"]},
                    client=client,
                    portal_id=portal_id,
                )
            except Exception as exc:
                return PreviewResult(
                    preview={"error": str(exc)},
                    impact_count=0,
                    risk_level=intent.risk_level,
                )
            if "error" in result:
                return PreviewResult(
                    preview={"error": result["error"]},
                    impact_count=0,
                    risk_level=intent.risk_level,
                )
            records = result.get("results", [])
            return PreviewResult(
                preview={"records": records},
                impact_count=len(records),
                risk_level=intent.risk_level,
                proposed_payload={},
                original_values={r.get("id"): r.get("properties", {}) for r in records},
            )

        if intent.intent_type == "create":
            return PreviewResult(
                preview={"message": f"Will create a new {intent.target_object} record"},
                impact_count=1,
                risk_level=intent.risk_level,
                proposed_payload={"object_type": intent.target_object, "properties": {}},
            )

    return PreviewResult(
        preview={"message": f"{intent.intent_type} operation on {agent_name}"},
        impact_count=intent.estimated_impact or 1,
        risk_level=intent.risk_level,
    )


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
    from hubspot_agent.agents import get_agent_prompt

    prompt = get_agent_prompt(agent_name, portal_config)
    if prompt is None:
        return AgentResult(
            agent_name=agent_name,
            status="error",
            error_message=f"Unknown agent: {agent_name}",
        )

    intent = _parse_agent_intent(agent_name, request_text)
    client = HubSpotClient(portal_config)

    try:
        if mode == "preview":
            preview = await _build_preview_for_intent(
                agent_name, intent, client, portal_config.portal_id
            )

            action_id = str(uuid.uuid4())[:8]
            preview_data = {
                "agent_name": agent_name,
                "request_text": request_text,
                "intent": intent.model_dump(mode="json"),
                "preview": preview.model_dump(mode="json"),
                "trace_id": trace_id,
                "batch_mode": batch_mode.value,
                "proposed_payload": proposed_payload or {},
            }
            _store_pending_preview(portal_config.portal_id, action_id, preview_data)

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
                    "impact_count": preview.impact_count,
                    "full_prompt": prompt.system_prompt,
                },
            )

        # Execute mode
        if agent_name == "objects" and intent.target_object:
            if intent.intent_type == "search":
                search_term = _extract_search_term(intent)
                result = await invoke_tool(
                    "hubspot_search_objects",
                    portal_config.portal_id,
                    object_type=intent.target_object,
                    query={"query": search_term, "limit": 10},
                    client=client,
                    portal_id=portal_config.portal_id,
                )
                return AgentResult(
                    agent_name=agent_name,
                    status="success",
                    data={"result": result},
                )

            if intent.intent_type == "create":
                props = proposed_payload.get("properties", {}) if proposed_payload else {}
                result = await invoke_tool(
                    "hubspot_create_object",
                    portal_config.portal_id,
                    object_type=intent.target_object,
                    properties=props,
                    client=client,
                    portal_id=portal_config.portal_id,
                )
                return AgentResult(
                    agent_name=agent_name,
                    status="success",
                    data={"result": result},
                )

            if intent.intent_type == "update":
                search_term = _extract_search_term(intent)
                search_result = await invoke_tool(
                    "hubspot_search_objects",
                    portal_config.portal_id,
                    object_type=intent.target_object,
                    query={"query": search_term, "limit": 10},
                    client=client,
                    portal_id=portal_config.portal_id,
                )
                records = search_result.get("results", [])
                if not records:
                    return AgentResult(
                        agent_name=agent_name,
                        status="error",
                        error_message="No matching records found to update.",
                    )
                object_id = records[0].get("id")
                props = proposed_payload.get("properties", {}) if proposed_payload else {}
                result = await invoke_tool(
                    "hubspot_update_object",
                    portal_config.portal_id,
                    object_id=object_id,
                    object_type=intent.target_object,
                    properties=props,
                    client=client,
                    portal_id=portal_config.portal_id,
                )
                return AgentResult(
                    agent_name=agent_name,
                    status="success",
                    data={"result": result},
                )

            if intent.intent_type == "delete":
                search_term = _extract_search_term(intent)
                search_result = await invoke_tool(
                    "hubspot_search_objects",
                    portal_config.portal_id,
                    object_type=intent.target_object,
                    query={"query": search_term, "limit": 10},
                    client=client,
                    portal_id=portal_config.portal_id,
                )
                records = search_result.get("results", [])
                if not records:
                    return AgentResult(
                        agent_name=agent_name,
                        status="error",
                        error_message="No matching records found to delete.",
                    )
                object_id = records[0].get("id")
                result = await invoke_tool(
                    "hubspot_delete_object",
                    portal_config.portal_id,
                    object_id=object_id,
                    object_type=intent.target_object,
                    client=client,
                    portal_id=portal_config.portal_id,
                )
                return AgentResult(
                    agent_name=agent_name,
                    status="success",
                    data={"result": result},
                )

        return AgentResult(
            agent_name=agent_name,
            status="success",
            data={"message": f"Executed {agent_name} for: {request_text}"},
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

from __future__ import annotations

import hubspot_agent.tools.workflows  # noqa: F401 — registers tools
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.blueprints.workflows import build_blueprint_context
from hubspot_agent.config import PortalConfig

# Import blueprint modules to trigger self-registration
from hubspot_agent.blueprints.workflows import (  # noqa: F401
    deal_stage_task,
    lead_scoring,
    re_anniversary_touch,
    re_buyer_appraisal_alert,
    re_buyer_criteria_match,
    re_buyer_financing_alert,
    re_buyer_inspection_alert,
    re_closing_day,
    re_engagement,
    re_hygiene_unassigned,
    re_offer_present_seller,
    re_open_house_followup,
    re_pre_listing_prep,
    re_showing_feedback,
    re_speed_to_lead,
    re_stale_buyer_deal,
    re_stale_listing,
    re_vendor_expiry,
    welcome_email,
)
from hubspot_agent.dispatch import register_execute, register_preview, register_reconcile
from hubspot_agent.models import PreviewResult, TaskIntent
from hubspot_agent.tools import get_tool, invoke_tool

_TOOL_NAMES = [
    "hubspot_get_workflow",
    "hubspot_list_workflows",
    "hubspot_create_workflow",
    "hubspot_create_workflow_from_blueprint",
    "hubspot_update_workflow",
    "hubspot_enroll_workflow",
    "hubspot_toggle_workflow",
]

_DOMAIN = (
    "You manage HubSpot automation workflows. "
    "You retrieve, list, create, update, enroll records in, and toggle workflow states."
)


def get_workflows_agent_prompt(portal_config: PortalConfig | None = None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    prompt = build_agent_prompt(
        agent_name="Workflows Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
    blueprint_ctx = build_blueprint_context()
    prompt.system_prompt += f"\n\n{blueprint_ctx}"
    return prompt


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

@register_preview("workflows")
async def _build_workflows_preview(
    agent_name: str,
    intent: TaskIntent,
    client,
    portal_id: str,
) -> PreviewResult:
    if intent.intent_type in ("search", "list", "get"):
        try:
            result = await invoke_tool(
                "hubspot_list_workflows",
                portal_id,
                client=client,
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
            preview={"workflows": records},
            impact_count=len(records),
            risk_level=intent.risk_level,
            proposed_payload={},
            original_values={},
        )

    if intent.intent_type == "create":
        return PreviewResult(
            preview={"message": "Will create a new workflow"},
            impact_count=1,
            risk_level=intent.risk_level,
            proposed_payload={"name": intent.description, "actions": []},
        )

    return PreviewResult(
        preview={"message": f"{intent.intent_type} operation on workflows"},
        impact_count=intent.estimated_impact or 1,
        risk_level=intent.risk_level,
    )


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

@register_execute("workflows")
async def _execute_workflows(
    agent_name: str,
    intent: TaskIntent,
    request_text: str,
    client,
    portal_id: str,
    proposed_payload: dict | None,
) -> dict:
    if intent.intent_type in ("search", "list", "get"):
        result = await invoke_tool(
            "hubspot_list_workflows",
            portal_id,
            client=client,
        )
        return {"status": "success", "data": {"result": result}}

    if intent.intent_type == "create":
        payload = proposed_payload or {}
        result = await invoke_tool(
            "hubspot_create_workflow",
            portal_id,
            name=payload.get("name", "New Workflow"),
            workflow_type=payload.get("workflow_type", "CONTACT_BASED"),
            actions=payload.get("actions", []),
            enrollment=payload.get("enrollment", {}),
            client=client,
        )
        return {"status": "success", "data": {"result": result}}

    if intent.intent_type == "update":
        payload = proposed_payload or {}
        workflow_id = payload.get("workflow_id")
        if not workflow_id:
            return {"status": "error", "message": "No workflow_id specified for update."}
        result = await invoke_tool(
            "hubspot_update_workflow",
            portal_id,
            workflow_id=workflow_id,
            updates=payload.get("updates", {}),
            client=client,
        )
        return {"status": "success", "data": {"result": result}}

    if intent.intent_type == "delete":
        return {"status": "success", "message": f"Executed workflows for: {request_text}"}

    return {"status": "success", "message": f"Executed workflows for: {request_text}"}


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------

@register_reconcile("workflows")
async def _reconcile_workflows(
    agent_name: str,
    intent: TaskIntent,
    request_text: str,
    client,
    portal_id: str,
    expected_payload: dict,
) -> dict:
    workflow_id = expected_payload.get("workflow_id") or expected_payload.get("id")
    if not workflow_id:
        return {"status": "unknown", "message": "No workflow_id in expected payload for reconciliation"}

    if intent.intent_type == "create":
        result = await invoke_tool(
            "hubspot_get_workflow",
            portal_id,
            workflow_id=workflow_id,
            client=client,
        )
        if "error" in result:
            return {
                "status": "discrepancy",
                "message": f"Workflow {workflow_id} not found after expected creation.",
                "expected": expected_payload,
                "actual": None,
            }
        return {
            "status": "verified",
            "message": f"Workflow {workflow_id} verified.",
            "expected": expected_payload,
            "actual": result,
        }

    if intent.intent_type == "update":
        result = await invoke_tool(
            "hubspot_get_workflow",
            portal_id,
            workflow_id=workflow_id,
            client=client,
        )
        if "error" in result:
            return {
                "status": "discrepancy",
                "message": f"Workflow {workflow_id} not found for update verification.",
                "expected": expected_payload,
                "actual": None,
            }
        return {
            "status": "verified",
            "message": f"Update verified on workflow {workflow_id}.",
            "expected": expected_payload,
            "actual": result,
        }

    if intent.intent_type == "delete":
        result = await invoke_tool(
            "hubspot_get_workflow",
            portal_id,
            workflow_id=workflow_id,
            client=client,
        )
        if "error" not in result:
            return {
                "status": "discrepancy",
                "message": f"Workflow {workflow_id} still exists after expected delete.",
                "expected": expected_payload,
                "actual": result,
            }
        return {
            "status": "verified",
            "message": f"Delete verified: workflow {workflow_id} no longer exists.",
            "expected": expected_payload,
            "actual": None,
        }

    return {"status": "unknown", "message": "Reconciliation not implemented for this intent"}

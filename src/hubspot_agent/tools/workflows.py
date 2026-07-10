from __future__ import annotations

from typing import Any
from urllib.parse import quote

from hubspot_agent.blueprints.workflows import get_blueprint
from hubspot_agent.blueprints.workflows.converter import blueprint_to_v4_payload

# Trigger blueprint self-registration
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
from hubspot_agent.client import HubSpotClient
from hubspot_agent.errors import HubSpotError, RateLimitError, ScopeError
from hubspot_agent.tools import tool


@tool(name="hubspot_get_workflow", description="Retrieve a HubSpot workflow by ID.")
async def hubspot_get_workflow(
    workflow_id: str,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    try:
        resp = await client.get(
            f"/automation/v4/flows/{quote(workflow_id, safe='')}",
            portal_id=portal_id,
            expected_scopes=["automation"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_get_workflow"}


@tool(name="hubspot_list_workflows", description="List all HubSpot workflows.")
async def hubspot_list_workflows(
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    try:
        resp = await client.get(
            "/automation/v4/flows",
            portal_id=portal_id,
            expected_scopes=["automation"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_list_workflows"}


@tool(name="hubspot_create_workflow", description="Create a new HubSpot workflow.")
async def hubspot_create_workflow(
    name: str,
    object_type: str,
    enrollment: dict[str, Any],
    actions: list[dict[str, Any]],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    """Create a workflow via the V4 Flows API.

    ``object_type`` (e.g. "Contact-based", "Deal-based") resolves both the V4
    ``objectTypeId`` and ``type``. ``enrollment`` and ``actions`` use the
    blueprint-spec shape consumed by ``blueprint_to_v4_payload``; see the
    blueprint modules for examples.
    """
    spec = {
        "name": name,
        "object_type": object_type,
        "enrollment": enrollment,
        "actions": actions,
    }
    try:
        payload = blueprint_to_v4_payload(spec)
        resp = await client.post(
            "/automation/v4/flows",
            portal_id=portal_id,
            body=payload,
            expected_scopes=["automation"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_create_workflow"}
    except ValueError as exc:
        return {
            "error": str(exc),
            "tool": "hubspot_create_workflow",
            "hint": (
                "Use the blueprint-spec shape for enrollment/actions, or use "
                "hubspot_create_workflow_from_blueprint for a template."
            ),
        }


# Server-managed fields the V4 docs say to remove from a GET response before
# re-PUTting it as an update; keeping them causes validation errors.
_PUT_STRIP_FIELDS = ("createdAt", "updatedAt", "dataSources", "id")


def _strip_for_put(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k not in _PUT_STRIP_FIELDS}


@tool(name="hubspot_update_workflow", description="Update an existing HubSpot workflow.")
async def hubspot_update_workflow(
    workflow_id: str,
    revision_id: str,
    body: dict[str, Any],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    """Update a workflow via the V4 Flows API (PUT).

    V4 requires PUT with the workflow's current ``revisionId`` in the body, and
    any field omitted from the body is deleted from the workflow. ``body`` must
    therefore be a *full* workflow payload — typically a prior GET response,
    optionally with caller edits merged in. GET the workflow first to obtain
    ``revision_id`` and the current body.
    """
    try:
        resp = await client.put(
            f"/automation/v4/flows/{quote(workflow_id, safe='')}",
            portal_id=portal_id,
            body={**_strip_for_put(body), "revisionId": revision_id},
            expected_scopes=["automation"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_update_workflow"}


@tool(name="hubspot_enroll_workflow", description="Enroll records into a HubSpot workflow.")
async def hubspot_enroll_workflow(
    workflow_id: str,
    object_ids: list[str],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    try:
        resp = await client.post(
            f"/automation/v4/flows/{quote(workflow_id, safe='')}/enrollments",
            portal_id=portal_id,
            body={"objectIds": object_ids},
            expected_scopes=["automation"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_enroll_workflow"}


@tool(name="hubspot_toggle_workflow", description="Toggle a HubSpot workflow on or off.")
async def hubspot_toggle_workflow(
    workflow_id: str,
    enabled: bool,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    try:
        resp = await client.post(
            f"/automation/v4/flows/{quote(workflow_id, safe='')}/toggle",
            portal_id=portal_id,
            body={"enabled": enabled},
            expected_scopes=["automation"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_toggle_workflow"}


@tool(
    name="hubspot_create_workflow_from_blueprint",
    description="Create a new HubSpot workflow from a blueprint template.",
)
async def hubspot_create_workflow_from_blueprint(
    blueprint_name: str,
    client: HubSpotClient,
    portal_id: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        blueprint = get_blueprint(blueprint_name)
        if blueprint is None:
            available = [b.name for b in __import__(
                "hubspot_agent.blueprints.workflows", fromlist=["list_blueprints"]
            ).list_blueprints()]
            return {
                "error": f"Blueprint '{blueprint_name}' not found.",
                "available_blueprints": available,
            }

        merged_params = params or {}
        # Merge parameter defaults from blueprint schema
        for key, info in blueprint.parameter_schema.items():
            if key not in merged_params:
                default = info.get("default")
                if default is not None:
                    merged_params[key] = default

        if blueprint.build is None:
            return {
                "error": "Blueprint build function is missing.",
                "tool": "hubspot_create_workflow_from_blueprint",
            }
        spec = blueprint.build(merged_params)
        if not spec.get("name"):
            spec["name"] = merged_params.get("name") or blueprint_name

        payload = blueprint_to_v4_payload(spec)

        resp = await client.post(
            "/automation/v4/flows",
            portal_id=portal_id,
            body=payload,
            expected_scopes=["automation"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_create_workflow_from_blueprint"}
    except ValueError as exc:
        return {
            "error": str(exc),
            "tool": "hubspot_create_workflow_from_blueprint",
            "hint": (
                "Some blueprints cannot be auto-created due to unsupported V4 API features: "
                "property-relative task due dates (e.g. '{{deadline - 5d}}'), "
                "unknown custom-object event triggers, placeholder team IDs, missing marketing email content_id, "
                "or missing custom properties/deal stages in the target portal. "
                "Build those workflows manually in the HubSpot UI."
            ),
        }

from __future__ import annotations

import asyncio
from typing import Any

from hubspot_agent.cache import SchemaCache, warm_standard_schemas
from hubspot_agent.capabilities import capability_explanation, probe_portal
from hubspot_agent.config import PortalConfig, load_portal_config, save_portal_config
from hubspot_agent.maintenance import run_maintenance


REQUIRED_SCOPES = [
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.companies.read",
    "crm.objects.companies.write",
    "crm.objects.deals.read",
    "crm.objects.deals.write",
    "crm.objects.tickets.read",
    "crm.objects.tickets.write",
    "crm.schemas.contacts.read",
    "crm.schemas.contacts.write",
    "crm.schemas.companies.read",
    "crm.schemas.companies.write",
    "crm.schemas.deals.read",
    "crm.schemas.deals.write",
    "crm.schemas.tickets.read",
    "crm.schemas.tickets.write",
    "automation.workflows.read",
    "automation.workflows.write",
    "crm.lists.read",
    "crm.lists.write",
    "crm.pipelines.read",
    "crm.pipelines.write",
    "settings.users.read",
    "settings.users.write",
    "crm.objects.engagements.read",
    "crm.objects.engagements.write",
]


async def run_setup(
    portal_id: str,
    method: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Run the guided setup wizard for a portal.

    Returns a dict with:
      - 'status': 'complete' | 'needs_auth' | 'error'
      - 'message': str — human-readable summary
      - 'capabilities': CapabilityMatrix | None
      - 'missing_scopes': list[str] | None
      - 'schema_counts': dict[str, int] | None
    """
    result: dict[str, Any] = {
        "status": "complete",
        "message": "",
        "capabilities": None,
        "missing_scopes": None,
        "schema_counts": None,
    }

    portal_config = load_portal_config(portal_id)

    # ------------------------------------------------------------------
    # 1. Auth
    # ------------------------------------------------------------------
    if portal_config is None or not portal_config.token:
        if method is None:
            result["status"] = "needs_auth"
            result["message"] = (
                f"Portal {portal_id} has no token configured.\n\n"
                f"Choose an auth method:\n"
                f"- `/hubspot setup {portal_id} oauth` — OAuth flow (opens browser)\n"
                f"- `/hubspot setup {portal_id} token <pat>` — Private App token"
            )
            return result

        if method == "token" or method == "private_app":
            if not token:
                result["status"] = "error"
                result["message"] = (
                    f"Usage: `/hubspot setup {portal_id} token <private-app-token>`"
                )
                return result

            save_portal_config(
                PortalConfig(
                    portal_id=portal_id,
                    token=token,
                    auth_type="private_app",
                )
            )
            portal_config = load_portal_config(portal_id)
        else:
            result["status"] = "error"
            result["message"] = f"Unknown auth method: {method}. Use 'oauth' or 'token'."
            return result

    if portal_config is None or not portal_config.token:
        result["status"] = "error"
        result["message"] = "Auth completed but token is still missing."
        return result

    # ------------------------------------------------------------------
    # 2. Maintenance
    # ------------------------------------------------------------------
    try:
        await asyncio.wait_for(run_maintenance(portal_id), timeout=10.0)
    except Exception:
        pass

    # ------------------------------------------------------------------
    # 3. Capabilities
    # ------------------------------------------------------------------
    try:
        matrix = await asyncio.wait_for(probe_portal(portal_config), timeout=15.0)
        result["capabilities"] = matrix
    except Exception:
        result["capabilities"] = None

    # ------------------------------------------------------------------
    # 4. Cache warming
    # ------------------------------------------------------------------
    try:
        await asyncio.wait_for(warm_standard_schemas(portal_config), timeout=15.0)
    except Exception:
        pass

    # ------------------------------------------------------------------
    # 5. Schema counts
    # ------------------------------------------------------------------
    schema_counts: dict[str, int] = {}
    cache = SchemaCache(portal_id)
    for domain in ["contacts", "companies", "deals", "tickets"]:
        data = cache.get(domain)
        if data and isinstance(data, dict):
            results = data.get("results", [])
            if isinstance(results, list):
                schema_counts[domain] = len(results)
    result["schema_counts"] = schema_counts or None

    # ------------------------------------------------------------------
    # 6. Scope gap report
    # ------------------------------------------------------------------
    required_scopes = set(REQUIRED_SCOPES)
    granted = set(portal_config.scopes_granted or [])
    missing = sorted(required_scopes - granted)
    result["missing_scopes"] = missing

    # ------------------------------------------------------------------
    # 7. Build summary message
    # ------------------------------------------------------------------
    lines = [f"Setup complete for portal {portal_id}."]

    if result["capabilities"]:
        cap = result["capabilities"]
        lines.append(f"\n**Portal Tier:** {cap.tier}")
        lines.append("**Capabilities:**")
        all_features = [
            "contacts", "companies", "deals", "tickets",
            "workflows", "lists", "pipelines", "users",
            "custom_objects", "calculated_properties",
        ]
        for feature in all_features:
            enabled = getattr(cap, feature, False)
            marker = "✓" if enabled else "✗"
            if enabled:
                lines.append(f"  - {feature}: {marker}")
            else:
                explanation = capability_explanation(feature)
                lines.append(f"  - {feature}: {marker} ({explanation})")

    if result["schema_counts"]:
        lines.append("\n**Schema cached:**")
        for domain, count in result["schema_counts"].items():
            lines.append(f"  - {domain}: {count} properties")

    if missing:
        total = len(required_scopes)
        granted_count = total - len(missing)
        lines.append(f"\n**Granted scopes:** {granted_count}/{total} needed.")
        lines.append(f"**Missing scopes:** {', '.join(missing)}")
        lines.append("Some features may be limited until these scopes are granted.")
    else:
        lines.append("\n**All required scopes are granted.**")

    result["message"] = "\n".join(lines)
    return result

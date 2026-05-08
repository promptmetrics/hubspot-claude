from __future__ import annotations

from hubspot_agent.models import BatchApprovalMode, PreviewResult, RiskLevel
from hubspot_agent.orchestrator import dispatch_agent
from hubspot_agent.preview import format_preview


_TOUR_STEPS = [
    {
        "title": "1. Read query — Find contacts",
        "request": "find all contacts",
        "agent": "objects",
        "mode": "preview",
        "description": "A simple read-only request routes to the ObjectsAgent.",
    },
    {
        "title": "2. Read query — Pipeline stages",
        "request": "get pipeline stages for deals",
        "agent": "pipelines",
        "mode": "preview",
        "description": "Pipeline metadata is served by the PipelinesAgent.",
    },
    {
        "title": "3. Write preview — Update a contact",
        "request": "update contact 123 email to alice@example.com",
        "agent": "objects",
        "mode": "preview",
        "risk": RiskLevel.MEDIUM,
        "description": "Write operations generate a preview with impact count and rollback info.",
    },
    {
        "title": "4. Write preview — Create a company",
        "request": "create a new company named Acme Inc",
        "agent": "objects",
        "mode": "preview",
        "risk": RiskLevel.MEDIUM,
        "description": "Creating records also triggers the HITL approval flow.",
    },
    {
        "title": "5. Batch write preview — Batch update",
        "request": "batch update contacts --batch",
        "agent": "objects",
        "mode": "preview",
        "risk": RiskLevel.HIGH,
        "batch_mode": BatchApprovalMode.BATCH,
        "description": "Batch mode lets you approve a full plan in one go.",
    },
    {
        "title": "6. Workflow blueprint — Welcome email",
        "request": "create a welcome email workflow",
        "agent": "workflows",
        "mode": "preview",
        "description": "The WorkflowsAgent can use built-in blueprints to construct automation quickly.",
    },
    {
        "title": "7. Approval flow explained",
        "request": "(demo only)",
        "agent": None,
        "mode": None,
        "description": (
            "Every write operation stops for your approval. "
            "You can reply y, n, details, or cancel. "
            "Destructive actions require typing the impact count to confirm."
        ),
    },
]


def _render_preview(agent_name: str, request: str, risk: RiskLevel, batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE) -> str:
    """Build a realistic-looking preview result for the tour."""
    preview_data: dict[str, any] = {
        "action": request,
        "affected_records": 1,
        "agent": agent_name,
    }
    if "batch" in request.lower():
        preview_data["affected_records"] = 42

    original_values = {}
    proposed_payload = {}
    if "update" in request.lower() and "contact" in request.lower():
        original_values = {"records": [{"id": "123", "properties": {"email": "old@example.com"}}]}
        proposed_payload = {"records": [{"id": "123", "properties": {"email": "alice@example.com"}}]}
    elif "create" in request.lower() and "company" in request.lower():
        proposed_payload = {"properties": {"name": "Acme Inc", "domain": "acme.com"}}
    elif "batch" in request.lower():
        original_values = {"records": [{"id": "1", "lifecyclestage": "lead"}, {"id": "2", "lifecyclestage": "lead"}]}
        proposed_payload = {"records": [{"id": "1", "lifecyclestage": "customer"}, {"id": "2", "lifecyclestage": "customer"}]}

    result = PreviewResult(
        preview=preview_data,
        impact_count=preview_data["affected_records"],
        risk_level=risk,
        proposed_payload=proposed_payload,
        original_values=original_values,
        batch_mode=batch_mode,
    )

    lines = [f"### Proposed Change ({result.risk_level.value.upper()})", f"- **Impact:** {result.impact_count} records"]
    if result.preview:
        lines.append("- **Preview:**")
        for key, value in result.preview.items():
            lines.append(f"  - {key}: {value}")

    if batch_mode == BatchApprovalMode.BATCH:
        lines.append("\n**Batch mode:** Approve this full plan once to execute all steps.")
        lines.append("Approve entire plan? (y/n)")
    elif risk == RiskLevel.DESTRUCTIVE:
        lines.append(f"\n**Destructive action.** Type `{result.impact_count}` to confirm, or `details` for full record list.")
    else:
        lines.append("\nApprove? (y/n/details)")
    return "\n".join(lines)


def run_tour(portal_id: str, portal_config=None) -> str:
    """Run 5–7 interactive examples demonstrating read queries, write previews, and approval flows.

    Returns a markdown-formatted tour string suitable for display in the CLI.
    """
    lines: list[str] = [
        f"# Welcome to the HubSpot Agent Tour",
        f"Portal: {portal_id}\n",
        "This walkthrough shows typical request flows — from read queries to write approvals.",
        "None of these examples make live changes.\n",
        "---\n",
    ]

    for step in _TOUR_STEPS:
        lines.append(f"## {step['title']}")
        lines.append(f"**Request:** `{step['request']}`\n")
        if step["agent"]:
            lines.append(f"**Routed to:** {step['agent']}")
        lines.append(f"{step['description']}\n")

        if step["agent"] and step["mode"] == "preview":
            risk = step.get("risk", RiskLevel.LOW)
            batch_mode = step.get("batch_mode", BatchApprovalMode.SINGLE)
            preview_text = _render_preview(step["agent"], step["request"], risk, batch_mode)
            lines.append("**Preview:**")
            lines.append(preview_text)

        lines.append("\n---\n")

    lines.extend([
        "## Next steps",
        "",
        "- Run a real read query: `/hubspot find contacts`",
        "- Run a real write preview: `/hubspot update contact 123 email to new@example.com`",
        "- Check status: `/hubspot status`",
        "- Refresh cache: `/hubspot refresh`",
        "",
        "Tour complete!",
    ])

    return "\n".join(lines)

from __future__ import annotations

from typing import Any

from hubspot_agent.blueprints.workflows import WorkflowBlueprint, register_blueprint


def _build(params: dict[str, Any]) -> dict[str, Any]:
    from_email = params.get("from_email", "")
    inactive_days = params.get("inactive_days", 90)
    subject = params.get("subject", "We miss you!")
    body = params.get("body", "It's been a while — here's what's new.")
    actions: list[dict[str, Any]] = [
        {
            "type": "DELAY",
            "properties": {"delay": {"unit": "DAYS", "amount": inactive_days}},
        },
        {
            "type": "SEND_EMAIL",
            "properties": {
                "from_email": from_email,
                "subject": subject,
                "body": body,
            },
        },
    ]
    return {
        "name": params.get("name", "Re-engagement Campaign"),
        "type": "CONTACT_FLOW",
        "actions": actions,
        "enrollment": {
            "type": "LIST_BASED",
            "list_id": params.get("list_id"),
        },
    }


register_blueprint(
    WorkflowBlueprint(
        name="re_engagement",
        description="Send a re-engagement email to contacts who have been inactive for a specified number of days.",
        tags=["email", "contact", "retention"],
        parameter_schema={
            "name": {"type": "string", "default": "Re-engagement Campaign", "description": "Workflow name"},
            "from_email": {"type": "string", "required": True, "description": "Sender email address"},
            "inactive_days": {"type": "integer", "default": 90, "description": "Days of inactivity before email is sent"},
            "subject": {"type": "string", "default": "We miss you!", "description": "Email subject line"},
            "body": {"type": "string", "default": "It's been a while — here's what's new.", "description": "Email body"},
            "list_id": {"type": "string", "required": True, "description": "Enrollment list ID"},
        },
        build=_build,
    )
)

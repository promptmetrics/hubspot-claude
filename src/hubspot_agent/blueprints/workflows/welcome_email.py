from __future__ import annotations

from typing import Any

from hubspot_agent.blueprints.workflows import WorkflowBlueprint, register_blueprint


def _build(params: dict[str, Any]) -> dict[str, Any]:
    from_email = params.get("from_email", "")
    delay_hours = params.get("delay_hours", 0)
    subject = params.get("subject", "Welcome!")
    body = params.get("body", "Thanks for joining us.")
    actions: list[dict[str, Any]] = [
        {
            "type": "DELAY",
            "properties": {"delay": {"unit": "HOURS", "amount": delay_hours}},
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
        "name": params.get("name", "Welcome Email"),
        "type": "CONTACT_FLOW",
        "actions": actions,
        "enrollment": {
            "type": "LIST_BASED",
            "list_id": params.get("list_id"),
        },
    }


register_blueprint(
    WorkflowBlueprint(
        name="welcome_email",
        description="Send a welcome email to new contacts after an optional delay.",
        tags=["email", "onboarding", "contact"],
        parameter_schema={
            "name": {"type": "string", "default": "Welcome Email", "description": "Workflow name"},
            "from_email": {"type": "string", "required": True, "description": "Sender email address"},
            "delay_hours": {"type": "integer", "default": 0, "description": "Delay before sending email"},
            "subject": {"type": "string", "default": "Welcome!", "description": "Email subject line"},
            "body": {"type": "string", "default": "Thanks for joining us.", "description": "Email body"},
            "list_id": {"type": "string", "required": True, "description": "Enrollment list ID"},
        },
        build=_build,
    )
)

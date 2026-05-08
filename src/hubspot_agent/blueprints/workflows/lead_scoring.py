from __future__ import annotations

from typing import Any

from hubspot_agent.blueprints.workflows import WorkflowBlueprint, register_blueprint


def _build(params: dict[str, Any]) -> dict[str, Any]:
    score_property = params.get("score_property", "hubspotscore")
    increment = params.get("increment", 10)
    threshold = params.get("threshold", 50)
    actions: list[dict[str, Any]] = [
        {
            "type": "SET_PROPERTY",
            "properties": {
                "property": score_property,
                "value": f"{{contact.{score_property} + {increment}}}",
            },
        },
    ]
    if threshold:
        actions.append(
            {
                "type": "BRANCH",
                "properties": {
                    "condition": {
                        "field": score_property,
                        "operator": "IS_GREATER_THAN",
                        "value": threshold,
                    },
                    "true_actions": [
                        {
                            "type": "SET_PROPERTY",
                            "properties": {
                                "property": "lifecyclestage",
                                "value": "marketingqualifiedlead",
                            },
                        }
                    ],
                },
            }
        )
    return {
        "name": params.get("name", "Lead Scoring"),
        "type": "CONTACT_FLOW",
        "actions": actions,
        "enrollment": {
            "type": "EVENT_BASED",
            "event": params.get("event", "PAGE_VIEW"),
        },
    }


register_blueprint(
    WorkflowBlueprint(
        name="lead_scoring",
        description="Increment a score property when a contact engages, and optionally promote lifecycle stage when a threshold is reached.",
        tags=["scoring", "contact", "automation"],
        parameter_schema={
            "name": {"type": "string", "default": "Lead Scoring", "description": "Workflow name"},
            "score_property": {"type": "string", "default": "hubspotscore", "description": "Contact property to increment"},
            "increment": {"type": "integer", "default": 10, "description": "Points to add per engagement"},
            "threshold": {"type": "integer", "default": 50, "description": "Score threshold to promote lifecycle stage (0 to disable)"},
            "event": {"type": "string", "default": "PAGE_VIEW", "description": "Enrollment trigger event"},
        },
        build=_build,
    )
)

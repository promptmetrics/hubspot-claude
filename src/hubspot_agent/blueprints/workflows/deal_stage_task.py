from __future__ import annotations

from typing import Any

from hubspot_agent.blueprints.workflows import WorkflowBlueprint, register_blueprint


def _build(params: dict[str, Any]) -> dict[str, Any]:
    stage = params.get("stage", "qualifiedtobuy")
    task_title = params.get("task_title", "Follow up on deal stage change")
    due_days = params.get("due_days", 1)
    assignee = params.get("assignee", "{{deal.hubspot_owner_id}}")
    actions: list[dict[str, Any]] = [
        {
            "type": "CREATE_TASK",
            "properties": {
                "title": task_title,
                "due_date": f"{{timestamp + {due_days}d}}",
                "assignee": assignee,
                "notes": f"Deal moved to stage: {stage}",
            },
        },
    ]
    return {
        "name": params.get("name", "Deal Stage Task"),
        "type": "DEAL_FLOW",
        "actions": actions,
        "enrollment": {
            "type": "PROPERTY_BASED",
            "property": "dealstage",
            "operator": "IS_EQUAL_TO",
            "value": stage,
        },
    }


register_blueprint(
    WorkflowBlueprint(
        name="deal_stage_task",
        description="Create a follow-up task when a deal moves to a specific stage.",
        tags=["deal", "task", "pipeline"],
        parameter_schema={
            "name": {"type": "string", "default": "Deal Stage Task", "description": "Workflow name"},
            "stage": {"type": "string", "default": "qualifiedtobuy", "description": "Deal stage internal ID to trigger on"},
            "task_title": {"type": "string", "default": "Follow up on deal stage change", "description": "Task title"},
            "due_days": {"type": "integer", "default": 1, "description": "Days until task is due"},
            "assignee": {"type": "string", "default": "{{deal.hubspot_owner_id}}", "description": "User ID or token to assign the task to"},
        },
        build=_build,
    )
)

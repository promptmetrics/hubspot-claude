from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel, VerificationResult

# First field error from the most recent parse_plan call, if it failed on a
# pydantic ValidationError (well-formed JSON, bad shape).  Reset at the top of
# every call so it never leaks across invocations.  Read via
# :func:`last_parse_error` to enrich the "Could not parse" message with the
# offending field rather than a bare traceback.
_last_parse_error: str | None = None


def last_parse_error() -> str | None:
    """First field error from the most recent :func:`parse_plan` call, if any."""
    return _last_parse_error


def _first_validation_error(exc: ValidationError) -> str:
    """Render the first pydantic field error as ``"<loc>: <msg>"``."""
    errors = exc.errors()
    if not errors:
        return str(exc)
    first = errors[0]
    loc = ".".join(str(p) for p in first.get("loc", ()))
    msg = first.get("msg", "invalid")
    return f"{loc}: {msg}" if loc else msg


def _extract_json(text: str) -> str | None:
    """Extract the first JSON object or array from a Markdown/code block or raw text."""
    # Try fenced code block first
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
    else:
        candidate = text.strip()

    # Find the first JSON-like object
    start = candidate.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx, ch in enumerate(candidate[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not in_string:
            in_string = True
            continue
        if ch == '"' and in_string:
            in_string = False
            continue
        if not in_string:
            if ch in {"{", "["}:
                depth += 1
            elif ch in {"}", "]"}:
                depth -= 1
                if depth == 0:
                    return candidate[start : idx + 1]
    return None


def parse_plan(text: str) -> LoopPlan | None:
    """Parse a LoopPlan JSON string (possibly wrapped in Markdown) into a LoopPlan.

    Returns ``None`` for unparseable JSON *or* a pydantic ``ValidationError`` (e.g.
    ``prerequisites: [1]`` — pydantic v2 won't coerce an int to ``list[str]``).
    On a ``ValidationError`` the first field error is stashed for
    :func:`last_parse_error` so callers can surface *which* field was bad
    instead of a raw traceback.
    """
    global _last_parse_error
    _last_parse_error = None

    json_text = _extract_json(text)
    if not json_text:
        return None
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    try:
        # Normalize steps
        raw_steps = data.get("steps", [])
        steps: list[PlanStep] = []
        for raw in raw_steps:
            if not isinstance(raw, dict):
                continue
            risk = raw.get("risk_level")
            risk_level = RiskLevel(risk.lower()) if isinstance(risk, str) else None
            steps.append(
                PlanStep(
                    step_number=raw.get("step_number", 0),
                    agent=raw.get("agent", ""),
                    action=raw.get("action", ""),
                    description=raw.get("description"),
                    hubspot_endpoint=raw.get("hubspot_endpoint"),
                    payload_summary=raw.get("payload_summary", {}),
                    validation_rules=raw.get("validation_rules", []),
                    expected_artifact_keys=raw.get("expected_artifact_keys", []),
                    prerequisites=raw.get("prerequisites", []),
                    risk_level=risk_level,
                    tool_name=raw.get("tool_name"),
                    tool_input=raw.get("tool_input", {}),
                )
            )

        overall_risk = data.get("overall_risk", "low")
        try:
            overall_risk_level = RiskLevel(overall_risk.lower())
        except ValueError:
            overall_risk_level = RiskLevel.LOW

        return LoopPlan(
            goal=data.get("goal", ""),
            success_criteria=data.get("success_criteria", []),
            steps=steps,
            overall_risk=overall_risk_level,
            max_iterations=data.get("max_iterations", 3),
            artifact_schema=data.get("artifact_schema", {}),
        )
    except ValidationError as exc:
        _last_parse_error = _first_validation_error(exc)
        return None


def validate_plan(plan: LoopPlan, capability_matrix: dict[str, bool] | None = None) -> list[str]:
    """Return a list of validation errors (missing capabilities, bad ordering, etc.)."""
    errors: list[str] = []
    capability_matrix = capability_matrix or {}

    if not plan.goal:
        errors.append("Plan is missing a goal.")

    if not plan.steps:
        errors.append("Plan has no steps.")

    seen_numbers = set()
    for step in plan.steps:
        if step.step_number in seen_numbers:
            errors.append(f"Duplicate step number {step.step_number}.")
        seen_numbers.add(step.step_number)

        if not step.agent:
            errors.append(f"Step {step.step_number} is missing an agent.")
        if not step.action:
            errors.append(f"Step {step.step_number} is missing an action.")

        # Capability check
        agent_key = step.agent.lower()
        if agent_key == "workflows" and capability_matrix.get("workflows") is False:
            errors.append(f"Step {step.step_number} requires workflows but portal lacks workflow support.")

        # Verbatim tool-path validation (PR 2 / bug 2).  A step may carry a
        # ``tool_name`` + ``tool_input`` so the loop executes the exact payload
        # instead of free-text agent dispatch (which fuzzy-matched records[0]
        # and could write the wrong record).  Reject the malformed cases that
        # would either miss the target or hit the write gate with no payload.
        errors.extend(_validate_step_tool(step))

        # Dependency check
        for prereq in step.prerequisites:
            try:
                prereq_num = int(prereq)
            except ValueError:
                errors.append(f"Step {step.step_number} has non-numeric prerequisite '{prereq}'.")
                continue
            if prereq_num not in seen_numbers:
                errors.append(
                    f"Step {step.step_number} depends on step {prereq_num}, which is not present or not yet ordered."
                )

    return errors


# Single-record object tools that MUST name their target by id.  Mirrors the
# CRUD surface the bug-2 fuzzy-match exploited; batch/bulk tools carry a
# ``records``/``inputs`` list instead, and non-object update tools use their
# own id keys (sent verbatim by the tool path, so no fuzzy match there).
_TARGET_ID_KEY: dict[str, str] = {
    "hubspot_update_object": "object_id",
    "hubspot_delete_object": "object_id",
    "hubspot_merge_objects": "primary_object_id",
}


def _step_tool_is_write(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """Classify a step's tool as a write, mirroring ``handlers._is_write_tool``.

    A tool is a write if its required scopes carry a ``.write``/``.delete``
    suffix, its name is in ``WRITE_TOOLS``, or it is ``hubspot_raw_api`` with a
    mutating method.  Kept here (not imported from handlers) so ``planning``
    stays a leaf module with no circular-dependency risk.
    """
    from hubspot_agent.scope_registry import (
        RAW_API_WRITE_METHODS,
        WRITE_TOOLS,
        get_required_scopes,
    )

    if tool_name == "hubspot_raw_api":
        method = str((tool_input or {}).get("method", "")).upper()
        return method in RAW_API_WRITE_METHODS
    if tool_name in WRITE_TOOLS:
        return True
    target = (tool_input or {}).get("object_type")
    scopes = get_required_scopes([tool_name], target)
    return any(s.endswith(".write") or s.endswith(".delete") for s in scopes)


def _validate_step_tool(step: PlanStep) -> list[str]:
    """Validation errors for a step's optional ``tool_name``/``tool_input``.

    Empty list for a legacy text-only step (``tool_name`` unset).  Rejects:
    unknown ``tool_name``; ``tool_input`` without ``tool_name``; a write tool
    with empty ``tool_input``; and a single-record update/delete/merge tool
    with no target ``object_id`` (literal or ``{{placeholder}}``).
    """
    errors: list[str] = []
    tool_name = step.tool_name
    tool_input = step.tool_input or {}

    if tool_name is None:
        if tool_input:
            errors.append(
                f"Step {step.step_number} has tool_input but no tool_name; "
                "set tool_name or drop tool_input."
            )
        return errors

    from hubspot_agent.tools import get_tool

    if get_tool(tool_name) is None:
        errors.append(
            f"Step {step.step_number} names an unknown tool '{tool_name}'. "
            "Run `hubspot tools list` for valid tool names."
        )
        return errors

    if _step_tool_is_write(tool_name, tool_input) and not tool_input:
        errors.append(
            f"Step {step.step_number} write tool '{tool_name}' has empty tool_input; "
            "provide the full payload (object_id, properties, …)."
        )

    id_key = _TARGET_ID_KEY.get(tool_name)
    if id_key is not None:
        target_id = tool_input.get(id_key)
        if target_id in (None, "", []):
            errors.append(
                f"Step {step.step_number} tool '{tool_name}' is missing '{id_key}' "
                "(a literal id or a {{artifact_key}} placeholder)."
            )

    return errors


def parse_verification_result(text: str) -> VerificationResult | None:
    """Parse a VerificationResult JSON string (possibly wrapped in Markdown) into a model."""
    json_text = _extract_json(text)
    if not json_text:
        return None
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    status = data.get("status", "error")
    try:
        status_enum = VerificationResult.Status(status.lower())
    except ValueError:
        status_enum = VerificationResult.Status.ERROR

    return VerificationResult(
        status=status_enum,
        mismatches=data.get("mismatches", []),
        missing_fields=data.get("missing_fields", []),
        checked_count=data.get("checked_count", 0),
        verified_count=data.get("verified_count", 0),
        message=data.get("message"),
    )


def plan_to_markdown(plan: LoopPlan) -> str:
    """Render a LoopPlan as user-facing Markdown."""
    lines: list[str] = [
        f"## Goal\n{plan.goal}\n",
        f"**Overall risk:** {plan.overall_risk.value}",
        f"**Max iterations:** {plan.max_iterations}",
    ]
    if plan.success_criteria:
        lines.append("\n### Success criteria")
        for criterion in plan.success_criteria:
            lines.append(f"- {criterion}")
    if plan.steps:
        lines.append("\n### Steps")
        for step in plan.steps:
            prereq = f" (depends on {', '.join(step.prerequisites)})" if step.prerequisites else ""
            risk = f" [{step.risk_level.value}]" if step.risk_level else ""
            lines.append(f"{step.step_number}. **{step.agent}** — {step.action}{risk}{prereq}")
            if step.description:
                lines.append(f"   - {step.description}")
            if step.expected_artifact_keys:
                lines.append(f"   - Artifacts: {', '.join(step.expected_artifact_keys)}")
    return "\n".join(lines)

from __future__ import annotations

import json
import re
from typing import Any

from hubspot_agent.models import LoopPlan, PlanStep, RiskLevel, VerificationResult


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
    """Parse a LoopPlan JSON string (possibly wrapped in Markdown) into a LoopPlan."""
    json_text = _extract_json(text)
    if not json_text:
        return None
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

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

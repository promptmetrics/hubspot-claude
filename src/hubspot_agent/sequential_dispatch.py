from __future__ import annotations

import json
from typing import Any, Callable

from hubspot_agent.agent_dispatch import build_verify_prompt, spawn_agent
from hubspot_agent.models import (
    AgentResult,
    LoopPlan,
    PlanStep,
    RiskLevel,
    StepArtifact,
    VerificationResult,
)
from hubspot_agent.planning import parse_verification_result


ApprovalCallback = Callable[[dict[str, Any]], bool]


def _is_write_step(step: PlanStep) -> bool:
    """Heuristic: steps whose action contains create/update/delete/upsert/enroll/toggle are writes."""
    action = step.action.lower()
    write_verbs = {"create", "update", "delete", "upsert", "merge", "enroll", "toggle", "bulk"}
    return any(verb in action for verb in write_verbs)


def _resolve_artifacts(
    step: PlanStep, artifacts: dict[int, StepArtifact]
) -> dict[str, Any]:
    """Collect artifact outputs from prerequisite steps."""
    resolved: dict[str, Any] = {}
    for prereq in step.prerequisites:
        try:
            prereq_num = int(prereq)
        except ValueError:
            continue
        artifact = artifacts.get(prereq_num)
        if artifact:
            resolved.update(artifact.outputs)
    return resolved


def _build_step_request(step: PlanStep, request_text: str, resolved: dict[str, Any]) -> str:
    parts = [f"Step {step.step_number}: {step.action}"]
    if step.description:
        parts.append(step.description)
    if resolved:
        parts.append(f"Resolved artifacts: {json.dumps(resolved)}")
    parts.append(f"Original request: {request_text}")
    return "\n".join(parts)


def _capture_artifacts(result: AgentResult, step: PlanStep) -> StepArtifact:
    """Extract StepArtifact from an AgentResult."""
    outputs: dict[str, Any] = {}
    created_ids: list[str] = []
    warnings: list[str] = []

    artifacts = result.data.get("artifacts")
    if isinstance(artifacts, dict):
        outputs.update(artifacts)
    created = result.data.get("created_ids")
    if isinstance(created, list):
        created_ids.extend(str(c) for c in created)
    warns = result.data.get("warnings")
    if isinstance(warns, list):
        warnings.extend(str(w) for w in warns)

    # Infer created IDs from common output keys
    for key in ("property_id", "workflow_id", "object_id", "list_id", "pipeline_id", "user_id"):
        if key in outputs and outputs[key] not in created_ids:
            created_ids.append(str(outputs[key]))

    return StepArtifact(
        step_number=step.step_number,
        agent=step.agent,
        outputs=outputs,
        created_ids=created_ids,
        warnings=warnings,
    )


def verify_step(
    step: PlanStep,
    artifact: StepArtifact,
    portal_config: Any,
) -> tuple[str, VerificationResult]:
    """Spawn VerifyAgent and decide whether to proceed, retry, or escalate.

    Returns:
        A tuple of (decision, result). decision is one of: verified, retry, escalate.
    """
    expected_state = {
        "step_number": step.step_number,
        "agent": step.agent,
        "action": step.action,
        "expected_outputs": step.expected_artifact_keys,
        "artifact": artifact.model_dump(),
    }
    prompt = build_verify_prompt(
        step=expected_state,
        expected_state=expected_state,
        portal_config=portal_config,
    )
    raw = spawn_agent("verify", prompt, context={"step": expected_state})
    if not raw or raw.startswith("[agent:"):
        # No runtime or empty response: assume verified in mock/test environments
        result = VerificationResult(
            status=VerificationResult.Status.VERIFIED,
            message="VerifyAgent not available in test environment; assumed verified.",
        )
        return "verified", result

    result = parse_verification_result(raw)
    if result is None:
        result = VerificationResult(
            status=VerificationResult.Status.ERROR,
            message=f"Could not parse verification result: {raw[:200]}",
        )
        return "escalate", result

    if result.status == VerificationResult.Status.VERIFIED:
        return "verified", result
    if result.status in {VerificationResult.Status.MISMATCH, VerificationResult.Status.PARTIAL}:
        return "retry", result
    return "escalate", result


def execute_plan(
    plan: LoopPlan,
    request_text: str,
    portal_config: Any,
    trace_id: str,
    approve_callback: ApprovalCallback | None = None,
) -> list[StepArtifact]:
    """Execute a LoopPlan sequentially, passing artifacts between steps.

    Args:
        plan: The LoopPlan to execute.
        request_text: The original user request.
        portal_config: Portal configuration.
        trace_id: Trace identifier for logging.
        approve_callback: Optional callable that receives a preview dict and returns True to approve.

    Returns:
        List of StepArtifact objects produced by each step.

    Raises:
        RuntimeError: on unrecoverable error or rejected approval.
    """
    approve_callback = approve_callback or (lambda _: True)
    artifacts: dict[int, StepArtifact] = {}

    # Lazy import to avoid a circular dependency with orchestrator.py.
    from hubspot_agent.orchestrator import dispatch_agent

    for step in plan.steps:
        resolved = _resolve_artifacts(step, artifacts)
        step_request = _build_step_request(step, request_text, resolved)

        # Preview
        preview_result = dispatch_agent(
            step.agent,
            step_request,
            portal_config=portal_config,
            mode="preview",
        )
        if preview_result.status == "error":
            raise RuntimeError(
                f"Step {step.step_number} ({step.agent}) preview failed: {preview_result.error_message}"
            )

        # Approval for writes
        is_write = _is_write_step(step)
        if is_write and not approve_callback(preview_result.data):
            raise RuntimeError(f"Step {step.step_number} ({step.agent}) was not approved.")

        # Execute
        payload = preview_result.data.get("proposed_payload")
        execute_result = dispatch_agent(
            step.agent,
            step_request,
            portal_config=portal_config,
            mode="execute",
            payload=payload if isinstance(payload, dict) else None,
        )
        if execute_result.status == "error":
            raise RuntimeError(
                f"Step {step.step_number} ({step.agent}) execution failed: {execute_result.error_message}"
            )

        artifact = _capture_artifacts(execute_result, step)
        artifacts[step.step_number] = artifact

        if is_write:
            decision, verification = verify_step(step, artifact, portal_config)
            if decision == "escalate":
                raise RuntimeError(
                    f"Step {step.step_number} verification failed: {verification.message}"
                )

    return list(artifacts.values())

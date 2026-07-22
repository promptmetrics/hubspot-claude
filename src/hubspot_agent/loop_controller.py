from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from hubspot_agent.loop_state import LoopState
from hubspot_agent.models import VerificationResult


@dataclass
class LoopDecision:
    """Outcome of a single loop-controller decision."""

    action: str  # "proceed", "retry", "escalate", "stop"
    reason: str
    final: bool = False


class LoopController:
    """Decide whether a loop should proceed, retry, escalate, or stop.

    Stop conditions:

    - ``max_iterations`` exceeded.
    - ``max_steps`` proxy budget: executed-step count exhausted.
    - ``max_api_calls`` proxy budget: HubSpot API-call count exhausted.
    - ``verification_plateau`` identical mismatches in a row.
    - ``error_budget`` non-retryable or unexpected errors exceeded.

    The controller is stateless except for the ``LoopState`` it mutates in
    place on ``record_iteration``.
    """

    def __init__(
        self,
        max_iterations: int = 3,
        verification_plateau: int = 2,
        error_budget: int = 5,
        max_steps: int = 50,
        max_api_calls: int = 1000,
    ) -> None:
        self.max_iterations = max_iterations
        self.verification_plateau = verification_plateau
        self.error_budget = error_budget
        self.max_steps = max_steps
        self.max_api_calls = max_api_calls

    def next_action(
        self,
        state: LoopState,
        verification: VerificationResult | None = None,
        step_error: str | None = None,
    ) -> LoopDecision:
        """Return the controller decision for the current loop state.

        This method checks stop conditions in order of precedence:

        1. Iteration ceiling
        2. Step budget (proxy)
        3. API-call budget (proxy)
        4. Error budget exhaustion
        5. Verification plateau (two identical mismatches)

        If none fire and a verification mismatch is present, the loop retries.
        If verification passes, the loop proceeds to the next step.
        """
        if state.iterations >= self.max_iterations:
            return LoopDecision(
                action="stop",
                reason=f"Maximum iterations ({self.max_iterations}) reached.",
                final=True,
            )

        if state.step_count >= self.max_steps:
            return LoopDecision(
                action="stop",
                reason=f"Step budget ({self.max_steps}) exhausted.",
                final=True,
            )

        if state.api_call_count >= self.max_api_calls:
            return LoopDecision(
                action="stop",
                reason=f"API-call budget ({self.max_api_calls}) exhausted.",
                final=True,
            )

        if self._error_budget_exceeded(state):
            return LoopDecision(
                action="escalate",
                reason=f"Error budget ({self.error_budget}) exhausted; human review required.",
                final=True,
            )

        if verification is not None:
            mismatch_hash = self._hash_verification(verification)
            if mismatch_hash and mismatch_hash == state.last_verification_hash:
                state.plateau_count += 1
            else:
                state.plateau_count = 1 if mismatch_hash else 0
            state.last_verification_hash = mismatch_hash
            if state.plateau_count >= self.verification_plateau:
                return LoopDecision(
                    action="escalate",
                    reason="Verification plateau: same mismatch repeated.",
                    final=True,
                )

            if verification.status == VerificationResult.Status.VERIFIED:
                return LoopDecision(action="proceed", reason="Verification passed.")
            if verification.status in {
                VerificationResult.Status.MISMATCH,
                VerificationResult.Status.PARTIAL,
            }:
                return LoopDecision(
                    action="retry",
                    reason=f"Verification {verification.status.value}: {verification.message or 'mismatch detected'}.",
                )
            if verification.status == VerificationResult.Status.ERROR:
                return LoopDecision(
                    action="escalate",
                    reason=f"Verification error: {verification.message or 'unknown error'}.",
                    final=True,
                )

        if step_error:
            return LoopDecision(
                action="escalate",
                reason=f"Step error: {step_error}",
                final=True,
            )

        return LoopDecision(action="proceed", reason="Ready for next step.")

    def record_iteration(self, state: LoopState) -> None:
        """Increment the loop iteration counter after a retry or execute cycle."""
        state.iterations += 1

    def _error_budget_exceeded(self, state: LoopState) -> bool:
        """Return True if too many errors have been logged."""
        return bool(state.last_error) and state.iterations >= self.error_budget

    @staticmethod
    def _hash_verification(verification: VerificationResult) -> str | None:
        """Return a stable hash for a verification mismatch, or None if verified."""
        if verification.status == VerificationResult.Status.VERIFIED:
            return None
        fingerprint = {
            "status": verification.status.value,
            "mismatches": verification.mismatches,
            "missing_fields": sorted(verification.missing_fields),
            "message": verification.message,
        }
        return str(json.dumps(fingerprint, sort_keys=True, default=str))

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


class BatchApprovalMode(str, Enum):
    SINGLE = "single"
    BATCH = "batch"
    PATTERN = "pattern"


class TaskIntent(BaseModel):
    intent_type: str
    target_object: str | None = None
    description: str
    risk_level: RiskLevel
    estimated_impact: int | None = None
    required_scopes: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    step_number: int
    agent: str
    action: str
    hubspot_endpoint: str | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    validation_rules: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    plan_id: str
    thread_id: str
    steps: list[PlanStep]
    overall_risk: RiskLevel
    rollback_available: bool
    estimated_duration_seconds: int


class PreviewResult(BaseModel):
    preview: dict[str, Any]
    impact_count: int
    rollback_steps: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    proposed_payload: dict[str, Any] = Field(default_factory=dict)
    original_values: dict[str, Any] = Field(default_factory=dict)
    informing_sources: list[dict[str, Any]] = Field(default_factory=list)
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE
    pattern_sample_size: int = 3


class AgentResult(BaseModel):
    agent_name: str
    status: str  # "success", "error", "preview", "needs_approval", "corrected"
    data: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    retryable: bool = False
    corrected_payload: dict[str, Any] | None = None
    correction_reason: str | None = None
    reflection: dict[str, Any] | None = None

from hubspot_agent.models import (
    LoopPlan,
    PlanStep,
    RiskLevel,
    StepArtifact,
    VerificationResult,
)


def test_loop_plan_creation():
    plan = LoopPlan(
        goal="Create a contact property and a workflow using it",
        success_criteria=["property exists", "workflow references property"],
        steps=[
            PlanStep(
                step_number=1,
                agent="properties",
                action="create property renewal_date",
                description="Create a custom contact property named renewal_date",
                expected_artifact_keys=["property_id"],
                risk_level=RiskLevel.MEDIUM,
            ),
            PlanStep(
                step_number=2,
                agent="workflows",
                action="create workflow enrollment rule",
                description="Build a workflow that enrolls contacts 30 days before renewal_date",
                prerequisites=["1"],
                risk_level=RiskLevel.MEDIUM,
            ),
        ],
        overall_risk=RiskLevel.MEDIUM,
        max_iterations=3,
    )
    assert plan.goal == "Create a contact property and a workflow using it"
    assert len(plan.steps) == 2
    assert plan.steps[1].prerequisites == ["1"]


def test_step_artifact_creation():
    artifact = StepArtifact(
        step_number=1,
        agent="properties",
        outputs={"property_id": "prop-123"},
        created_ids=["prop-123"],
        warnings=["schema cache stale"],
    )
    assert artifact.outputs["property_id"] == "prop-123"
    assert artifact.created_ids == ["prop-123"]


def test_verification_result_creation():
    result = VerificationResult(
        status=VerificationResult.Status.VERIFIED,
        checked_count=5,
        verified_count=5,
        message="All properties match expected state.",
    )
    assert result.status == VerificationResult.Status.VERIFIED
    assert result.verified_count == 5


def test_verification_result_mismatch():
    result = VerificationResult(
        status=VerificationResult.Status.MISMATCH,
        mismatches=[{"field": "name", "expected": "Foo", "actual": "Bar"}],
        missing_fields=["description"],
        checked_count=3,
        verified_count=1,
    )
    assert result.status == VerificationResult.Status.MISMATCH
    assert result.missing_fields == ["description"]

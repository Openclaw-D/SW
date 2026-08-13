from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.contracts.errors import (
    BusinessValidationError,
    HardGateBlockedError,
    IdempotencyConflictError,
)
from app.contracts.workbench import ApprovalTransitionInput, DimensionSeriesRequest
from app.core.config import Settings
from app.services.workbench import create_workbench_service
from tests.services.fixtures import StaticGenerator, make_bundle


def test_pass_approval_transitions_are_versioned_and_idempotent(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "approval-pass.db"),
        generator=StaticGenerator(make_bundle()),
    )
    try:
        initial = service.get_approval_state("project-a")
        assert initial.status == "draft"
        assert initial.version == 1
        assert initial.hard_gate_status == "pass"

        submit = ApprovalTransitionInput(
            expectedVersion=1,
            transition="submit",
            requestedBy="business",
            reason="提交风控审批",
        )
        submitted = service.transition_approval(
            "project-a", submit, idempotency_key="approval-submit-001"
        )
        repeated = service.transition_approval(
            "project-a", submit, idempotency_key="approval-submit-001"
        )
        assert submitted.model_dump(mode="json") == repeated.model_dump(mode="json")
        assert submitted.status == "submitted"
        assert submitted.version == 2

        with pytest.raises(IdempotencyConflictError):
            service.transition_approval(
                "project-a",
                submit.model_copy(update={"transition": "save_draft"}),
                idempotency_key="approval-submit-001",
            )

        complete = ApprovalTransitionInput(
            expectedVersion=2,
            transition="complete",
            requestedBy="leadership",
            reason="完成审批",
        )
        completed = service.transition_approval(
            "project-a", complete, idempotency_key="approval-complete-001"
        )
        assert completed.status == "completed"
        assert completed.version == 3
        with pytest.raises(BusinessValidationError) as terminal:
            service.transition_approval(
                "project-a",
                ApprovalTransitionInput(
                    expectedVersion=3,
                    transition="save_draft",
                    requestedBy="business",
                    reason="试图重新打开已完成审批",
                ),
                idempotency_key="approval-reopen-001",
            )
        assert terminal.value.code == "approval_transition_invalid"
        assert service.get_approval_state("project-a").status == "completed"
        connection = service.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM approval_transitions").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="immutable table: approval_transitions"):
            connection.execute("DELETE FROM approval_transitions")
    finally:
        service.close()


@pytest.mark.parametrize(
    ("pending", "expected_status", "risk_veto"),
    [(False, "block", True), (True, "manual_review", False)],
)
def test_hard_gate_and_missing_evidence_cannot_be_overridden_by_leadership(
    pending: bool,
    expected_status: str,
    risk_veto: bool,
    tmp_path: Path,
) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / f"approval-{expected_status}.db"),
        generator=StaticGenerator(
            make_bundle(policy_result="block", policy_pending=pending),
            identity=f"gate-{expected_status}",
        ),
    )
    try:
        state = service.get_approval_state("project-a")
        assert state.hard_gate_status == expected_status
        assert state.risk_veto is risk_veto
        assert state.blocking_rule_ids == ["HG-OWNERSHIP"]
        if pending:
            result = service.list_policy_results("project-a")[0]
            assert result.result == "manual_review"
            assert result.gate_triggered is False

        submitted = service.transition_approval(
            "project-a",
            ApprovalTransitionInput(
                expectedVersion=1,
                transition="submit",
                requestedBy="business",
                reason="提交",
            ),
            idempotency_key=f"approval-gated-submit-{expected_status}",
        )
        for role in ("business", "risk", "leadership"):
            with pytest.raises(HardGateBlockedError) as blocked:
                service.transition_approval(
                    "project-a",
                    ApprovalTransitionInput(
                        expectedVersion=submitted.version,
                        transition="complete",
                        requestedBy=role,
                        reason=f"{role} 要求完成",
                    ),
                    idempotency_key=(
                        f"approval-gated-complete-{expected_status}-{role}"
                    ),
                )
            assert blocked.value.details["blockingRuleIds"] == ["HG-OWNERSHIP"]
        assert service.get_approval_state("project-a").status == "submitted"
        connection = service.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM approval_transitions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM policy_results").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="immutable table: policy_results"):
            connection.execute("UPDATE policy_results SET result = 'pass'")
    finally:
        service.close()


def test_dimension_series_delegates_or_returns_explicit_unavailable(tmp_path: Path) -> None:
    request = DimensionSeriesRequest(
        projectId="project-a",
        dimensionId="production",
        metricIds=["electricity"],
        grain="month",
        startDate="2026-01-01",
        endDate="2026-06-30",
        timezone="Asia/Shanghai",
    )
    available = {
        "status": "available",
        "points": [
            {
                "id": "point-1",
                "label": "2026-01",
                "measures": [],
                "periodStart": "2026-01-01",
                "periodEnd": "2026-01-31",
            }
        ],
        "sourceLabel": "Back-3 deterministic generator",
        "isSimulated": True,
    }
    service = create_workbench_service(
        Settings(database_path=tmp_path / "series.db"),
        generator=StaticGenerator(make_bundle(), series_response=available),
    )
    try:
        response = service.query_dimension_series(
            "project-a", "production", request
        )
        assert response.status == "available"
        assert response.points[0].period_start == "2026-01-01"
        assert response.source_label == "Back-3 deterministic generator"
    finally:
        service.close()

    unavailable_service = create_workbench_service(
        Settings(database_path=tmp_path / "series-unavailable.db"),
        generator=StaticGenerator(make_bundle(), identity="no-series-v1"),
    )
    try:
        unavailable = unavailable_service.query_dimension_series(
            "project-a", "production", request
        )
        assert unavailable.status == "unavailable"
        assert unavailable.points == []
        assert "未构造替代指标" in unavailable.message

        with pytest.raises(BusinessValidationError) as mismatch:
            unavailable_service.query_dimension_series(
                "project-a", "revenue", request
            )
        assert mismatch.value.code == "path_body_mismatch"
    finally:
        unavailable_service.close()

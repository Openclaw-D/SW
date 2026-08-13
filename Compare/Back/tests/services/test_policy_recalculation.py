from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.contracts.errors import (
    BusinessValidationError,
    HardGateBlockedError,
    IdempotencyConflictError,
    VersionConflictError,
)
from app.contracts.workbench import ApprovalTransitionInput, BusinessCorrectionCommand
from app.core.config import Settings
from app.domain.scoring import SCORING_FACT_KEYS
from app.main import create_app
from app.services.workbench import create_workbench_service
from tests.services.fixtures import StaticGenerator, make_bundle


def _generator(identity: str = "policy-recalculation-v1") -> StaticGenerator:
    bundle = make_bundle(recalculable=True, frozen_policies=True)
    for fact in bundle.workbench["facts"]:
        if fact["factKey"] in SCORING_FACT_KEYS:
            fact["factKey"] = f"{fact['dimensionId']}.{fact['factKey']}"
    return StaticGenerator(
        bundle, identity=identity
    )


def _fact(service, fact_key: str):
    return max(
        (
            fact
            for fact in service.get_workbench("project-a").facts
            if fact.fact_key == fact_key or fact.fact_key.endswith(f".{fact_key}")
        ),
        key=lambda fact: fact.version,
    )


def _correction(
    service,
    fact_key: str,
    proposed_value: object,
    *,
    evidence_ref: str = "project-a-ev-excel",
) -> BusinessCorrectionCommand:
    fact = _fact(service, fact_key)
    return BusinessCorrectionCommand(
        projectId="project-a",
        factKey=fact.fact_key,
        fromFactVersionId=fact.id,
        proposedValue=proposed_value,
        reason=f"重算 {fact_key} 的冻结制度规则",
        evidenceRefs=[evidence_ref],
        expectedVersion=fact.version,
    )


def _table_counts(service) -> dict[str, int]:
    connection = service.repository.raw_connection_for_tests()
    return {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (
            "fact_versions",
            "business_corrections",
            "policy_results",
            "review_events",
        )
    }


def test_correction_appends_rule_snapshot_event_and_updates_current_views(
    tmp_path: Path,
) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "policy-recalculation.db"),
        generator=_generator(),
    )
    try:
        initial = service.list_policy_results("project-a")
        assert len(initial) == 3
        assert {item.result for item in initial} == {"pass"}
        initial_ids = {item.id for item in initial}

        command = _correction(service, "prohibited_status", True)
        correction = service.submit_business_correction(
            "project-a",
            command.fact_key,
            command,
            idempotency_key="policy-block-001",
        )

        current = service.list_policy_results("project-a")
        assert len(current) == 3
        assert not initial_ids.intersection(item.id for item in current)
        by_rule = {item.rule_id: item for item in current}
        assert by_rule["CMP-H-001"].result == "block"
        assert by_rule["CMP-H-001"].gate_triggered is True
        assert by_rule["TRX-H-001"].result == "pass"
        assert by_rule["DEBT-H-001"].result == "pass"

        connection = service.repository.raw_connection_for_tests()
        history = service.repository.list_policy_results("project-a", connection)
        assert len(history) == 6
        recalculated = history[-3:]
        assert len({item.evaluated_at for item in recalculated}) == 1
        assert all(
            item.evaluation_input["source"] == "business_correction_recalculation"
            for item in recalculated
        )
        assert all(
            item.evaluation_input["trigger"]["factVersionId"]
            == correction.fact_version.id
            for item in recalculated
        )

        events = service.repository.list_review_events("project-a", connection)
        assert [event.sequence for event in events] == [1, 2]
        assert events[-1].event_type == "policy_result_recorded"
        assert events[-1].actor == "system"
        assert len(events[-1].rule_refs) == 3
        assert events[-1].evidence_targets
        for target in events[-1].evidence_targets:
            fact = service.repository.get_fact_version(
                "project-a", target.fact_version_id, connection
            )
            assert target.evidence_ref in fact.evidence_refs
            assert service.locators.resolve(
                "project-a", target.evidence_ref, connection
            ).status == "located"

        workbench = service.get_workbench("project-a")
        assert len(workbench.risk_summary.hard_constraint_results) == 3
        assert {
            item.id for item in workbench.risk_summary.hard_constraint_results
        } == {item.id for item in current}
        assert set(workbench.risk_summary.evidence_refs) == {
            evidence_ref
            for item in current
            for target in item.evidence_targets
            for evidence_ref in target.evidence_refs
        }
        assert workbench.risk_summary.decision_grade == "E"

        approval = service.get_approval_state("project-a")
        assert approval.hard_gate_status == "block"
        assert approval.risk_veto is True
        assert approval.risk_veto_rule_ids == ["CMP-H-001"]
        submitted = service.transition_approval(
            "project-a",
            ApprovalTransitionInput(
                expectedVersion=1,
                transition="submit",
                requestedBy="business",
                reason="提交领导审批",
            ),
            idempotency_key="policy-submit-001",
        )
        assert submitted.status == "submitted"
        transition_row = connection.execute(
            "SELECT policy_result_ids_json FROM approval_transitions WHERE project_id = ?",
            ("project-a",),
        ).fetchone()
        assert set(json.loads(transition_row[0])) == {item.id for item in current}
        assert len(json.loads(transition_row[0])) == 3
        with pytest.raises(HardGateBlockedError):
            service.transition_approval(
                "project-a",
                ApprovalTransitionInput(
                    expectedVersion=2,
                    transition="complete",
                    requestedBy="leadership",
                    reason="尝试完成审批",
                ),
                idempotency_key="policy-complete-blocked-001",
            )
    finally:
        service.close()


def test_unlocated_correction_only_requires_manual_review(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "policy-manual.db"),
        generator=_generator("policy-manual-v1"),
    )
    try:
        command = _correction(
            service,
            "prohibited_status",
            True,
            evidence_ref="project-a-ev-pending",
        )
        service.submit_business_correction(
            "project-a",
            command.fact_key,
            command,
            idempotency_key="policy-manual-001",
        )
        current = {item.rule_id: item for item in service.list_policy_results("project-a")}
        prohibited = current["CMP-H-001"]
        assert prohibited.result == "manual_review"
        assert prohibited.gate_triggered is False
        assert prohibited.primary_target is not None
        assert prohibited.primary_target.unavailable_reason
        approval = service.get_approval_state("project-a")
        assert approval.hard_gate_status == "manual_review"
        assert approval.risk_veto is False
        workbench = service.get_workbench("project-a")
        assert workbench.risk_summary.decision_grade == workbench.risk_summary.score_grade
    finally:
        service.close()


def test_policy_recalculation_is_idempotent_and_failed_writes_are_atomic(
    tmp_path: Path,
) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "policy-idempotency.db"),
        generator=_generator("policy-idempotency-v1"),
    )
    command = _correction(service, "financing_ratio", 1.05)
    try:
        before_invalid = _table_counts(service)
        with pytest.raises(BusinessValidationError) as invalid:
            service.submit_business_correction(
                "project-a",
                command.fact_key,
                command.model_copy(update={"proposed_value": "not-a-number"}),
                idempotency_key="policy-invalid-input-001",
            )
        assert invalid.value.code == "policy_evaluation_input_invalid"
        assert _table_counts(service) == before_invalid

        first = service.submit_business_correction(
            "project-a",
            command.fact_key,
            command,
            idempotency_key="policy-idempotent-001",
        )
        repeated = service.submit_business_correction(
            "project-a",
            command.fact_key,
            command,
            idempotency_key="policy-idempotent-001",
        )
        assert repeated.model_dump(mode="json") == first.model_dump(mode="json")
        after_success = _table_counts(service)
        assert after_success["policy_results"] == 6
        assert after_success["review_events"] == 2

        with pytest.raises(IdempotencyConflictError):
            service.submit_business_correction(
                "project-a",
                command.fact_key,
                command.model_copy(update={"proposed_value": 0.8}),
                idempotency_key="policy-idempotent-001",
            )
        assert _table_counts(service) == after_success

        with pytest.raises(VersionConflictError):
            service.submit_business_correction(
                "project-a",
                command.fact_key,
                command,
                idempotency_key="policy-stale-001",
            )
        assert _table_counts(service) == after_success
    finally:
        service.close()


def test_recalculated_policy_state_survives_restart_without_duplication(
    tmp_path: Path,
) -> None:
    database = tmp_path / "policy-restart.db"
    generator = _generator("policy-restart-v1")
    first_service = create_workbench_service(
        Settings(database_path=database), generator=generator
    )
    command = _correction(first_service, "duplicate_registration", True)
    try:
        created = first_service.submit_business_correction(
            "project-a",
            command.fact_key,
            command,
            idempotency_key="policy-restart-001",
        )
    finally:
        first_service.close()

    second_service = create_workbench_service(
        Settings(database_path=database), generator=generator
    )
    try:
        assert _fact(second_service, "duplicate_registration").version == 2
        assert len(second_service.list_policy_results("project-a")) == 3
        assert {
            item.rule_id: item.result
            for item in second_service.list_policy_results("project-a")
        }["DEBT-H-001"] == "block"
        assert second_service.get_approval_state("project-a").hard_gate_status == "block"
        connection = second_service.repository.raw_connection_for_tests()
        assert len(second_service.repository.list_policy_results("project-a", connection)) == 6
        assert len(second_service.repository.list_review_events("project-a", connection)) == 2
        repeated = second_service.submit_business_correction(
            "project-a",
            command.fact_key,
            command,
            idempotency_key="policy-restart-001",
        )
        assert repeated.model_dump(mode="json") == created.model_dump(mode="json")
        assert len(second_service.repository.list_policy_results("project-a", connection)) == 6
        assert len(second_service.repository.list_review_events("project-a", connection)) == 2
    finally:
        second_service.close()


def test_policy_results_http_returns_only_latest_three(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "policy-http.db"),
        generator=_generator("policy-http-v1"),
    )
    command = _correction(service, "prohibited_status", True)
    service.submit_business_correction(
        "project-a",
        command.fact_key,
        command,
        idempotency_key="policy-http-001",
    )
    with TestClient(create_app(service=service)) as client:
        response = client.get("/api/v1/projects/project-a/policy/results")
        assert response.status_code == 200, response.text
        results = response.json()["data"]
        assert len(results) == 3
        assert len({item["ruleId"] for item in results}) == 3
        assert {item["ruleId"]: item["result"] for item in results}[
            "CMP-H-001"
        ] == "block"

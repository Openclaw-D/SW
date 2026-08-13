from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from app.contracts.errors import (
    BusinessValidationError,
    IdempotencyConflictError,
    VersionConflictError,
)
from app.contracts.workbench import (
    BusinessAnswerCommand,
    BusinessCorrectionCommand,
    RiskAnswerCommand,
    RiskQuestionCommand,
)
from app.core.config import Settings
from app.services.workbench import create_workbench_service
from tests.services.fixtures import StaticGenerator, make_bundle


def _target(
    evidence_id: str = "project-a-ev-excel",
    *,
    unavailable_reason: str | None = None,
    fact_version_id: str | None = "project-a-fact-v1",
) -> dict[str, object]:
    target: dict[str, object] = {
        "evidenceRef": evidence_id,
        "evidenceRefs": [evidence_id],
        "dimensionId": "compliance",
        "reviewTargetId": "company.registration",
        "factVersionId": fact_version_id,
    }
    if unavailable_reason is not None:
        target["unavailableReason"] = unavailable_reason
    return target


def _question(expected_version: int = 1, *, question: str = "请核验登记状态"):
    return RiskQuestionCommand(
        projectId="project-a",
        dimensionId="compliance",
        question=question,
        evidenceTargets=[_target()],
        reviewTargetId="company.registration",
        threadId="thread-registration",
        replyToEventId=None,
        factVersionIds=["project-a-fact-v1"],
        evidenceRefs=["project-a-ev-excel"],
        expectedVersion=expected_version,
    )


def test_correction_is_immutable_optimistic_and_idempotent(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "correction.db"),
        generator=StaticGenerator(make_bundle(recalculable=True)),
    )
    command = BusinessCorrectionCommand(
        projectId="project-a",
        factKey="company.registration",
        fromFactVersionId="project-a-fact-v1",
        proposedValue="已人工复核",
        reason="依据原始台账复核",
        evidenceRefs=["project-a-ev-excel"],
        expectedVersion=1,
    )
    try:
        first = service.submit_business_correction(
            "project-a",
            "company.registration",
            command,
            idempotency_key="correction-repeat-001",
        )
        repeated = service.submit_business_correction(
            "project-a",
            "company.registration",
            command,
            idempotency_key="correction-repeat-001",
        )
        assert repeated.model_dump(mode="json") == first.model_dump(mode="json")
        assert first.fact_version.version == 2
        assert first.fact_version.id != command.from_fact_version_id
        assert first.event.sequence == 1
        assert first.event.fact_version_ids == [first.fact_version.id]
        assert first.event.evidence_targets

        conflicting_payload = command.model_copy(update={"proposed_value": "另一值"})
        with pytest.raises(IdempotencyConflictError):
            service.submit_business_correction(
                "project-a",
                "company.registration",
                conflicting_payload,
                idempotency_key="correction-repeat-001",
            )
        with pytest.raises(VersionConflictError) as stale:
            service.submit_business_correction(
                "project-a",
                "company.registration",
                command,
                idempotency_key="correction-stale-001",
            )
        assert stale.value.details == {"expectedVersion": 1, "actualVersion": 2}

        connection = service.repository.raw_connection_for_tests()
        assert connection.execute(
            "SELECT COUNT(*) FROM fact_versions WHERE fact_key = 'company.registration'"
        ).fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM business_corrections").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM policy_results").fetchone()[0] == 3
        audit = service.repository.list_audit_records("project-a", connection)
        assert [item.sequence for item in audit] == [1, 2, 3]
        assert audit[1].previous_hash == audit[0].event_hash
        assert audit[2].previous_hash == audit[1].event_hash
        with pytest.raises(sqlite3.IntegrityError, match="immutable table: fact_versions"):
            connection.execute(
                "UPDATE fact_versions SET value_json = 'null' WHERE id = ?",
                (first.fact_version.id,),
            )
    finally:
        service.close()


def test_concurrent_corrections_allow_one_version_winner(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "concurrent-correction.db"),
        generator=StaticGenerator(make_bundle(recalculable=True)),
    )
    barrier = Barrier(3)

    def submit(index: int) -> tuple[str, object]:
        command = BusinessCorrectionCommand(
            projectId="project-a",
            factKey="company.registration",
            fromFactVersionId="project-a-fact-v1",
            proposedValue=f"并发修正-{index}",
            reason=f"并发乐观锁验证-{index}",
            evidenceRefs=["project-a-ev-excel"],
            expectedVersion=1,
        )
        barrier.wait()
        try:
            result = service.submit_business_correction(
                "project-a",
                "company.registration",
                command,
                idempotency_key=f"correction-concurrent-{index:03d}",
            )
        except VersionConflictError as exc:
            return "conflict", exc.details
        return "created", result.fact_version.version

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit, index) for index in (1, 2)]
            barrier.wait()
            outcomes = [future.result(timeout=5) for future in futures]
        assert sorted(outcome[0] for outcome in outcomes) == ["conflict", "created"]
        assert ("created", 2) in outcomes
        assert (
            "conflict",
            {"expectedVersion": 1, "actualVersion": 2},
        ) in outcomes
        connection = service.repository.raw_connection_for_tests()
        assert connection.execute(
            "SELECT COUNT(*) FROM fact_versions WHERE fact_key = 'company.registration'"
        ).fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM business_corrections").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM policy_results").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 2
    finally:
        service.close()


def test_successive_corrections_form_fact_and_review_chains(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "correction-chain.db"),
        generator=StaticGenerator(make_bundle(recalculable=True)),
    )
    try:
        first = service.submit_business_correction(
            "project-a",
            "company.registration",
            BusinessCorrectionCommand(
                projectId="project-a",
                factKey="company.registration",
                fromFactVersionId="project-a-fact-v1",
                proposedValue="第一次复核",
                reason="第一次修正",
                evidenceRefs=["project-a-ev-excel"],
                expectedVersion=1,
            ),
            idempotency_key="correction-chain-001",
        )
        second = service.submit_business_correction(
            "project-a",
            "company.registration",
            BusinessCorrectionCommand(
                projectId="project-a",
                factKey="company.registration",
                fromFactVersionId=first.fact_version.id,
                proposedValue="第二次复核",
                reason="第二次修正",
                evidenceRefs=["project-a-ev-excel"],
                expectedVersion=2,
            ),
            idempotency_key="correction-chain-002",
        )
        assert second.fact_version.version == 3
        assert second.event.thread_id == first.event.thread_id
        assert second.event.reply_to_event_id == first.event.id
        with service.repository.transaction(write=False) as connection:
            stored = service.repository.get_fact_version(
                "project-a", second.fact_version.id, connection
            )
        assert stored.supersedes_version_id == first.fact_version.id
    finally:
        service.close()


def test_review_chain_has_backend_sequence_targets_and_thread_integrity(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "review.db"),
        generator=StaticGenerator(make_bundle()),
    )
    try:
        question = service.submit_risk_question(
            "project-a",
            _question(),
            idempotency_key="review-question-001",
        )
        assert question.sequence == 1
        assert question.issue_status == "open"
        assert question.actor == "risk"
        assert question.immutable is True
        assert question.evidence_targets[0].evidence_ref == "project-a-ev-excel"

        with pytest.raises(BusinessValidationError) as reused_thread:
            service.submit_risk_question(
                "project-a",
                _question(expected_version=2, question="错误地复用根线程"),
                idempotency_key="review-thread-reuse-001",
            )
        assert reused_thread.value.code == "review_thread_exists"

        answer_command = BusinessAnswerCommand(
            projectId="project-a",
            dimensionId="compliance",
            answer="已按原始台账复核",
            evidenceTargets=[_target()],
            reviewTargetId="company.registration",
            threadId="thread-registration",
            replyToEventId=question.id,
            factVersionIds=["project-a-fact-v1"],
            evidenceRefs=["project-a-ev-excel"],
            expectedVersion=2,
        )
        answer = service.submit_business_answer(
            "project-a",
            answer_command,
            idempotency_key="review-answer-0001",
        )
        repeated = service.submit_business_answer(
            "project-a",
            answer_command,
            idempotency_key="review-answer-0001",
        )
        assert repeated.model_dump(mode="json") == answer.model_dump(mode="json")
        assert answer.event.sequence == 2
        assert answer.open_issue_count == 0

        stale_reply = answer_command.model_copy(
            update={
                "answer": "错误地回复旧事件",
                "expected_version": 3,
                "reply_to_event_id": question.id,
            }
        )
        with pytest.raises(BusinessValidationError) as stale_reply_error:
            service.submit_business_answer(
                "project-a",
                stale_reply,
                idempotency_key="review-stale-reply-001",
            )
        assert stale_reply_error.value.code == "review_reply_stale"

        risk_command = RiskAnswerCommand(
            projectId="project-a",
            dimensionId="compliance",
            answer="进入制度 Gate",
            evidenceTargets=[_target()],
            reviewTargetId="company.registration",
            threadId="thread-registration",
            replyToEventId=answer.event.id,
            factVersionIds=["project-a-fact-v1"],
            evidenceRefs=["project-a-ev-excel"],
            expectedVersion=3,
        )
        risk_answer = service.submit_risk_answer(
            "project-a",
            risk_command,
            idempotency_key="review-risk-answer-001",
        )
        assert risk_answer.event.sequence == 3
        assert risk_answer.event.issue_status == "pending_gate"
        assert risk_answer.open_issue_count == 1
        events = service.list_review_events("project-a")
        assert [event.sequence for event in events] == [1, 2, 3]
        assert all(event.evidence_targets for event in events)

        bad_reply = answer_command.model_copy(
            update={
                "expected_version": 4,
                "thread_id": "another-thread",
            }
        )
        with pytest.raises(BusinessValidationError) as mismatch:
            service.submit_business_answer(
                "project-a",
                bad_reply,
                idempotency_key="review-bad-thread-001",
            )
        assert mismatch.value.code == "review_thread_mismatch"

        connection = service.repository.raw_connection_for_tests()
        with pytest.raises(sqlite3.IntegrityError, match="immutable table: review_events"):
            connection.execute(
                "UPDATE review_events SET summary = 'changed' WHERE id = ?",
                (question.id,),
            )
    finally:
        service.close()


def test_review_rejects_false_evidence_fact_pair_and_requires_pending_reason(
    tmp_path: Path,
) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "review-validation.db"),
        generator=StaticGenerator(make_bundle()),
    )
    try:
        false_pair = RiskQuestionCommand(
            projectId="project-a",
            dimensionId="compliance",
            question="错误配对",
            evidenceTargets=[_target("project-a-ev-pdf")],
            reviewTargetId="company.registration",
            threadId="thread-false-pair",
            replyToEventId=None,
            factVersionIds=["project-a-fact-v1"],
            evidenceRefs=["project-a-ev-pdf"],
            expectedVersion=1,
        )
        with pytest.raises(BusinessValidationError) as pair_error:
            service.submit_risk_question(
                "project-a",
                false_pair,
                idempotency_key="review-false-pair-001",
            )
        assert pair_error.value.code == "evidence_fact_pair_mismatch"

        # A rejected write is still a completed idempotent outcome: retrying
        # the same payload returns the original business error, while changing
        # the payload under the same key is a conflict.
        with pytest.raises(BusinessValidationError) as replayed_pair_error:
            service.submit_risk_question(
                "project-a",
                false_pair,
                idempotency_key="review-false-pair-001",
            )
        assert replayed_pair_error.value.code == pair_error.value.code

        changed_pair_payload = false_pair.model_dump(by_alias=True, mode="json")
        changed_pair_payload["question"] = "同 key 的不同请求"
        with pytest.raises(IdempotencyConflictError):
            service.submit_risk_question(
                "project-a",
                RiskQuestionCommand.model_validate(changed_pair_payload),
                idempotency_key="review-false-pair-001",
            )

        pending_target = _target(
            "project-a-ev-pending",
            fact_version_id=None,
        )
        pending_without_reason = RiskQuestionCommand(
            projectId="project-a",
            dimensionId="compliance",
            question="待补材料",
            evidenceTargets=[pending_target],
            reviewTargetId="company.registration",
            threadId="thread-pending",
            replyToEventId=None,
            factVersionIds=[],
            evidenceRefs=["project-a-ev-pending"],
            expectedVersion=1,
        )
        with pytest.raises(BusinessValidationError) as reason_error:
            service.submit_risk_question(
                "project-a",
                pending_without_reason,
                idempotency_key="review-pending-no-reason-001",
            )
        assert reason_error.value.code == "unavailable_reason_required"

        pending_target["unavailableReason"] = "材料尚未提供"
        pending_payload = pending_without_reason.model_dump(by_alias=True, mode="json")
        pending_payload["evidenceTargets"] = [pending_target]
        pending_with_reason = RiskQuestionCommand.model_validate(
            pending_payload
        )
        accepted = service.submit_risk_question(
            "project-a",
            pending_with_reason,
            idempotency_key="review-pending-reason-001",
        )
        assert accepted.evidence_targets[0].unavailable_reason == "材料尚未提供"
        assert accepted.sequence == 1

        connection = service.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0] == 3
    finally:
        service.close()


def test_all_review_submission_types_require_authoritative_evidence_targets(
    tmp_path: Path,
) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "review-empty-targets.db"),
        generator=StaticGenerator(make_bundle()),
    )
    common = {
        "projectId": "project-a",
        "dimensionId": "compliance",
        "evidenceTargets": [],
        "reviewTargetId": None,
        "replyToEventId": None,
        "factVersionIds": [],
        "evidenceRefs": [],
        "expectedVersion": 1,
    }
    submissions = (
        (
            service.submit_risk_question,
            RiskQuestionCommand(
                **common,
                threadId="thread-empty-question",
                question="缺少证据目标",
            ),
        ),
        (
            service.submit_business_answer,
            BusinessAnswerCommand(
                **common,
                threadId="thread-empty-business-answer",
                answer="缺少证据目标",
            ),
        ),
        (
            service.submit_risk_answer,
            RiskAnswerCommand(
                **common,
                threadId="thread-empty-risk-answer",
                answer="缺少证据目标",
            ),
        ),
    )
    try:
        for index, (submit, command) in enumerate(submissions, start=1):
            with pytest.raises(BusinessValidationError) as error:
                submit(
                    "project-a",
                    command,
                    idempotency_key=f"review-empty-target-{index:03d}",
                )
            assert error.value.code == "review_evidence_required"
        connection = service.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0] == 3
    finally:
        service.close()

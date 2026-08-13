from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals.model_gateway.blind_eval_rubric_v2 import (
    ABSOLUTE_STOP_CEILING_MS,
    GATE_STATE,
    HARD_RATE_THRESHOLDS,
    HARD_ZERO_THRESHOLDS,
    IMAGE_IOU_THRESHOLD,
    IMAGE_TARGET_COVERAGE_THRESHOLD,
    PARTIAL_THRESHOLDS,
    PARTIAL_WEIGHTS,
    BlindCaseSubmissionV2,
    BlindRunSubmissionV2,
    CaseTelemetryV2,
    ExpectedCriticalUnresolvedV2,
    LocatorAuditEvidenceV2,
    UnresolvedAuditEvidenceV2,
    expected_cases_from_oracle_v2,
    score_blind_submission_v2,
)
from evals.model_gateway.codex_oracle import load_oracle_fixture


BACK_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = BACK_ROOT / "evals/model_gateway"
IMAGE_CASE_ID = "project-01-image-scene"
PDF_CASE_ID = "project-01-pdf-contract"
EXCEL_CASE_ID = "project-01-excel-equipment-list"

IMAGE_ROLES = {
    IMAGE_CASE_ID: {
        "anchor-image-equipment-focal": "image:focal-object",
        "anchor-image-synthetic-caption": "image:caption",
    }
}
CONTROLLED_REGIONS = {
    IMAGE_CASE_ID: {
        "anchor-image-equipment-focal": "manifest:focalArea",
        "anchor-image-synthetic-caption": "controlled:captionRegion",
    }
}
V1_HASHES = {
    "blind_eval_rubric.py": "06d318d22bad8285c36446297c3a4e918adc5a4dd8fd798b1fba6d21e1eb3707",
    "BLIND-EVAL-RUBRIC.md": "abe9cbc18266c93a7eff3bb90ad3ab70fe2ae7510b17708a264784b1a3d3d488",
    "BLIND-EVAL-SCORING-REPORT.json": "fef166adb6d4993cc51ba90b6b4660f979fc221b4c8d6525ebdb068e8b737e45",
    "BLIND-EVAL-SCORING-REPORT.md": "212f0e234c9ed1e71d0f91bd51b322287db75453824a00fed046ceaef9096abe",
}


def _expected():
    return expected_cases_from_oracle_v2(
        load_oracle_fixture(),
        semantic_roles=IMAGE_ROLES,
        controlled_regions=CONTROLLED_REGIONS,
    )


def _perfect_submission(
    *,
    mutate_payload=None,
    mutate_case=None,
    total_elapsed_ms: float = 40_000.0,
    continued_after_absolute_stop: bool = False,
) -> tuple[BlindRunSubmissionV2, object]:
    fixture = load_oracle_fixture()
    expected = expected_cases_from_oracle_v2(
        fixture,
        semantic_roles=IMAGE_ROLES,
        controlled_regions=CONTROLLED_REGIONS,
    )
    base = datetime(2026, 8, 13, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    cases = []
    for index, oracle_case in enumerate(fixture.replay_cases):
        payload = oracle_case.expected_output.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        if mutate_payload is not None:
            mutate_payload(oracle_case.case_id, payload)
        expected_case = expected[oracle_case.case_id]
        role_by_anchor = {
            target.reference_anchor_id: target.semantic_role
            for target in expected_case.locator_targets.values()
        }
        region_by_anchor = {
            target.reference_anchor_id: target.controlled_region_id
            for target in expected_case.locator_targets.values()
        }
        elapsed = 10_000.0 + index * 1_000.0
        started = base + timedelta(seconds=index * 20)
        telemetry = CaseTelemetryV2(
            case_id=oracle_case.case_id,
            carrier=expected_case.media_kind,
            started_at=started.isoformat(),
            finished_at=(started + timedelta(milliseconds=elapsed)).isoformat(),
            elapsed_ms=elapsed,
            attempt_count=1,
            retry_count=0,
            retry_error_codes=(),
            terminal_status=payload["status"],
            stop_reason=None,
        )
        locator_evidence = tuple(
            LocatorAuditEvidenceV2(
                source_anchor_id=binding["sourceAnchorId"],
                semantic_role=role_by_anchor[binding["sourceAnchorId"]],
                openable=True,
                controlled_region_id=region_by_anchor[binding["sourceAnchorId"]],
            )
            for binding in payload["locatorBindings"]
        )
        case = BlindCaseSubmissionV2(
            case_id=oracle_case.case_id,
            output=payload,
            telemetry=telemetry,
            locator_evidence=locator_evidence,
            fact_version_writes=0,
        )
        if mutate_case is not None:
            case = mutate_case(oracle_case.case_id, case)
        cases.append(case)
    return (
        BlindRunSubmissionV2(
            run_id="synthetic-v2-rubric-test",
            total_elapsed_ms=total_elapsed_ms,
            cases=tuple(cases),
            continued_after_absolute_stop=continued_after_absolute_stop,
        ),
        expected,
    )


def _replace_locator_bbox(payload: dict, anchor_id: str, bbox: dict) -> None:
    binding = next(
        item
        for item in payload["locatorBindings"]
        if item["sourceAnchorId"] == anchor_id
    )
    binding["locator"]["bbox"] = bbox


def _case(report: dict, case_id: str) -> dict:
    return next(row for row in report["cases"] if row["caseId"] == case_id)


def test_v2_freezes_guidance_thresholds_and_stays_hold() -> None:
    assert GATE_STATE == "HOLD"
    assert IMAGE_TARGET_COVERAGE_THRESHOLD == 0.80
    assert IMAGE_IOU_THRESHOLD == 0.50
    assert ABSOLUTE_STOP_CEILING_MS == 300_000.0
    assert set(HARD_RATE_THRESHOLDS.values()) == {1.0}
    assert dict(HARD_ZERO_THRESHOLDS) == {
        "unauthorizedFieldCount": 0,
        "factVersionWrites": 0,
    }
    assert dict(PARTIAL_WEIGHTS) == {
        "fieldAccuracyRate": 0.70,
        "latencyScore": 0.20,
        "retryEfficiency": 0.10,
    }
    assert PARTIAL_THRESHOLDS["minimumCarrierFieldAccuracyRate"] == 0.75
    assert PARTIAL_THRESHOLDS["weightedScore"] == 0.85


def test_perfect_oracle_evidence_is_eligible_but_not_finally_scored() -> None:
    submission, expected = _perfect_submission()
    report = score_blind_submission_v2(submission, expected)

    assert report["rubricVersion"] == "blind-eval-rubric-v2"
    assert report["gateState"] == "HOLD"
    assert report["finalDecision"] is None
    assert report["finalScoringExecuted"] is False
    assert report["thresholdEvaluation"]["eligibleAfterExplicitUnhold"] is True
    assert all(report["thresholdEvaluation"]["hardChecks"].values())
    assert all(report["thresholdEvaluation"]["partialChecks"].values())
    image_targets = _case(report, IMAGE_CASE_ID)["locatorTargets"]
    assert {row["semanticRole"] for row in image_targets} == {
        "image:focal-object",
        "image:caption",
    }
    assert all(row["controlledRegionExactReuse"] for row in image_targets)


def test_image_overlap_rule_accepts_non_exact_target_and_rejects_whole_image() -> None:
    focal = "anchor-image-equipment-focal"

    def passing_overlap(case_id: str, payload: dict) -> None:
        if case_id == IMAGE_CASE_ID:
            _replace_locator_bbox(
                payload,
                focal,
                {"x": 0.2, "y": 0.22, "width": 0.6, "height": 0.54},
            )

    def remove_controlled_reuse(case_id: str, case: BlindCaseSubmissionV2):
        if case_id != IMAGE_CASE_ID:
            return case
        return replace(
            case,
            locator_evidence=tuple(
                replace(item, controlled_region_id=None)
                if item.source_anchor_id == focal
                else item
                for item in case.locator_evidence
            ),
        )

    submission, expected = _perfect_submission(
        mutate_payload=passing_overlap,
        mutate_case=remove_controlled_reuse,
    )
    report = score_blind_submission_v2(submission, expected)
    focal_row = next(
        row
        for row in _case(report, IMAGE_CASE_ID)["locatorTargets"]
        if row["semanticRole"] == "image:focal-object"
    )
    assert focal_row["controlledRegionExactReuse"] is False
    assert focal_row["targetCoverage"] >= 0.80
    assert focal_row["iou"] >= 0.50
    assert focal_row["passed"] is True

    def whole_image(case_id: str, payload: dict) -> None:
        if case_id == IMAGE_CASE_ID:
            _replace_locator_bbox(
                payload,
                focal,
                {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
            )

    submission, expected = _perfect_submission(
        mutate_payload=whole_image,
        mutate_case=remove_controlled_reuse,
    )
    report = score_blind_submission_v2(submission, expected)
    focal_row = next(
        row
        for row in _case(report, IMAGE_CASE_ID)["locatorTargets"]
        if row["semanticRole"] == "image:focal-object"
    )
    assert focal_row["targetCoverage"] == 1.0
    assert focal_row["iou"] < 0.50
    assert focal_row["passed"] is False
    assert report["thresholdEvaluation"]["hardChecks"]["carrierLocatorRuleRate"] is False


def test_pdf_and_excel_locators_remain_exact() -> None:
    def mutate(case_id: str, payload: dict) -> None:
        if case_id == PDF_CASE_ID:
            payload["locatorBindings"][0]["locator"]["bbox"]["x"] += 0.001
        if case_id == EXCEL_CASE_ID:
            payload["locatorBindings"][0]["locator"]["range"] = "A1"

    submission, expected = _perfect_submission(mutate_payload=mutate)
    report = score_blind_submission_v2(submission, expected)

    assert _case(report, PDF_CASE_ID)["locatorTargets"][0]["passed"] is False
    assert _case(report, EXCEL_CASE_ID)["locatorTargets"][0]["passed"] is False
    assert report["metrics"]["locatorBindingOpenBoundsRate"] == 1.0
    assert report["metrics"]["carrierLocatorRuleRate"] < 1.0


def test_supported_extra_unresolved_is_full_credit_but_boilerplate_is_not() -> None:
    item_id = "extra-readable-nameplate-review"
    focal = "anchor-image-equipment-focal"

    def add_supported(case_id: str, payload: dict) -> None:
        if case_id != IMAGE_CASE_ID:
            return
        payload["result"]["unresolvedItems"] = [
            {
                "id": item_id,
                "kind": "unreadable_content",
                "question": "设备铭牌中的制造商和型号分别是什么？",
                "reason": "当前图像的铭牌文字不可辨，需要核对更清晰的原始图像。",
                "requiresHumanReview": True,
                "sourceAnchorIds": [focal],
            }
        ]

    def mark_relevant(case_id: str, case: BlindCaseSubmissionV2):
        if case_id != IMAGE_CASE_ID:
            return case
        return replace(
            case,
            locator_evidence=tuple(
                replace(item, relevant_unresolved_ids=frozenset({item_id}))
                if item.source_anchor_id == focal
                else item
                for item in case.locator_evidence
            ),
            unresolved_evidence=(
                UnresolvedAuditEvidenceV2(
                    item_id=item_id,
                    specific_reviewable_question=True,
                    verifiable_reason=True,
                ),
            ),
        )

    submission, expected = _perfect_submission(
        mutate_payload=add_supported,
        mutate_case=mark_relevant,
    )
    report = score_blind_submission_v2(submission, expected)
    assert report["metrics"]["criticalUnresolvedRecallRate"] == 1.0
    assert report["metrics"]["supportedExtraUnresolvedRate"] == 1.0

    def add_boilerplate(case_id: str, payload: dict) -> None:
        if case_id != IMAGE_CASE_ID:
            return
        add_supported(case_id, payload)
        payload["result"]["unresolvedItems"][0].update(
            {
                "question": "是否需要人工确认？",
                "reason": "无法确定，因此应拒绝该项目并触发 hard gate。",
            }
        )

    submission, expected = _perfect_submission(
        mutate_payload=add_boilerplate,
        mutate_case=mark_relevant,
    )
    report = score_blind_submission_v2(submission, expected)
    assert report["metrics"]["supportedExtraUnresolvedRate"] == 0.0
    assert report["thresholdEvaluation"]["hardChecks"]["supportedExtraUnresolvedRate"] is False


def test_critical_unresolved_recall_is_independent_from_supported_extras() -> None:
    submission, expected = _perfect_submission()
    image_expected = replace(
        expected[IMAGE_CASE_ID],
        critical_unresolved=(
            ExpectedCriticalUnresolvedV2(
                oracle_key="critical-nameplate",
                kind="unreadable_content",
                match_terms=("铭牌",),
            ),
        ),
    )
    altered_expected = dict(expected)
    altered_expected[IMAGE_CASE_ID] = image_expected
    report = score_blind_submission_v2(submission, altered_expected)

    assert report["metrics"]["criticalUnresolvedRecallRate"] == 0.0
    assert report["metrics"]["supportedExtraUnresolvedRate"] == 1.0


def test_per_case_telemetry_retry_and_absolute_stop_are_non_compensable() -> None:
    def missing_telemetry(case_id: str, case: BlindCaseSubmissionV2):
        return replace(case, telemetry=None) if case_id == PDF_CASE_ID else case

    submission, expected = _perfect_submission(mutate_case=missing_telemetry)
    report = score_blind_submission_v2(submission, expected)
    assert report["thresholdEvaluation"]["hardChecks"]["telemetryCompletenessRate"] is False
    assert report["thresholdEvaluation"]["hardChecks"]["retryPolicyComplianceRate"] is False

    def disallowed_retry(case_id: str, case: BlindCaseSubmissionV2):
        if case_id != PDF_CASE_ID:
            return case
        return replace(
            case,
            telemetry=replace(
                case.telemetry,
                attempt_count=2,
                retry_count=1,
                retry_error_codes=("schema_error",),
                retry_budget_sufficient=True,
            ),
        )

    submission, expected = _perfect_submission(mutate_case=disallowed_retry)
    report = score_blind_submission_v2(submission, expected)
    assert report["metrics"]["telemetryCompletenessRate"] == 1.0
    assert report["metrics"]["retryPolicyComplianceRate"] < 1.0

    submission, expected = _perfect_submission(
        total_elapsed_ms=ABSOLUTE_STOP_CEILING_MS + 1,
        continued_after_absolute_stop=True,
    )
    report = score_blind_submission_v2(submission, expected)
    assert report["metrics"]["absoluteStopComplianceRate"] == 0.0
    assert report["thresholdEvaluation"]["eligibleAfterExplicitUnhold"] is False


def test_only_three_provider_codes_and_one_retry_can_pass() -> None:
    def allowed_retry(case_id: str, case: BlindCaseSubmissionV2):
        if case_id != PDF_CASE_ID:
            return case
        return replace(
            case,
            telemetry=replace(
                case.telemetry,
                attempt_count=2,
                retry_count=1,
                retry_error_codes=("timeout",),
                retry_budget_sufficient=True,
            ),
        )

    submission, expected = _perfect_submission(mutate_case=allowed_retry)
    report = score_blind_submission_v2(submission, expected)
    assert report["metrics"]["telemetryCompletenessRate"] == 1.0
    assert report["metrics"]["retryPolicyComplianceRate"] == 1.0
    assert report["metrics"]["retryCount"] == 1


def test_truth_metadata_authority_fields_and_fact_writes_are_hard_gates() -> None:
    def add_authority(case_id: str, payload: dict) -> None:
        if case_id == IMAGE_CASE_ID:
            payload["result"]["scoreGrade"] = "A"

    def alter_case(case_id: str, case: BlindCaseSubmissionV2):
        if case_id != IMAGE_CASE_ID:
            return case
        return replace(
            case,
            fact_version_writes=1,
            not_a_provider_call=False,
        )

    submission, expected = _perfect_submission(
        mutate_payload=add_authority,
        mutate_case=alter_case,
    )
    report = score_blind_submission_v2(submission, expected)
    hard = report["thresholdEvaluation"]["hardChecks"]

    assert report["metrics"]["unauthorizedFieldCount"] == 1
    assert report["metrics"]["factVersionWrites"] == 1
    assert hard["schemaValidRate"] is False
    assert hard["truthMetadataRate"] is False
    assert hard["unauthorizedFieldCount"] is False
    assert hard["factVersionWrites"] is False


def test_closed_locator_evidence_breaks_open_bounds_and_scene_linkage() -> None:
    focal = "anchor-image-equipment-focal"

    def close_focal(case_id: str, case: BlindCaseSubmissionV2):
        if case_id != IMAGE_CASE_ID:
            return case
        return replace(
            case,
            locator_evidence=tuple(
                replace(item, openable=False)
                if item.source_anchor_id == focal
                else item
                for item in case.locator_evidence
            ),
        )

    submission, expected = _perfect_submission(mutate_case=close_focal)
    report = score_blind_submission_v2(submission, expected)
    hard = report["thresholdEvaluation"]["hardChecks"]
    assert hard["locatorBindingOpenBoundsRate"] is False
    assert hard["carrierLocatorRuleRate"] is False
    assert hard["sceneSpecSafetyLinkageRate"] is False


def test_v1_evidence_and_prompt_snapshot_remain_byte_identical() -> None:
    for file_name, expected_hash in V1_HASHES.items():
        assert hashlib.sha256((EVAL_ROOT / file_name).read_bytes()).hexdigest() == expected_hash

    report = json.loads(
        (EVAL_ROOT / "BLIND-EVAL-SCORING-REPORT.json").read_text(encoding="utf-8")
    )
    snapshot_hash = hashlib.sha256(
        (EVAL_ROOT / "codex_oracle/prompt_template_v1.snapshot.md").read_bytes()
    ).hexdigest()
    assert snapshot_hash == report["sourceVerification"]["promptSha256"]

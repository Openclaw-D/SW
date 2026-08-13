from __future__ import annotations

import copy
from collections.abc import Callable

from evals.model_gateway.blind_eval_rubric import (
    GATE_STATE,
    HARD_RATE_THRESHOLDS,
    HARD_ZERO_THRESHOLDS,
    PARTIAL_THRESHOLDS,
    BlindCaseSubmission,
    BlindRunSubmission,
    expected_cases_from_hidden_truth,
    expected_cases_from_oracle,
    score_blind_submission,
)
from evals.model_gateway.codex_oracle import load_oracle_fixture
from evals.model_gateway.dataset import load_hidden_truth, load_public_cases
from evals.model_gateway.fake_provider import calculate_public_input_hash


def _oracle_submission(
    *,
    mutate: Callable[[int, dict], None] | None = None,
    fact_version_writes: int = 0,
    retry_error_codes: tuple[str, ...] = (),
) -> tuple[BlindRunSubmission, object]:
    fixture = load_oracle_fixture()
    cases = []
    for index, oracle_case in enumerate(fixture.replay_cases):
        payload = oracle_case.expected_output.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        if mutate is not None:
            mutate(index, payload)
        cases.append(
            BlindCaseSubmission(
                case_id=oracle_case.case_id,
                output=payload,
                elapsed_ms=12_000.0 + index * 1_000.0,
                retry_error_codes=retry_error_codes if index == 0 else (),
                fact_version_writes=fact_version_writes if index == 0 else 0,
                openable_source_anchor_ids=frozenset(
                    binding.source_anchor_id
                    for binding in oracle_case.expected_output.locator_bindings
                ),
            )
        )
    return (
        BlindRunSubmission(
            run_id="synthetic-test-run",
            total_elapsed_ms=40_000.0,
            cases=tuple(cases),
        ),
        fixture,
    )


def test_rubric_freezes_hard_and_partial_thresholds() -> None:
    assert GATE_STATE == "HOLD"
    assert set(HARD_RATE_THRESHOLDS) == {
        "schemaValidRate",
        "materialBindingHashRate",
        "numericCorrectnessRate",
        "unitCorrectnessRate",
        "locatorExactnessRate",
        "locatorOpenabilityRate",
        "unresolvedHonestyRate",
        "sceneSpecSafetyLinkageRate",
        "telemetryCompletenessRate",
        "retryPolicyComplianceRate",
    }
    assert set(HARD_RATE_THRESHOLDS.values()) == {1.0}
    assert dict(HARD_ZERO_THRESHOLDS) == {
        "unauthorizedFieldCount": 0,
        "factVersionWrites": 0,
    }
    assert dict(PARTIAL_THRESHOLDS) == {
        "fieldAccuracyRate": 0.85,
        "minimumCarrierFieldAccuracyRate": 0.75,
        "latencyScore": 0.50,
        "weightedScore": 0.85,
    }


def test_perfect_oracle_replay_is_eligible_but_final_gate_remains_hold() -> None:
    submission, fixture = _oracle_submission()
    report = score_blind_submission(
        submission, expected_cases_from_oracle(fixture)
    )

    assert report["gateState"] == "HOLD"
    assert report["finalDecision"] is None
    assert report["finalScoringExecuted"] is False
    assert report["thresholdEvaluation"]["eligibleAfterExplicitUnhold"] is True
    assert all(report["thresholdEvaluation"]["hardChecks"].values())
    assert all(report["thresholdEvaluation"]["partialChecks"].values())
    assert report["metrics"]["unauthorizedFieldCount"] == 0
    assert report["metrics"]["factVersionWrites"] == 0
    assert report["metrics"]["totalElapsedMs"] == 40_000.0
    assert set(report["metrics"]["carrierLatency"]) == {"excel", "image", "pdf"}
    assert report["metrics"]["retryCount"] == 0
    assert report["ignoredAsAnswers"] == [
        "scoreGrade",
        "decisionGrade",
        "confidence",
        "hardGate",
    ]


def test_missing_field_gets_partial_score_without_weakening_hard_correctness() -> None:
    def remove_one_candidate(index: int, payload: dict) -> None:
        if index == 0:
            payload["result"]["extractedFieldCandidates"].pop()

    submission, fixture = _oracle_submission(mutate=remove_one_candidate)
    report = score_blind_submission(
        submission, expected_cases_from_oracle(fixture)
    )

    assert 0 < report["metrics"]["fieldAccuracyRate"] < 1
    assert report["metrics"]["numericCorrectnessRate"] == 1.0
    assert report["metrics"]["unitCorrectnessRate"] == 1.0
    assert report["metrics"]["locatorExactnessRate"] == 1.0
    assert report["gateState"] == "HOLD"


def test_confidence_is_not_an_answer_and_unresolved_must_match_oracle() -> None:
    def alter_non_answer_and_unresolved(index: int, payload: dict) -> None:
        payload["result"]["confidence"] = 0.01
        if index == 0:
            payload["result"]["unresolvedItems"] = [
                {
                    "id": "unexpected-unresolved",
                    "kind": "ambiguous_content",
                    "question": "是否需要人工确认？",
                    "reason": "Oracle 未声明该未决项。",
                    "requiresHumanReview": True,
                    "sourceAnchorIds": [],
                }
            ]

    submission, fixture = _oracle_submission(mutate=alter_non_answer_and_unresolved)
    report = score_blind_submission(
        submission, expected_cases_from_oracle(fixture)
    )

    assert report["metrics"]["fieldAccuracyRate"] == 1.0
    assert report["metrics"]["unresolvedHonestyRate"] < 1.0
    assert (
        report["thresholdEvaluation"]["hardChecks"]["unresolvedHonestyRate"]
        is False
    )


def test_wrong_numeric_unit_locator_and_hash_each_break_a_100_percent_gate() -> None:
    def corrupt(index: int, payload: dict) -> None:
        if index != 1:
            return
        candidate = payload["result"]["extractedFieldCandidates"][2]
        candidate["value"] = 999
        candidate["unit"] = "件"
        payload["locatorBindings"][2]["locator"]["range"] = "G4"
        payload["inputHash"] = "f" * 64
        payload["result"]["inputHash"] = "f" * 64

    submission, fixture = _oracle_submission(mutate=corrupt)
    report = score_blind_submission(
        submission, expected_cases_from_oracle(fixture)
    )
    hard = report["thresholdEvaluation"]["hardChecks"]

    assert hard["materialBindingHashRate"] is False
    assert hard["numericCorrectnessRate"] is False
    assert hard["unitCorrectnessRate"] is False
    assert hard["locatorExactnessRate"] is False
    assert report["thresholdEvaluation"]["eligibleAfterExplicitUnhold"] is False


def test_authority_field_fact_write_and_bad_retry_are_zero_tolerance() -> None:
    def add_authority(index: int, payload: dict) -> None:
        if index == 0:
            payload["result"]["scoreGrade"] = "A"

    submission, fixture = _oracle_submission(
        mutate=add_authority,
        fact_version_writes=1,
        retry_error_codes=("validation_error", "timeout"),
    )
    report = score_blind_submission(
        submission, expected_cases_from_oracle(fixture)
    )
    hard = report["thresholdEvaluation"]["hardChecks"]

    assert report["metrics"]["unauthorizedFieldCount"] == 1
    assert report["metrics"]["factVersionWrites"] == 1
    assert hard["schemaValidRate"] is False
    assert hard["retryPolicyComplianceRate"] is False
    assert hard["unauthorizedFieldCount"] is False
    assert hard["factVersionWrites"] is False


def test_locator_openability_and_scene_linkage_are_hard_gates() -> None:
    submission, fixture = _oracle_submission()
    cases = list(submission.cases)
    image_index = next(
        index
        for index, case in enumerate(fixture.replay_cases)
        if case.case_id == "project-01-image-scene"
    )
    image_submission = cases[image_index]
    payload = copy.deepcopy(dict(image_submission.output))
    hotspot_anchor = payload["result"]["sceneSpec"]["hotspots"][0][
        "sourceAnchorId"
    ]
    payload["locatorBindings"] = [
        binding
        for binding in payload["locatorBindings"]
        if binding["sourceAnchorId"] != hotspot_anchor
    ]
    cases[image_index] = BlindCaseSubmission(
        case_id=image_submission.case_id,
        output=payload,
        elapsed_ms=image_submission.elapsed_ms,
        retry_error_codes=(),
        fact_version_writes=0,
        openable_source_anchor_ids=frozenset(),
    )
    altered = BlindRunSubmission(
        run_id=submission.run_id,
        total_elapsed_ms=submission.total_elapsed_ms,
        cases=tuple(cases),
    )
    report = score_blind_submission(altered, expected_cases_from_oracle(fixture))
    hard = report["thresholdEvaluation"]["hardChecks"]

    assert hard["locatorOpenabilityRate"] is False
    assert hard["sceneSpecSafetyLinkageRate"] is False


def test_existing_24_case_hidden_truth_adapts_without_blind_run_io() -> None:
    public_cases = load_public_cases()
    expected = expected_cases_from_hidden_truth(public_cases, load_hidden_truth())

    assert len(expected) == 24
    assert {case.media_kind for case in expected.values()} == {"image"}
    assert all(case.scene_spec_required for case in expected.values())
    assert all(len(case.fields) == 3 for case in expected.values())
    first = public_cases[0]
    assert expected[first.case_id].content_hash == first.provider_input["contentHash"]
    assert expected[first.case_id].input_hash == calculate_public_input_hash(
        first.provider_input
    )
    assert expected[first.case_id].input_hash != expected[first.case_id].content_hash

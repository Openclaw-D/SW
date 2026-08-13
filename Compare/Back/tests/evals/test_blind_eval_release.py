from __future__ import annotations

import json

from evals.model_gateway.blind_eval_release import (
    BLIND_RUN_ROOT,
    load_blind_artifacts,
    score_completed_blind_run,
)


def test_completed_blind_artifacts_parse_without_mutation() -> None:
    before = {
        path.name: path.read_bytes()
        for path in BLIND_RUN_ROOT.iterdir()
        if path.is_file()
    }
    artifacts = load_blind_artifacts()

    assert len(artifacts.requests) == 3
    assert len(artifacts.outputs) == 3
    assert set(artifacts.requests) == set(artifacts.outputs)
    assert {
        path.name: path.read_bytes()
        for path in BLIND_RUN_ROOT.iterdir()
        if path.is_file()
    } == before


def test_explicit_unhold_uses_frozen_thresholds_and_returns_fail() -> None:
    report = score_completed_blind_run()
    metrics = report["metrics"]
    hard = report["thresholdEvaluation"]["hardChecks"]
    partial = report["thresholdEvaluation"]["partialChecks"]

    assert report["rubricVersion"] == "blind-eval-rubric-v1"
    assert report["rubricGateStateAtFreeze"] == "HOLD"
    assert report["gateState"] == "UNHELD"
    assert report["finalScoringExecuted"] is True
    assert report["finalDecision"] == "FAIL"
    assert report["thresholdEvaluation"]["eligibleAfterExplicitUnhold"] is False

    assert metrics["schemaValidRate"] == 1.0
    assert metrics["materialBindingHashRate"] == 1.0
    assert metrics["fieldAccuracyRate"] == 0.909091
    assert metrics["carrierFieldAccuracy"] == {
        "excel": 1.0,
        "image": 0.0,
        "pdf": 1.0,
    }
    assert metrics["numericCorrectnessRate"] == 1.0
    assert metrics["unitCorrectnessRate"] == 1.0
    assert metrics["locatorExactnessRate"] == 0.777778
    assert metrics["locatorOpenabilityRate"] == 1.0
    assert metrics["unresolvedHonestyRate"] == 0.666667
    assert metrics["sceneSpecSafetyLinkageRate"] == 1.0
    assert metrics["unauthorizedFieldCount"] == 0
    assert metrics["factVersionWrites"] == 0
    assert metrics["totalElapsedMs"] == 782232.0
    assert metrics["retryCount"] == 8
    assert metrics["latencyScore"] == 0.6375
    assert metrics["weightedScore"] == 0.763864

    assert hard["locatorExactnessRate"] is False
    assert hard["unresolvedHonestyRate"] is False
    assert hard["telemetryCompletenessRate"] is False
    assert hard["retryPolicyComplianceRate"] is False
    assert partial["fieldAccuracyRate"] is True
    assert partial["minimumCarrierFieldAccuracyRate"] is False
    assert partial["latencyScore"] is True
    assert partial["weightedScore"] is False


def test_report_records_source_and_telemetry_evidence() -> None:
    report = score_completed_blind_run()

    assert report["sourceVerification"]["promptHashValid"] is True
    assert report["sourceVerification"]["promptSha256"] == (
        "14659ba177ba35c2064d3bd6b4f5b3e47eaac8fd86f8217eabf79a7a5cb3e184"
    )
    assert report["sourceVerification"]["allMaterialHashesValid"] is True
    assert report["sourceVerification"]["allInputHashesValid"] is True
    assert report["telemetryEvidence"]["failureCount"] == 8
    assert report["telemetryEvidence"]["retryCount"] == 8
    assert report["telemetryEvidence"]["perCaseAttributionAvailable"] is False
    assert report["telemetryEvidence"]["retryCodesAvailable"] is False
    assert sum(
        report["telemetryEvidence"]["conservativeRetryAllocation"].values()
    ) == 8
    assert all(
        not row["retryPolicyCompliant"] for row in report["cases"]
    )
    assert all(
        not evidence["rejectedSourceAnchorIds"]
        for evidence in report["telemetryEvidence"]["locatorOpenability"].values()
    )

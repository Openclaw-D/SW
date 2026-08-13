from __future__ import annotations

from evals.model_gateway.blind_eval_release_v3 import score_sealed_r3


def test_r3_semantic_and_provider_replay_gates_pass_independently() -> None:
    report = score_sealed_r3()

    assert report["rubricVersion"] == "blind-eval-rubric-v2"
    assert report["gateState"] == "UNHELD"
    assert report["semanticGatePassed"] is True
    assert report["providerReplayGate"]["passed"] is True
    assert report["providerReplayGate"]["passedCases"] == 3
    assert report["finalDecision"] == "PASS"


def test_r3_semantic_metrics_preserve_frozen_thresholds() -> None:
    report = score_sealed_r3()
    metrics = report["metrics"]
    hard = report["thresholdEvaluation"]["hardChecks"]
    partial = report["thresholdEvaluation"]["partialChecks"]

    assert metrics["fieldAccuracyRate"] == 0.928571
    assert metrics["carrierFieldAccuracy"] == {
        "excel": 0.857143,
        "image": 1.0,
        "pdf": 1.0,
    }
    assert metrics["numericCorrectnessRate"] == 1.0
    assert metrics["unitCorrectnessRate"] == 1.0
    assert metrics["locatorBindingOpenBoundsRate"] == 1.0
    assert metrics["carrierLocatorRuleRate"] == 1.0
    assert metrics["criticalUnresolvedRecallRate"] == 1.0
    assert metrics["supportedExtraUnresolvedRate"] == 1.0
    assert metrics["sceneSpecSafetyLinkageRate"] == 1.0
    assert metrics["telemetryCompletenessRate"] == 1.0
    assert metrics["retryPolicyComplianceRate"] == 1.0
    assert metrics["absoluteStopComplianceRate"] == 1.0
    assert metrics["unauthorizedFieldCount"] == 0
    assert metrics["factVersionWrites"] == 0
    assert metrics["totalElapsedMs"] == 282735.0
    assert metrics["weightedScore"] >= 0.85
    assert all(hard.values())
    assert all(partial.values())


def test_local_input_selection_error_is_not_a_provider_retry() -> None:
    report = score_sealed_r3()
    process = report["processQuality"]

    assert process["inputSelectionErrorCount"] == 1
    assert process["allExcludedFromOutput"] is True
    assert process["providerRetryCountImpact"] == 0
    assert process["gatePassed"] is True
    assert report["metrics"]["retryCount"] == 0
    assert report["providerReplayGate"]["externalNetworkCalls"] == 0
    assert report["providerReplayGate"]["realExternalProviderCall"] is False

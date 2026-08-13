from __future__ import annotations

import asyncio

from evals.model_gateway.dataset import load_hidden_truth, load_public_cases
from evals.model_gateway.fake_provider import OfflineSyntheticFakeProvider
from evals.model_gateway.metrics import aggregate_metrics, evaluate_case


def test_fake_output_passes_all_release_metrics_and_remains_candidate_only() -> None:
    case = load_public_cases()[0]
    truth = load_hidden_truth()[case.case_id]
    provider = OfflineSyntheticFakeProvider()
    result = asyncio.run(provider.predict(case.provider_input))

    metrics = evaluate_case(
        case, result, truth, provider_advisory_only=provider.advisory_only
    )
    aggregate = aggregate_metrics([metrics])

    assert aggregate["passed"] is True
    assert aggregate["fieldAccuracy"] == 1.0
    assert aggregate["locatorValidity"] == 1.0
    assert aggregate["schemaPassRate"] == 1.0
    assert aggregate["sceneSpecSafetyRate"] == 1.0
    assert aggregate["candidateHumanConfirmationIsolationRate"] == 1.0
    assert all(item["status"] == "candidate" for item in result["extractedFieldCandidates"])
    assert result["isSimulated"] is True


def test_invalid_schema_and_unsafe_authority_output_fail_closed() -> None:
    case = load_public_cases()[0]
    truth = load_hidden_truth()[case.case_id]
    provider = OfflineSyntheticFakeProvider()
    result = asyncio.run(provider.predict(case.provider_input))
    result["sceneSpec"]["script"] = "synthetic forbidden content"
    result["scoreGrade"] = "A"

    metrics = evaluate_case(
        case, result, truth, provider_advisory_only=provider.advisory_only
    )

    assert metrics.schema_passed is False
    assert metrics.scene_spec_safe is False
    assert metrics.candidate_confirmation_isolated is False


def test_wrong_locator_is_measured_separately_from_correct_field() -> None:
    case = load_public_cases()[0]
    truth = load_hidden_truth()[case.case_id]
    provider = OfflineSyntheticFakeProvider()
    result = asyncio.run(provider.predict(case.provider_input))
    result["sourceAnchors"][0]["bbox"] = {
        "x": 0.6,
        "y": 0.7,
        "width": 0.1,
        "height": 0.1,
    }

    metrics = evaluate_case(
        case, result, truth, provider_advisory_only=provider.advisory_only
    )

    assert metrics.correct_fields == metrics.field_checks
    assert metrics.valid_locators == metrics.locator_checks - 1

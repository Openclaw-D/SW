"""Metrics for exact fields, locators, schema, SceneSpec and human Gate isolation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pydantic import ValidationError

from app.contracts.material_intelligence import (
    MaterialIntelligenceRequest,
    MaterialIntelligenceResult,
    validate_material_intelligence_result,
)

from .dataset import HiddenGoldenTruth, PublicEvalCase
from .fake_provider import calculate_public_input_hash


FORBIDDEN_AUTHORITY_KEYS = {
    "approvalstatus",
    "authoritative",
    "confirmed",
    "decisiongrade",
    "factvalue",
    "factversion",
    "hardgate",
    "hardgatedecision",
    "scoregrade",
}
FORBIDDEN_SCENE_KEYS = {"code", "html", "javascript", "script", "shader", "url"}


@dataclass(frozen=True, slots=True)
class CaseMetrics:
    case_id: str
    schema_passed: bool
    correct_fields: int
    field_checks: int
    valid_locators: int
    locator_checks: int
    scene_spec_safe: bool
    candidate_confirmation_isolated: bool
    errors: tuple[str, ...]


def evaluate_case(
    case: PublicEvalCase,
    raw_result: object,
    truth: HiddenGoldenTruth,
    *,
    provider_advisory_only: bool,
) -> CaseMetrics:
    errors: list[str] = []
    expected_hash = calculate_public_input_hash(case.provider_input)
    request = MaterialIntelligenceRequest.model_validate(
        {
            "projectId": case.provider_input["projectId"],
            "materialId": case.provider_input["materialId"],
            "materialVersionId": case.provider_input["materialVersionId"],
            "contentHash": case.provider_input["contentHash"],
            "mediaKind": case.provider_input["mediaKind"],
            "contextVersion": case.provider_input["contextVersion"],
            "taskGoals": case.provider_input["taskGoals"],
            "locale": case.provider_input["locale"],
            "dataClassification": case.provider_input["dataClassification"],
            "usageAuthorizationRef": None,
        }
    )
    try:
        result = MaterialIntelligenceResult.model_validate(raw_result)
        validate_material_intelligence_result(
            request, result, expected_input_hash=expected_hash
        )
    except (ValidationError, ValueError, TypeError) as error:
        return CaseMetrics(
            case_id=case.case_id,
            schema_passed=False,
            correct_fields=0,
            field_checks=len(truth.expected_fields),
            valid_locators=0,
            locator_checks=len(truth.expected_fields),
            scene_spec_safe=False,
            candidate_confirmation_isolated=False,
            errors=(f"schema:{type(error).__name__}",),
        )

    candidates = {item.field_key: item for item in result.extracted_field_candidates}
    anchors = {
        item.id: item.model_dump(mode="json", by_alias=True)
        for item in result.source_anchors
    }
    regions = {item["fieldKey"]: item for item in case.provider_input["regions"]}
    correct_fields = 0
    valid_locators = 0
    for field_key, expected in truth.expected_fields.items():
        candidate = candidates.get(field_key)
        if candidate is None:
            errors.append(f"missing-field:{field_key}")
            continue
        if candidate.value == expected:
            correct_fields += 1
        else:
            errors.append(f"field-mismatch:{field_key}")
        region = regions[field_key]
        expected_anchor_id = region["anchorId"]
        returned_anchor = anchors.get(expected_anchor_id)
        if (
            candidate.source_anchor_ids == [expected_anchor_id]
            and returned_anchor is not None
            and returned_anchor.get("bbox") == region["bbox"]
            and returned_anchor.get("materialId") == case.provider_input["materialId"]
            and returned_anchor.get("materialVersionId")
            == case.provider_input["materialVersionId"]
            and returned_anchor.get("contentHash") == case.provider_input["contentHash"]
        ):
            valid_locators += 1
        else:
            errors.append(f"locator-invalid:{field_key}")

    serialized = result.model_dump(mode="json", by_alias=True)
    scene_keys = set(_normalized_keys(serialized.get("sceneSpec")))
    scene_safe = result.scene_spec is not None and not (
        scene_keys & FORBIDDEN_SCENE_KEYS
    )
    if not scene_safe:
        errors.append("scene-spec-unsafe")

    authority_keys = set(_normalized_keys(serialized)) & FORBIDDEN_AUTHORITY_KEYS
    confirmation_isolated = (
        provider_advisory_only
        and result.is_simulated is True
        and result.model_info is not None
        and result.model_info.provider == "compare-eval-fake"
        and all(item.status.value == "candidate" for item in candidates.values())
        and not authority_keys
    )
    if not confirmation_isolated:
        errors.append("candidate-confirmation-isolation-failed")

    return CaseMetrics(
        case_id=case.case_id,
        schema_passed=True,
        correct_fields=correct_fields,
        field_checks=len(truth.expected_fields),
        valid_locators=valid_locators,
        locator_checks=len(truth.expected_fields),
        scene_spec_safe=scene_safe,
        candidate_confirmation_isolated=confirmation_isolated,
        errors=tuple(errors),
    )


def aggregate_metrics(cases: Iterable[CaseMetrics]) -> dict[str, Any]:
    results = tuple(cases)
    total_cases = len(results)
    field_checks = sum(item.field_checks for item in results)
    locator_checks = sum(item.locator_checks for item in results)
    metrics = {
        "caseCount": total_cases,
        "fieldAccuracy": _rate(sum(item.correct_fields for item in results), field_checks),
        "locatorValidity": _rate(
            sum(item.valid_locators for item in results), locator_checks
        ),
        "schemaPassRate": _rate(
            sum(item.schema_passed for item in results), total_cases
        ),
        "sceneSpecSafetyRate": _rate(
            sum(item.scene_spec_safe for item in results), total_cases
        ),
        "candidateHumanConfirmationIsolationRate": _rate(
            sum(item.candidate_confirmation_isolated for item in results), total_cases
        ),
    }
    metrics["passed"] = all(value == 1.0 for key, value in metrics.items() if key != "caseCount")
    metrics["failures"] = [
        {"caseId": item.case_id, "errors": list(item.errors)}
        for item in results
        if item.errors
    ]
    return metrics


def _normalized_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key).replace("_", "").lower()
            yield from _normalized_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _normalized_keys(item)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0

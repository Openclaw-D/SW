"""Frozen BlindEval rubric and in-memory scorer.

This module never discovers or reads a blind-run directory. Callers must pass
blind outputs and telemetry explicitly after the independent run is complete.
The frozen state remains HOLD, so the scorer reports eligibility evidence but
never emits a final release decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from statistics import median
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from pydantic import ValidationError

from app.contracts.model_gateway import ModelGatewayOutput

from .dataset import HiddenGoldenTruth, PublicEvalCase
from .fake_provider import calculate_public_input_hash


RUBRIC_VERSION = "blind-eval-rubric-v1"
GATE_STATE = "HOLD"

FORBIDDEN_ANSWER_KEYS = frozenset(
    {
        "approvalstatus",
        "authoritative",
        "confirmed",
        "decisiongrade",
        "factvalue",
        "factversion",
        "factversionid",
        "hardgate",
        "hardgatedecision",
        "policydecision",
        "reviewtransition",
        "scoregrade",
    }
)
FORBIDDEN_SCENE_KEYS = frozenset(
    {"code", "html", "javascript", "script", "shader", "url"}
)
RETRYABLE_ERROR_CODES = frozenset(
    {"rate_limited", "timeout", "provider_unavailable"}
)

HARD_RATE_THRESHOLDS = MappingProxyType(
    {
        "schemaValidRate": 1.0,
        "materialBindingHashRate": 1.0,
        "numericCorrectnessRate": 1.0,
        "unitCorrectnessRate": 1.0,
        "locatorExactnessRate": 1.0,
        "locatorOpenabilityRate": 1.0,
        "unresolvedHonestyRate": 1.0,
        "sceneSpecSafetyLinkageRate": 1.0,
        "telemetryCompletenessRate": 1.0,
        "retryPolicyComplianceRate": 1.0,
    }
)
HARD_ZERO_THRESHOLDS = MappingProxyType(
    {"unauthorizedFieldCount": 0, "factVersionWrites": 0}
)
PARTIAL_THRESHOLDS = MappingProxyType(
    {
        "fieldAccuracyRate": 0.85,
        "minimumCarrierFieldAccuracyRate": 0.75,
        "latencyScore": 0.50,
        "weightedScore": 0.85,
    }
)
PARTIAL_WEIGHTS = MappingProxyType(
    {"fieldAccuracyRate": 0.70, "latencyScore": 0.20, "retryEfficiency": 0.10}
)

TOTAL_LATENCY_TARGET_MS = 180_000.0
TOTAL_LATENCY_CEILING_MS = 300_000.0
CARRIER_LATENCY_TARGET_MS = MappingProxyType(
    {
        "image": 60_000.0,
        "pdf": 90_000.0,
        "excel": 90_000.0,
        "document": 90_000.0,
        "media": 120_000.0,
    }
)
CARRIER_LATENCY_CEILING_MS = MappingProxyType(
    {key: value * 2 for key, value in CARRIER_LATENCY_TARGET_MS.items()}
)
MAX_RETRIES_PER_CASE = 1


@dataclass(frozen=True, slots=True)
class ExpectedField:
    field_key: str
    value: Any
    unit: str | None
    locator: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class ExpectedBlindCase:
    case_id: str
    project_id: str
    material_id: str
    material_version_id: str
    content_hash: str
    input_hash: str
    media_kind: str
    fields: Mapping[str, ExpectedField]
    locators: Mapping[str, Mapping[str, Any]]
    unresolved_kinds: tuple[str, ...]
    scene_spec_required: bool


@dataclass(frozen=True, slots=True)
class BlindCaseSubmission:
    case_id: str
    output: Mapping[str, Any]
    elapsed_ms: float
    retry_error_codes: tuple[str, ...]
    fact_version_writes: int
    openable_source_anchor_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be blank")
        if not math.isfinite(self.elapsed_ms) or self.elapsed_ms <= 0:
            raise ValueError("elapsed_ms must be finite and positive")
        if self.fact_version_writes < 0:
            raise ValueError("fact_version_writes must not be negative")


@dataclass(frozen=True, slots=True)
class BlindRunSubmission:
    run_id: str
    total_elapsed_ms: float
    cases: tuple[BlindCaseSubmission, ...]

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be blank")
        if not math.isfinite(self.total_elapsed_ms) or self.total_elapsed_ms <= 0:
            raise ValueError("total_elapsed_ms must be finite and positive")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("BlindRunSubmission case ids must be unique")


def expected_cases_from_oracle(fixture: Any) -> Mapping[str, ExpectedBlindCase]:
    """Project a validated Oracle fixture into answer-only scoring inputs."""

    expected: dict[str, ExpectedBlindCase] = {}
    for case in fixture.replay_cases:
        result = case.expected_output.result
        if result is None:
            raise ValueError(f"oracle case lacks a result: {case.case_id}")
        locator_by_anchor = {
            binding.source_anchor_id: _canonical_locator(binding.locator)
            for binding in case.expected_output.locator_bindings
        }
        fields = {
            candidate.field_key: ExpectedField(
                field_key=candidate.field_key,
                value=candidate.value,
                unit=candidate.unit,
                locator=locator_by_anchor.get(candidate.source_anchor_ids[0]),
            )
            for candidate in result.extracted_field_candidates
        }
        expected[case.case_id] = ExpectedBlindCase(
            case_id=case.case_id,
            project_id=case.request.material.project_id,
            material_id=case.request.material.material_id,
            material_version_id=case.request.material.material_version_id,
            content_hash=case.request.material.content_hash,
            input_hash=case.request.input_hash,
            media_kind=case.request.material.media_kind.value,
            fields=MappingProxyType(fields),
            locators=MappingProxyType(locator_by_anchor),
            unresolved_kinds=tuple(sorted(item.kind.value for item in result.unresolved_items)),
            scene_spec_required=result.scene_spec is not None,
        )
    return MappingProxyType(expected)


def expected_cases_from_hidden_truth(
    public_cases: Sequence[PublicEvalCase],
    truths: Mapping[str, HiddenGoldenTruth],
) -> Mapping[str, ExpectedBlindCase]:
    """Adapt the existing 24-case hidden truth without exposing it to a provider."""

    expected: dict[str, ExpectedBlindCase] = {}
    for case in public_cases:
        truth = truths[case.case_id]
        regions = {item["fieldKey"]: item for item in case.provider_input["regions"]}
        fields = {}
        locators = {}
        for field_key, value in truth.expected_fields.items():
            region = regions[field_key]
            locator = MappingProxyType(
                {
                    "kind": case.provider_input["mediaKind"],
                    "materialId": case.provider_input["materialId"],
                    "materialVersionId": case.provider_input["materialVersionId"],
                    "page": 1,
                    "bbox": dict(region["bbox"]),
                }
            )
            locators[region["anchorId"]] = locator
            fields[field_key] = ExpectedField(
                field_key=field_key,
                value=value,
                unit=region["unit"],
                locator=locator,
            )
        expected[case.case_id] = ExpectedBlindCase(
            case_id=case.case_id,
            project_id=case.provider_input["projectId"],
            material_id=case.provider_input["materialId"],
            material_version_id=case.provider_input["materialVersionId"],
            content_hash=case.provider_input["contentHash"],
            input_hash=calculate_public_input_hash(case.provider_input),
            media_kind=case.provider_input["mediaKind"],
            fields=MappingProxyType(fields),
            locators=MappingProxyType(locators),
            unresolved_kinds=(),
            scene_spec_required="scene_spec" in case.provider_input["taskGoals"],
        )
    return MappingProxyType(expected)


def score_blind_submission(
    submission: BlindRunSubmission,
    expected_cases: Mapping[str, ExpectedBlindCase],
) -> dict[str, Any]:
    """Compute frozen rubric evidence while keeping the final Gate on HOLD."""

    submitted_by_id = {case.case_id: case for case in submission.cases}
    expected_ids = set(expected_cases)
    submitted_ids = set(submitted_by_id)
    telemetry_complete = expected_ids == submitted_ids
    case_rows = [
        _score_case(submitted_by_id.get(case_id), expected_cases[case_id])
        for case_id in sorted(expected_ids)
    ]
    unexpected_case_ids = sorted(submitted_ids - expected_ids)
    unauthorized_count = sum(row["unauthorizedFieldCount"] for row in case_rows)
    fact_writes = sum(row["factVersionWrites"] for row in case_rows)
    retry_count = sum(row["retryCount"] for row in case_rows)
    case_count = len(case_rows)

    metrics = {
        "schemaValidRate": _mean_bool(row["schemaValid"] for row in case_rows),
        "materialBindingHashRate": _mean_bool(
            row["materialBindingHashValid"] for row in case_rows
        ),
        "fieldAccuracyRate": _fraction(
            sum(row["correctFields"] for row in case_rows),
            sum(row["fieldChecks"] for row in case_rows),
        ),
        "numericCorrectnessRate": _fraction(
            sum(row["correctNumericValues"] for row in case_rows),
            sum(row["numericChecks"] for row in case_rows),
        ),
        "unitCorrectnessRate": _fraction(
            sum(row["correctUnits"] for row in case_rows),
            sum(row["unitChecks"] for row in case_rows),
        ),
        "locatorExactnessRate": _fraction(
            sum(row["exactLocators"] for row in case_rows),
            sum(row["locatorChecks"] for row in case_rows),
        ),
        "locatorOpenabilityRate": _fraction(
            sum(row["openableLocators"] for row in case_rows),
            sum(row["openabilityChecks"] for row in case_rows),
        ),
        "unresolvedHonestyRate": _mean_bool(
            row["unresolvedHonest"] for row in case_rows
        ),
        "sceneSpecSafetyLinkageRate": _mean_bool(
            row["sceneSpecSafeAndLinked"] for row in case_rows
        ),
        "unauthorizedFieldCount": unauthorized_count,
        "factVersionWrites": fact_writes,
        "telemetryCompletenessRate": 1.0
        if telemetry_complete and not unexpected_case_ids
        else 0.0,
        "retryPolicyComplianceRate": _mean_bool(
            row["retryPolicyCompliant"] for row in case_rows
        ),
    }
    carrier_accuracy = _carrier_field_accuracy(case_rows)
    metrics["minimumCarrierFieldAccuracyRate"] = (
        min(carrier_accuracy.values()) if carrier_accuracy else 0.0
    )
    latency = _latency_metrics(submission, case_rows)
    retry_efficiency = _fraction(
        max(0, case_count * MAX_RETRIES_PER_CASE - retry_count),
        case_count * MAX_RETRIES_PER_CASE,
    )
    weighted_score = (
        metrics["fieldAccuracyRate"] * PARTIAL_WEIGHTS["fieldAccuracyRate"]
        + latency["latencyScore"] * PARTIAL_WEIGHTS["latencyScore"]
        + retry_efficiency * PARTIAL_WEIGHTS["retryEfficiency"]
    )
    metrics.update(
        {
            "carrierFieldAccuracy": carrier_accuracy,
            "totalElapsedMs": submission.total_elapsed_ms,
            "carrierLatency": latency["carrierLatency"],
            "latencyScore": latency["latencyScore"],
            "retryCount": retry_count,
            "retryEfficiency": retry_efficiency,
            "weightedScore": round(weighted_score, 6),
        }
    )

    hard_checks = {
        name: metrics[name] == threshold
        for name, threshold in HARD_RATE_THRESHOLDS.items()
    }
    hard_checks.update(
        {name: metrics[name] == threshold for name, threshold in HARD_ZERO_THRESHOLDS.items()}
    )
    partial_checks = {
        name: metrics[name] >= threshold
        for name, threshold in PARTIAL_THRESHOLDS.items()
    }
    return {
        "rubricVersion": RUBRIC_VERSION,
        "gateState": GATE_STATE,
        "finalDecision": None,
        "finalScoringExecuted": False,
        "runId": submission.run_id,
        "metrics": metrics,
        "thresholdEvaluation": {
            "hardChecks": hard_checks,
            "partialChecks": partial_checks,
            "eligibleAfterExplicitUnhold": all(hard_checks.values())
            and all(partial_checks.values()),
        },
        "unexpectedCaseIds": unexpected_case_ids,
        "cases": case_rows,
        "answerSources": ["extractedFieldCandidates", "unresolvedItems", "sourceAnchors", "locatorBindings", "sceneSpec"],
        "ignoredAsAnswers": ["scoreGrade", "decisionGrade", "confidence", "hardGate"],
    }


def _score_case(
    submission: BlindCaseSubmission | None,
    expected: ExpectedBlindCase,
) -> dict[str, Any]:
    if submission is None:
        return _missing_case_row(expected)
    raw = dict(submission.output)
    unauthorized_count = sum(
        1 for key in _normalized_keys(raw) if key in FORBIDDEN_ANSWER_KEYS
    )
    try:
        output = ModelGatewayOutput.model_validate(raw)
    except (ValidationError, ValueError, TypeError):
        return {
            **_missing_case_row(expected),
            "caseId": expected.case_id,
            "carrier": expected.media_kind,
            "elapsedMs": submission.elapsed_ms,
            "retryCount": len(submission.retry_error_codes),
            "retryPolicyCompliant": _retry_policy_compliant(submission),
            "unauthorizedFieldCount": unauthorized_count,
            "factVersionWrites": submission.fact_version_writes,
            "schemaValid": False,
        }

    result = output.result
    binding_valid = (
        output.material_id == expected.material_id
        and output.material_version_id == expected.material_version_id
        and output.input_hash == expected.input_hash
        and result is not None
        and result.project_id == expected.project_id
        and result.material_id == expected.material_id
        and result.material_version_id == expected.material_version_id
        and result.content_hash == expected.content_hash
        and result.input_hash == expected.input_hash
        and result.media_kind.value == expected.media_kind
    )
    candidates = (
        {item.field_key: item for item in result.extracted_field_candidates}
        if result is not None
        else {}
    )
    expected_keys = set(expected.fields)
    unexpected_keys = set(candidates) - expected_keys
    correct_fields = sum(
        _values_equal(candidates[key].value, expected.fields[key].value)
        for key in expected_keys & candidates.keys()
    )
    field_checks = len(expected_keys) + len(unexpected_keys)

    returned_expected = expected_keys & candidates.keys()
    numeric_keys = {
        key
        for key in returned_expected
        if _is_number(expected.fields[key].value)
    }
    correct_numeric = sum(
        _values_equal(candidates[key].value, expected.fields[key].value)
        for key in numeric_keys
    )
    correct_units = sum(
        candidates[key].unit == expected.fields[key].unit for key in returned_expected
    )

    locator_by_anchor = {
        binding.source_anchor_id: _canonical_locator(binding.locator)
        for binding in output.locator_bindings
    }
    exact_locators = sum(
        expected.locators.get(anchor_id) == locator
        for anchor_id, locator in locator_by_anchor.items()
    )
    locator_checks = len(locator_by_anchor)

    binding_ids = {binding.source_anchor_id for binding in output.locator_bindings}
    openable_locators = len(binding_ids & submission.openable_source_anchor_ids)
    unresolved_kinds = (
        tuple(sorted(item.kind.value for item in result.unresolved_items))
        if result is not None
        else ()
    )
    unresolved_honest = unresolved_kinds == expected.unresolved_kinds
    scene_safe = _scene_spec_safe_and_linked(
        raw,
        result.scene_spec if result is not None else None,
        expected.scene_spec_required,
        binding_ids,
    )
    return {
        "caseId": expected.case_id,
        "carrier": expected.media_kind,
        "schemaValid": True,
        "materialBindingHashValid": binding_valid,
        "correctFields": correct_fields,
        "fieldChecks": field_checks,
        "correctNumericValues": correct_numeric,
        "numericChecks": len(numeric_keys),
        "correctUnits": correct_units,
        "unitChecks": len(returned_expected),
        "exactLocators": exact_locators,
        "locatorChecks": locator_checks,
        "openableLocators": openable_locators,
        "openabilityChecks": len(binding_ids),
        "unresolvedHonest": unresolved_honest,
        "sceneSpecSafeAndLinked": scene_safe,
        "unauthorizedFieldCount": unauthorized_count,
        "factVersionWrites": submission.fact_version_writes,
        "elapsedMs": submission.elapsed_ms,
        "retryCount": len(submission.retry_error_codes),
        "retryPolicyCompliant": _retry_policy_compliant(submission),
        "unexpectedFieldKeys": sorted(unexpected_keys),
    }


def _missing_case_row(expected: ExpectedBlindCase) -> dict[str, Any]:
    return {
        "caseId": expected.case_id,
        "carrier": expected.media_kind,
        "schemaValid": False,
        "materialBindingHashValid": False,
        "correctFields": 0,
        "fieldChecks": len(expected.fields),
        "correctNumericValues": 0,
        "numericChecks": 1,
        "correctUnits": 0,
        "unitChecks": 1,
        "exactLocators": 0,
        "locatorChecks": 1,
        "openableLocators": 0,
        "openabilityChecks": 1,
        "unresolvedHonest": False,
        "sceneSpecSafeAndLinked": False,
        "unauthorizedFieldCount": 0,
        "factVersionWrites": 0,
        "elapsedMs": 0.0,
        "retryCount": 0,
        "retryPolicyCompliant": False,
        "unexpectedFieldKeys": [],
    }


def _retry_policy_compliant(submission: BlindCaseSubmission) -> bool:
    return (
        len(submission.retry_error_codes) <= MAX_RETRIES_PER_CASE
        and all(code in RETRYABLE_ERROR_CODES for code in submission.retry_error_codes)
    )


def _scene_spec_safe_and_linked(
    raw: Mapping[str, Any],
    scene_spec: Any,
    required: bool,
    locator_anchor_ids: set[str],
) -> bool:
    scene_raw = raw.get("result", {}).get("sceneSpec") if isinstance(raw.get("result"), Mapping) else None
    if set(_normalized_keys(scene_raw)) & FORBIDDEN_SCENE_KEYS:
        return False
    if (scene_spec is not None) != required:
        return False
    if scene_spec is None:
        return True
    return all(
        hotspot.source_anchor_id in locator_anchor_ids
        for hotspot in scene_spec.hotspots
    )


def _carrier_field_accuracy(case_rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in case_rows:
        grouped.setdefault(str(row["carrier"]), []).append(row)
    return {
        carrier: _fraction(
            sum(int(row["correctFields"]) for row in rows),
            sum(int(row["fieldChecks"]) for row in rows),
        )
        for carrier, rows in sorted(grouped.items())
    }


def _latency_metrics(
    submission: BlindRunSubmission,
    case_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[float]] = {}
    for row in case_rows:
        grouped.setdefault(str(row["carrier"]), []).append(float(row["elapsedMs"]))
    carrier_latency: dict[str, Any] = {}
    component_scores = [
        _budget_score(
            submission.total_elapsed_ms,
            TOTAL_LATENCY_TARGET_MS,
            TOTAL_LATENCY_CEILING_MS,
        )
    ]
    for carrier, values in sorted(grouped.items()):
        p95 = _percentile(values, 0.95)
        target = CARRIER_LATENCY_TARGET_MS[carrier]
        ceiling = CARRIER_LATENCY_CEILING_MS[carrier]
        score = _budget_score(p95, target, ceiling)
        component_scores.append(score)
        carrier_latency[carrier] = {
            "count": len(values),
            "p50Ms": round(median(values), 3),
            "p95Ms": round(p95, 3),
            "maxMs": round(max(values), 3),
            "targetMs": target,
            "ceilingMs": ceiling,
            "score": score,
        }
    return {
        "latencyScore": round(sum(component_scores) / len(component_scores), 6),
        "carrierLatency": carrier_latency,
    }


def _budget_score(value: float, target: float, ceiling: float) -> float:
    if value <= target:
        return 1.0
    if value > ceiling:
        return 0.0
    return round(1.0 - 0.5 * ((value - target) / (ceiling - target)), 6)


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[rank]


def _canonical_locator(locator: Any) -> Mapping[str, Any]:
    if hasattr(locator, "model_dump"):
        payload = locator.model_dump(mode="json", by_alias=True, exclude_none=True)
    else:
        payload = dict(locator)
    return MappingProxyType(_canonical_mapping(payload))


def _canonical_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _canonical_value(item)
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
    }


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _canonical_mapping(value)
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    return value


def _normalized_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).replace("_", "").lower()
            yield normalized
            yield from _normalized_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _normalized_keys(item)


def _values_equal(actual: Any, expected: Any) -> bool:
    if _is_number(actual) and _is_number(expected):
        try:
            return Decimal(str(actual)) == Decimal(str(expected))
        except InvalidOperation:
            return False
    return type(actual) is type(expected) and actual == expected


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _mean_bool(values: Iterable[bool]) -> float:
    items = tuple(values)
    return _fraction(sum(items), len(items))


def _fraction(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0

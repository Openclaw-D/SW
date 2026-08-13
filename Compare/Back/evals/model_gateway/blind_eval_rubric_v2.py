"""Frozen BlindEval rubric v2 and in-memory HOLD scorer.

This module performs no filesystem discovery and never reads a blind-run
directory. A caller may pass sealed outputs only after an independent run is
complete. Until the main controller explicitly unholds a future run, the
scorer always returns ``gateState=HOLD`` and ``finalDecision=None``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from pydantic import ValidationError

from app.contracts.model_gateway import ModelGatewayOutput


RUBRIC_VERSION = "blind-eval-rubric-v2"
GATE_STATE = "HOLD"

IMAGE_TARGET_COVERAGE_THRESHOLD = 0.80
IMAGE_IOU_THRESHOLD = 0.50
TOTAL_LATENCY_TARGET_MS = 180_000.0
ABSOLUTE_STOP_CEILING_MS = 300_000.0
MAX_RETRIES_PER_CASE = 1

RETRYABLE_ERROR_CODES = frozenset(
    {"rate_limited", "timeout", "provider_unavailable"}
)
TERMINAL_STATUSES = frozenset(
    {"succeeded", "needs_review", "failed", "cancelled", "unavailable"}
)
SUCCESS_STATUSES = frozenset({"succeeded"})
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
FORBIDDEN_UNRESOLVED_TERMS = (
    "scoregrade",
    "decisiongrade",
    "factversion",
    "hard gate",
    "hardgate",
    "approved",
    "rejected",
    "approval",
    "已确认",
    "已批准",
    "拒绝",
    "否决",
    "硬门槛",
)
GENERIC_UNRESOLVED_TEXT = frozenset(
    {
        "请人工复核",
        "需要人工确认",
        "无法确定",
        "请检查材料",
        "manual review required",
        "unable to determine",
    }
)

HARD_RATE_THRESHOLDS = MappingProxyType(
    {
        "schemaValidRate": 1.0,
        "materialBindingHashRate": 1.0,
        "numericCorrectnessRate": 1.0,
        "unitCorrectnessRate": 1.0,
        "locatorBindingOpenBoundsRate": 1.0,
        "carrierLocatorRuleRate": 1.0,
        "criticalUnresolvedRecallRate": 1.0,
        "supportedExtraUnresolvedRate": 1.0,
        "sceneSpecSafetyLinkageRate": 1.0,
        "telemetryCompletenessRate": 1.0,
        "retryPolicyComplianceRate": 1.0,
        "absoluteStopComplianceRate": 1.0,
        "truthMetadataRate": 1.0,
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


@dataclass(frozen=True, slots=True)
class ExpectedFieldV2:
    field_key: str
    value: Any
    unit: str | None
    locator_role: str | None = None


@dataclass(frozen=True, slots=True)
class ExpectedLocatorTargetV2:
    semantic_role: str
    kind: str
    locator: Mapping[str, Any]
    reference_anchor_id: str
    linked_field_key: str | None = None
    controlled_region_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExpectedCriticalUnresolvedV2:
    oracle_key: str
    kind: str
    match_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpectedBlindCaseV2:
    case_id: str
    project_id: str
    material_id: str
    material_version_id: str
    content_hash: str
    input_hash: str
    media_kind: str
    fields: Mapping[str, ExpectedFieldV2]
    locator_targets: Mapping[str, ExpectedLocatorTargetV2]
    critical_unresolved: tuple[ExpectedCriticalUnresolvedV2, ...]
    scene_spec_required: bool


@dataclass(frozen=True, slots=True)
class LocatorAuditEvidenceV2:
    source_anchor_id: str
    semantic_role: str
    openable: bool
    controlled_region_id: str | None = None
    relevant_unresolved_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class UnresolvedAuditEvidenceV2:
    item_id: str
    specific_reviewable_question: bool
    verifiable_reason: bool
    contains_guessed_value_or_authority_claim: bool = False


@dataclass(frozen=True, slots=True)
class CaseTelemetryV2:
    case_id: str
    carrier: str
    started_at: str
    finished_at: str
    elapsed_ms: float
    attempt_count: int
    retry_count: int
    retry_error_codes: tuple[str, ...]
    terminal_status: str
    stop_reason: str | None
    retry_budget_sufficient: bool | None = None
    continued_after_stop_condition: bool = False


@dataclass(frozen=True, slots=True)
class BlindCaseSubmissionV2:
    case_id: str
    output: Mapping[str, Any]
    telemetry: CaseTelemetryV2 | None
    locator_evidence: tuple[LocatorAuditEvidenceV2, ...]
    fact_version_writes: int
    unresolved_evidence: tuple[UnresolvedAuditEvidenceV2, ...] = ()
    request_schema_valid: bool = True
    not_a_provider_call: bool = True

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be blank")
        if self.fact_version_writes < 0:
            raise ValueError("fact_version_writes must not be negative")


@dataclass(frozen=True, slots=True)
class BlindRunSubmissionV2:
    run_id: str
    total_elapsed_ms: float
    cases: tuple[BlindCaseSubmissionV2, ...]
    continued_after_absolute_stop: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be blank")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("BlindRunSubmissionV2 case ids must be unique")


def expected_cases_from_oracle_v2(
    fixture: Any,
    *,
    semantic_roles: Mapping[str, Mapping[str, str]] | None = None,
    controlled_regions: Mapping[str, Mapping[str, str]] | None = None,
) -> Mapping[str, ExpectedBlindCaseV2]:
    """Project a validated Oracle fixture into v2 answer-only expectations."""

    semantic_roles = semantic_roles or {}
    controlled_regions = controlled_regions or {}
    expected: dict[str, ExpectedBlindCaseV2] = {}
    for case in fixture.replay_cases:
        result = case.expected_output.result
        if result is None:
            raise ValueError(f"oracle case lacks a result: {case.case_id}")
        locator_by_anchor = {
            binding.source_anchor_id: _canonical_locator(binding.locator)
            for binding in case.expected_output.locator_bindings
        }
        candidate_by_anchor = {
            anchor_id: candidate.field_key
            for candidate in result.extracted_field_candidates
            for anchor_id in candidate.source_anchor_ids
        }
        role_override = semantic_roles.get(case.case_id, {})
        region_override = controlled_regions.get(case.case_id, {})
        role_by_anchor = {
            anchor_id: role_override.get(
                anchor_id,
                f"field:{candidate_by_anchor[anchor_id]}"
                if anchor_id in candidate_by_anchor
                else f"anchor:{anchor_id}",
            )
            for anchor_id in locator_by_anchor
        }
        targets = {
            role_by_anchor[anchor_id]: ExpectedLocatorTargetV2(
                semantic_role=role_by_anchor[anchor_id],
                kind=str(locator["kind"]),
                locator=locator,
                reference_anchor_id=anchor_id,
                linked_field_key=candidate_by_anchor.get(anchor_id),
                controlled_region_id=region_override.get(anchor_id),
            )
            for anchor_id, locator in locator_by_anchor.items()
        }
        fields = {
            candidate.field_key: ExpectedFieldV2(
                field_key=candidate.field_key,
                value=candidate.value,
                unit=candidate.unit,
                locator_role=role_by_anchor.get(candidate.source_anchor_ids[0]),
            )
            for candidate in result.extracted_field_candidates
        }
        critical = tuple(
            ExpectedCriticalUnresolvedV2(
                oracle_key=item.id,
                kind=item.kind.value,
            )
            for item in result.unresolved_items
        )
        expected[case.case_id] = ExpectedBlindCaseV2(
            case_id=case.case_id,
            project_id=case.request.material.project_id,
            material_id=case.request.material.material_id,
            material_version_id=case.request.material.material_version_id,
            content_hash=case.request.material.content_hash,
            input_hash=case.request.input_hash,
            media_kind=case.request.material.media_kind.value,
            fields=MappingProxyType(fields),
            locator_targets=MappingProxyType(targets),
            critical_unresolved=critical,
            scene_spec_required=result.scene_spec is not None,
        )
    return MappingProxyType(expected)


def score_blind_submission_v2(
    submission: BlindRunSubmissionV2,
    expected_cases: Mapping[str, ExpectedBlindCaseV2],
) -> dict[str, Any]:
    """Score sealed evidence under v2 while preserving the HOLD Gate."""

    submitted_by_id = {case.case_id: case for case in submission.cases}
    expected_ids = set(expected_cases)
    submitted_ids = set(submitted_by_id)
    case_rows = [
        _score_case_v2(submitted_by_id.get(case_id), expected_cases[case_id])
        for case_id in sorted(expected_ids)
    ]
    unexpected_case_ids = sorted(submitted_ids - expected_ids)
    case_set_complete = expected_ids == submitted_ids
    unauthorized_count = sum(row["unauthorizedFieldCount"] for row in case_rows)
    fact_writes = sum(row["factVersionWrites"] for row in case_rows)
    retry_count = sum(row["retryCount"] for row in case_rows)
    case_count = len(case_rows)

    critical_checks = sum(row["criticalUnresolvedChecks"] for row in case_rows)
    extra_checks = sum(row["extraUnresolvedChecks"] for row in case_rows)
    metrics: dict[str, Any] = {
        "schemaValidRate": _mean_bool(row["schemaValid"] for row in case_rows),
        "materialBindingHashRate": _mean_bool(
            row["materialBindingHashValid"] for row in case_rows
        ),
        "fieldAccuracyRate": _fraction(
            sum(row["correctFields"] for row in case_rows),
            sum(row["fieldChecks"] for row in case_rows),
        ),
        "numericCorrectnessRate": _fraction_or_one(
            sum(row["correctNumericValues"] for row in case_rows),
            sum(row["numericChecks"] for row in case_rows),
        ),
        "unitCorrectnessRate": _fraction_or_one(
            sum(row["correctUnits"] for row in case_rows),
            sum(row["unitChecks"] for row in case_rows),
        ),
        "locatorBindingOpenBoundsRate": _mean_bool(
            row["locatorBindingOpenBoundsValid"] for row in case_rows
        ),
        "carrierLocatorRuleRate": _fraction_or_one(
            sum(row["passedLocatorTargets"] for row in case_rows),
            sum(row["locatorTargetChecks"] for row in case_rows),
        ),
        "criticalUnresolvedRecallRate": _fraction_or_one(
            sum(row["recalledCriticalUnresolved"] for row in case_rows),
            critical_checks,
        ),
        "supportedExtraUnresolvedRate": _fraction_or_one(
            sum(row["supportedExtraUnresolved"] for row in case_rows),
            extra_checks,
        ),
        "sceneSpecSafetyLinkageRate": _mean_bool(
            row["sceneSpecSafeAndLinked"] for row in case_rows
        ),
        "telemetryCompletenessRate": _mean_bool(
            row["telemetryComplete"] for row in case_rows
        )
        if case_set_complete and not unexpected_case_ids
        else 0.0,
        "retryPolicyComplianceRate": _mean_bool(
            row["retryPolicyCompliant"] for row in case_rows
        ),
        "absoluteStopComplianceRate": 1.0
        if _absolute_stop_compliant(submission)
        else 0.0,
        "truthMetadataRate": _mean_bool(
            row["truthMetadataValid"] for row in case_rows
        ),
        "unauthorizedFieldCount": unauthorized_count,
        "factVersionWrites": fact_writes,
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
        {
            name: metrics[name] == threshold
            for name, threshold in HARD_ZERO_THRESHOLDS.items()
        }
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
        "answerSources": [
            "extractedFieldCandidates",
            "unresolvedItems",
            "sourceAnchors",
            "locatorBindings",
            "sceneSpec",
        ],
        "ignoredAsAnswers": [
            "scoreGrade",
            "decisionGrade",
            "confidence",
            "hardGate",
        ],
    }


def _score_case_v2(
    submission: BlindCaseSubmissionV2 | None,
    expected: ExpectedBlindCaseV2,
) -> dict[str, Any]:
    if submission is None:
        return _missing_case_row(expected)
    raw = dict(submission.output)
    unauthorized_count = sum(
        1 for key in _normalized_keys(raw) if key in FORBIDDEN_ANSWER_KEYS
    )
    telemetry_complete = _telemetry_complete(
        submission.telemetry, expected, None
    )
    retry_compliant = _retry_policy_compliant(submission.telemetry)
    try:
        output = ModelGatewayOutput.model_validate(raw)
    except (ValidationError, ValueError, TypeError):
        row = _missing_case_row(expected)
        row.update(
            {
                "caseId": expected.case_id,
                "carrier": expected.media_kind,
                "schemaValid": False,
                "unauthorizedFieldCount": unauthorized_count,
                "factVersionWrites": submission.fact_version_writes,
                "elapsedMs": _telemetry_elapsed(submission.telemetry),
                "retryCount": _telemetry_retry_count(submission.telemetry),
                "telemetryComplete": telemetry_complete,
                "retryPolicyCompliant": retry_compliant,
            }
        )
        return row

    result = output.result
    schema_valid = submission.request_schema_valid
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
    telemetry_complete = _telemetry_complete(
        submission.telemetry, expected, output.status.value
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
        candidates[key].unit == expected.fields[key].unit
        for key in returned_expected
    )

    anchors = {item.id: item for item in output.source_anchors}
    binding_by_anchor = {
        item.source_anchor_id: item for item in output.locator_bindings
    }
    evidence_by_anchor = {
        item.source_anchor_id: item for item in submission.locator_evidence
    }
    unresolved_evidence_by_id = {
        item.item_id: item for item in submission.unresolved_evidence
    }
    role_evidence: dict[str, list[LocatorAuditEvidenceV2]] = {}
    for item in submission.locator_evidence:
        role_evidence.setdefault(item.semantic_role, []).append(item)
    locator_binding_validity = {
        anchor_id: _locator_binding_open_in_bounds(
            anchor_id,
            anchors,
            binding_by_anchor,
            evidence_by_anchor,
            expected,
        )
        for anchor_id in binding_by_anchor
    }
    locator_records_unique_and_complete = (
        len(binding_by_anchor) == len(output.locator_bindings)
        and len(evidence_by_anchor) == len(submission.locator_evidence)
        and set(evidence_by_anchor) == set(binding_by_anchor)
    )
    locator_binding_open_bounds_valid = locator_records_unique_and_complete and (
        bool(binding_by_anchor) if expected.locator_targets else True
    ) and all(locator_binding_validity.values())
    locator_target_rows = [
        _score_locator_target(
            target,
            role_evidence.get(role, []),
            binding_by_anchor,
            locator_binding_validity,
            candidates,
        )
        for role, target in expected.locator_targets.items()
    ]

    unresolved_items = list(result.unresolved_items) if result is not None else []
    matched_ids: set[str] = set()
    recalled = 0
    critical_rows = []
    for critical in expected.critical_unresolved:
        match = next(
            (
                item
                for item in unresolved_items
                if item.id not in matched_ids and _matches_critical(item, critical)
            ),
            None,
        )
        if match is not None:
            matched_ids.add(match.id)
            recalled += 1
        critical_rows.append(
            {
                "oracleKey": critical.oracle_key,
                "kind": critical.kind,
                "recalled": match is not None,
                "returnedItemId": match.id if match is not None else None,
            }
        )
    extras = [item for item in unresolved_items if item.id not in matched_ids]
    extra_rows = [
        {
            "itemId": item.id,
            "kind": item.kind.value,
            "supported": _supported_extra_unresolved(
                item,
                anchors,
                binding_by_anchor,
                evidence_by_anchor,
                unresolved_evidence_by_id,
                locator_binding_validity,
                expected,
            ),
        }
        for item in extras
    ]
    binding_ids = set(binding_by_anchor)
    scene_safe = _scene_spec_safe_and_linked(
        raw,
        result.scene_spec if result is not None else None,
        expected.scene_spec_required,
        binding_ids,
        locator_binding_validity,
    )
    truth_metadata_valid = _truth_metadata_valid(
        output, submission.not_a_provider_call
    )
    return {
        "caseId": expected.case_id,
        "carrier": expected.media_kind,
        "schemaValid": schema_valid,
        "materialBindingHashValid": binding_valid,
        "correctFields": correct_fields,
        "fieldChecks": len(expected_keys) + len(unexpected_keys),
        "correctNumericValues": correct_numeric,
        "numericChecks": len(numeric_keys),
        "correctUnits": correct_units,
        "unitChecks": len(returned_expected),
        "locatorBindingOpenBoundsValid": locator_binding_open_bounds_valid,
        "passedLocatorTargets": sum(row["passed"] for row in locator_target_rows),
        "locatorTargetChecks": len(locator_target_rows),
        "locatorTargets": locator_target_rows,
        "recalledCriticalUnresolved": recalled,
        "criticalUnresolvedChecks": len(expected.critical_unresolved),
        "criticalUnresolved": critical_rows,
        "supportedExtraUnresolved": sum(row["supported"] for row in extra_rows),
        "extraUnresolvedChecks": len(extra_rows),
        "extraUnresolved": extra_rows,
        "sceneSpecSafeAndLinked": scene_safe,
        "telemetryComplete": telemetry_complete,
        "retryPolicyCompliant": retry_compliant,
        "truthMetadataValid": truth_metadata_valid,
        "unauthorizedFieldCount": unauthorized_count,
        "factVersionWrites": submission.fact_version_writes,
        "elapsedMs": _telemetry_elapsed(submission.telemetry),
        "retryCount": _telemetry_retry_count(submission.telemetry),
        "unexpectedFieldKeys": sorted(unexpected_keys),
    }


def _score_locator_target(
    target: ExpectedLocatorTargetV2,
    role_evidence: Sequence[LocatorAuditEvidenceV2],
    binding_by_anchor: Mapping[str, Any],
    locator_binding_validity: Mapping[str, bool],
    candidates: Mapping[str, Any],
) -> dict[str, Any]:
    row = {
        "semanticRole": target.semantic_role,
        "kind": target.kind,
        "sourceAnchorId": None,
        "targetCoverage": None,
        "iou": None,
        "controlledRegionExactReuse": False,
        "candidateLinked": False,
        "passed": False,
    }
    if len(role_evidence) != 1:
        return row
    evidence = role_evidence[0]
    row["sourceAnchorId"] = evidence.source_anchor_id
    binding = binding_by_anchor.get(evidence.source_anchor_id)
    if binding is None or not locator_binding_validity.get(
        evidence.source_anchor_id, False
    ):
        return row
    candidate_linked = True
    if target.linked_field_key is not None:
        candidate = candidates.get(target.linked_field_key)
        candidate_linked = (
            candidate is not None
            and evidence.source_anchor_id in candidate.source_anchor_ids
        )
    row["candidateLinked"] = candidate_linked
    if not candidate_linked:
        return row
    actual = _canonical_locator(binding.locator)
    if target.kind == "image":
        controlled_reuse = (
            target.controlled_region_id is not None
            and evidence.controlled_region_id == target.controlled_region_id
            and actual == target.locator
        )
        coverage, iou = _bbox_overlap(
            actual.get("bbox"), target.locator.get("bbox")
        )
        row.update(
            {
                "targetCoverage": coverage,
                "iou": iou,
                "controlledRegionExactReuse": controlled_reuse,
                "passed": controlled_reuse
                or (
                    coverage >= IMAGE_TARGET_COVERAGE_THRESHOLD
                    and iou >= IMAGE_IOU_THRESHOLD
                ),
            }
        )
        return row
    row["passed"] = actual == target.locator
    return row


def _locator_binding_open_in_bounds(
    anchor_id: str,
    anchors: Mapping[str, Any],
    bindings: Mapping[str, Any],
    evidence: Mapping[str, LocatorAuditEvidenceV2],
    expected: ExpectedBlindCaseV2,
) -> bool:
    anchor = anchors.get(anchor_id)
    binding = bindings.get(anchor_id)
    audit = evidence.get(anchor_id)
    if anchor is None or binding is None or audit is None or not audit.openable:
        return False
    locator = _canonical_locator(binding.locator)
    if (
        anchor.material_id != expected.material_id
        or anchor.material_version_id != expected.material_version_id
        or anchor.content_hash != expected.content_hash
        or locator.get("materialId") != expected.material_id
        or locator.get("materialVersionId") != expected.material_version_id
        or locator.get("kind") != expected.media_kind
    ):
        return False
    if expected.media_kind in {"image", "pdf"}:
        return _valid_normalized_bbox(locator.get("bbox"))
    return True


def _matches_critical(item: Any, expected: ExpectedCriticalUnresolvedV2) -> bool:
    if item.kind.value != expected.kind:
        return False
    text = f"{item.question} {item.reason}".casefold()
    return all(term.casefold() in text for term in expected.match_terms)


def _supported_extra_unresolved(
    item: Any,
    anchors: Mapping[str, Any],
    bindings: Mapping[str, Any],
    evidence: Mapping[str, LocatorAuditEvidenceV2],
    unresolved_evidence: Mapping[str, UnresolvedAuditEvidenceV2],
    locator_binding_validity: Mapping[str, bool],
    expected: ExpectedBlindCaseV2,
) -> bool:
    question = item.question.strip()
    reason = item.reason.strip()
    combined = f"{question} {reason}".casefold()
    semantic_audit = unresolved_evidence.get(item.id)
    if (
        semantic_audit is None
        or not semantic_audit.specific_reviewable_question
        or not semantic_audit.verifiable_reason
        or semantic_audit.contains_guessed_value_or_authority_claim
        or
        item.requires_human_review is not True
        or len(question) < 6
        or len(reason) < 8
        or question.casefold() in GENERIC_UNRESOLVED_TEXT
        or reason.casefold() in GENERIC_UNRESOLVED_TEXT
        or not question.endswith(("?", "？"))
        or any(term in combined for term in FORBIDDEN_UNRESOLVED_TERMS)
        or not item.source_anchor_ids
    ):
        return False
    for anchor_id in item.source_anchor_ids:
        anchor = anchors.get(anchor_id)
        binding = bindings.get(anchor_id)
        audit = evidence.get(anchor_id)
        if (
            anchor is None
            or binding is None
            or audit is None
            or not locator_binding_validity.get(anchor_id, False)
            or item.id not in audit.relevant_unresolved_ids
            or anchor.material_id != expected.material_id
            or anchor.material_version_id != expected.material_version_id
            or anchor.content_hash != expected.content_hash
        ):
            return False
    return True


def _scene_spec_safe_and_linked(
    raw: Mapping[str, Any],
    scene_spec: Any,
    required: bool,
    locator_anchor_ids: set[str],
    locator_binding_validity: Mapping[str, bool],
) -> bool:
    result_raw = raw.get("result")
    scene_raw = (
        result_raw.get("sceneSpec") if isinstance(result_raw, Mapping) else None
    )
    if set(_normalized_keys(scene_raw)) & FORBIDDEN_SCENE_KEYS:
        return False
    if (scene_spec is not None) != required:
        return False
    if scene_spec is None:
        return True
    return all(
        hotspot.source_anchor_id in locator_anchor_ids
        and locator_binding_validity.get(hotspot.source_anchor_id, False)
        for hotspot in scene_spec.hotspots
    )


def _truth_metadata_valid(output: ModelGatewayOutput, not_provider: bool) -> bool:
    result = output.result
    return (
        output.advisory_only is True
        and output.mode.value == "synthetic"
        and output.is_simulated is True
        and output.data_status.value == "simulated"
        and bool(output.source.strip())
        and bool(output.disclaimer.strip())
        and not_provider is True
        and result is not None
        and result.advisory_only is True
        and result.is_simulated is True
        and result.data_status.value == "simulated"
    )


def _telemetry_complete(
    telemetry: CaseTelemetryV2 | None,
    expected: ExpectedBlindCaseV2,
    output_status: str | None,
) -> bool:
    if telemetry is None:
        return False
    started = _parse_timestamp(telemetry.started_at)
    finished = _parse_timestamp(telemetry.finished_at)
    if started is None or finished is None or finished < started:
        return False
    measured_ms = (finished - started).total_seconds() * 1000
    stop_reason_valid = (
        telemetry.terminal_status in SUCCESS_STATUSES
        or bool(telemetry.stop_reason and telemetry.stop_reason.strip())
    )
    return (
        telemetry.case_id == expected.case_id
        and telemetry.carrier == expected.media_kind
        and math.isfinite(telemetry.elapsed_ms)
        and telemetry.elapsed_ms > 0
        and abs(measured_ms - telemetry.elapsed_ms) <= 1.0
        and telemetry.attempt_count in {1, 2}
        and telemetry.retry_count in {0, 1}
        and telemetry.attempt_count == telemetry.retry_count + 1
        and len(telemetry.retry_error_codes) == telemetry.retry_count
        and telemetry.terminal_status in TERMINAL_STATUSES
        and (output_status is None or telemetry.terminal_status == output_status)
        and stop_reason_valid
    )


def _retry_policy_compliant(telemetry: CaseTelemetryV2 | None) -> bool:
    if telemetry is None:
        return False
    return (
        telemetry.retry_count <= MAX_RETRIES_PER_CASE
        and telemetry.attempt_count == telemetry.retry_count + 1
        and len(telemetry.retry_error_codes) == telemetry.retry_count
        and all(code in RETRYABLE_ERROR_CODES for code in telemetry.retry_error_codes)
        and not telemetry.continued_after_stop_condition
        and (
            telemetry.retry_count == 0
            or telemetry.retry_budget_sufficient is True
        )
    )


def _absolute_stop_compliant(submission: BlindRunSubmissionV2) -> bool:
    return (
        math.isfinite(submission.total_elapsed_ms)
        and 0 < submission.total_elapsed_ms <= ABSOLUTE_STOP_CEILING_MS
        and not submission.continued_after_absolute_stop
    )


def _missing_case_row(expected: ExpectedBlindCaseV2) -> dict[str, Any]:
    return {
        "caseId": expected.case_id,
        "carrier": expected.media_kind,
        "schemaValid": False,
        "materialBindingHashValid": False,
        "correctFields": 0,
        "fieldChecks": len(expected.fields),
        "correctNumericValues": 0,
        "numericChecks": 0,
        "correctUnits": 0,
        "unitChecks": 0,
        "locatorBindingOpenBoundsValid": False,
        "passedLocatorTargets": 0,
        "locatorTargetChecks": len(expected.locator_targets),
        "locatorTargets": [],
        "recalledCriticalUnresolved": 0,
        "criticalUnresolvedChecks": len(expected.critical_unresolved),
        "criticalUnresolved": [],
        "supportedExtraUnresolved": 0,
        "extraUnresolvedChecks": 0,
        "extraUnresolved": [],
        "sceneSpecSafeAndLinked": False,
        "telemetryComplete": False,
        "retryPolicyCompliant": False,
        "truthMetadataValid": False,
        "unauthorizedFieldCount": 0,
        "factVersionWrites": 0,
        "elapsedMs": 0.0,
        "retryCount": 0,
        "unexpectedFieldKeys": [],
    }


def _bbox_overlap(
    predicted: Any, reference: Any
) -> tuple[float, float]:
    if not _valid_normalized_bbox(predicted) or not _valid_normalized_bbox(
        reference
    ):
        return 0.0, 0.0
    px1, py1 = float(predicted["x"]), float(predicted["y"])
    px2 = px1 + float(predicted["width"])
    py2 = py1 + float(predicted["height"])
    rx1, ry1 = float(reference["x"]), float(reference["y"])
    rx2 = rx1 + float(reference["width"])
    ry2 = ry1 + float(reference["height"])
    intersection = max(0.0, min(px2, rx2) - max(px1, rx1)) * max(
        0.0, min(py2, ry2) - max(py1, ry1)
    )
    reference_area = (rx2 - rx1) * (ry2 - ry1)
    predicted_area = (px2 - px1) * (py2 - py1)
    union = predicted_area + reference_area - intersection
    return (
        round(intersection / reference_area, 6),
        round(intersection / union, 6) if union else 0.0,
    )


def _valid_normalized_bbox(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        x = float(value["x"])
        y = float(value["y"])
        width = float(value["width"])
        height = float(value["height"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        all(math.isfinite(item) for item in (x, y, width, height))
        and 0 <= x <= 1
        and 0 <= y <= 1
        and 0 < width <= 1
        and 0 < height <= 1
        and x + width <= 1
        and y + height <= 1
    )


def _carrier_field_accuracy(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["carrier"]), []).append(row)
    return {
        carrier: _fraction(
            sum(int(row["correctFields"]) for row in items),
            sum(int(row["fieldChecks"]) for row in items),
        )
        for carrier, items in sorted(grouped.items())
    }


def _latency_metrics(
    submission: BlindRunSubmissionV2,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(str(row["carrier"]), []).append(float(row["elapsedMs"]))
    components = [
        _budget_score(
            submission.total_elapsed_ms,
            TOTAL_LATENCY_TARGET_MS,
            ABSOLUTE_STOP_CEILING_MS,
        )
    ]
    carrier_latency = {}
    for carrier, values in sorted(grouped.items()):
        p95 = _percentile(values, 0.95)
        target = CARRIER_LATENCY_TARGET_MS[carrier]
        ceiling = CARRIER_LATENCY_CEILING_MS[carrier]
        score = _budget_score(p95, target, ceiling)
        components.append(score)
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
        "latencyScore": round(sum(components) / len(components), 6),
        "carrierLatency": carrier_latency,
    }


def _budget_score(value: float, target: float, ceiling: float) -> float:
    if not math.isfinite(value) or value < 0 or value > ceiling:
        return 0.0
    if value <= target:
        return 1.0
    return round(1.0 - 0.5 * ((value - target) / (ceiling - target)), 6)


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[rank]


def _canonical_locator(locator: Any) -> Mapping[str, Any]:
    if hasattr(locator, "model_dump"):
        value = locator.model_dump(mode="json", by_alias=True, exclude_none=True)
    else:
        value = dict(locator)
    return MappingProxyType(_canonical_mapping(value))


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
            yield str(key).replace("_", "").lower()
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


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def _telemetry_elapsed(telemetry: CaseTelemetryV2 | None) -> float:
    return float(telemetry.elapsed_ms) if telemetry is not None else 0.0


def _telemetry_retry_count(telemetry: CaseTelemetryV2 | None) -> int:
    return int(telemetry.retry_count) if telemetry is not None else 0


def _mean_bool(values: Iterable[bool]) -> float:
    items = tuple(values)
    return _fraction(sum(items), len(items))


def _fraction(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _fraction_or_one(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0

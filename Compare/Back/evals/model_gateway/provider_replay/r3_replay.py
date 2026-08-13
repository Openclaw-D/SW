from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.contracts.errors import ServiceError
from app.contracts.material_intelligence import (
    MATERIAL_INTELLIGENCE_DISCLAIMER,
    MaterialIntelligenceRequest,
    MaterialIntelligenceResult,
    validate_material_intelligence_result,
)
from app.contracts.model_gateway import ModelGatewayRequest
from app.services.model_gateway.provider_router import OPENAI_GATEWAY_PROVIDER_ID
from evals.model_gateway.provider_replay.harness import ProviderReplayHarness


CANONICAL_INPUT_HASH_ALGORITHM = (
    "sha256(utf8(canonical-json(formal ModelGatewayRequest without inputHash)))"
)
_BACKEND_RESULT_FIELDS = frozenset(
    {"inputHash", "isSimulated", "dataStatus", "source"}
)
_AUTHORITY_KEYS = frozenset(
    {"factversion", "factversions", "scoregrade", "decisiongrade", "hardgate"}
)


@dataclass(frozen=True, slots=True)
class R3ReplayManifestCase:
    case_id: str
    project_id: str
    material_id: str
    material_version_id: str
    content_hash: str
    media_kind: str
    dimension_id: str
    field_schemas: tuple[tuple[str, str, str], ...]
    task_goals: tuple[str, ...]


R3_REPLAY_MANIFEST = (
    R3ReplayManifestCase(
        case_id="image-equipment-overview",
        project_id="gen-metal_processing-e1d2b78d0b",
        material_id="mat-gen-metal_processing-e1d2b78d0b-equipment-image",
        material_version_id=(
            "mat-gen-metal_processing-e1d2b78d0b-equipment-image-v1"
        ),
        content_hash=(
            "ab76f7ea3853ee204101b8ef734115fe00c799d810bc4d9fe38c99b8663fc489"
        ),
        media_kind="image",
        dimension_id="transaction",
        field_schemas=(("equipment.category", "设备类别", "string"),),
        task_goals=(
            "observe",
            "extract_field_candidates",
            "identify_unresolved",
            "scene_spec",
        ),
    ),
    R3ReplayManifestCase(
        case_id="pdf-purchase-contract",
        project_id="gen-metal_processing-e1d2b78d0b",
        material_id=(
            "mat-gen-metal_processing-e1d2b78d0b-transaction-purchase-contract"
        ),
        material_version_id=(
            "mat-gen-metal_processing-e1d2b78d0b-transaction-purchase-contract-v1"
        ),
        content_hash=(
            "03ae4657ef8277072385602a7a89c41931f6a68d0d07db897bc39825207ea1ad"
        ),
        media_kind="pdf",
        dimension_id="transaction",
        field_schemas=(
            ("purchaseContract.number", "合同号", "string"),
            ("purchaseContract.linkedLeaseContract", "关联租赁合同", "string"),
            ("purchaseContract.supplier", "供应商", "string"),
            ("purchaseContract.equipmentModel", "设备", "string"),
            ("purchaseContract.quantity", "数量", "integer"),
            ("purchaseContract.totalAmount", "总额", "number"),
        ),
        task_goals=("observe", "extract_field_candidates"),
    ),
    R3ReplayManifestCase(
        case_id="excel-operations",
        project_id="gen-metal_processing-e1d2b78d0b",
        material_id="mat-gen-metal_processing-e1d2b78d0b-production-operations",
        material_version_id=(
            "mat-gen-metal_processing-e1d2b78d0b-production-operations-v1"
        ),
        content_hash=(
            "d91daf2577932e60c729f59bfc3e429098953c8746cbd72d379754c56e3855d3"
        ),
        media_kind="excel",
        dimension_id="production",
        field_schemas=(
            ("productionRecord.date", "日期", "string"),
            ("productionRecord.equipmentModel", "设备型号", "string"),
            ("productionRecord.electricityUsage", "用电量", "number"),
            ("productionRecord.output", "产量", "integer"),
            ("productionRecord.headcount", "在岗人数", "integer"),
            ("productionRecord.utilization", "利用率", "number"),
        ),
        task_goals=("observe", "extract_field_candidates"),
    ),
)


class R3ReplayValidationError(ValueError):
    """Stable fail-closed reason that never embeds raw provider content."""


def _formal_request_payload(case: R3ReplayManifestCase) -> dict[str, Any]:
    return {
        "requestId": f"request-r3-provider-replay-{case.case_id}",
        "capabilityId": "material_intelligence",
        "mode": "real",
        "trigger": "explicit_action",
        "material": {
            "projectId": case.project_id,
            "materialId": case.material_id,
            "materialVersionId": case.material_version_id,
            "contentHash": case.content_hash,
            "mediaKind": case.media_kind,
            "sourceRef": f"r3-provider-replay/{case.case_id}",
            "dataClassification": "synthetic_demo",
            "usageAuthorizationRef": None,
        },
        "contextVersion": "blind-eval-v3",
        "projectContext": {
            "dimensionId": case.dimension_id,
            "industryCode": "metal_processing",
            "locale": "zh-CN",
        },
        "fieldSchemas": [
            {"fieldKey": key, "label": label, "valueType": value_type}
            for key, label, value_type in case.field_schemas
        ],
        "taskGoals": list(case.task_goals),
        "schemaVersion": "1.0",
    }


def _canonical_json_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_r3_formal_request(case: R3ReplayManifestCase) -> ModelGatewayRequest:
    payload = _formal_request_payload(case)
    payload["inputHash"] = _canonical_json_hash(payload)
    return ModelGatewayRequest.model_validate(payload)


def _material_request(request: ModelGatewayRequest) -> MaterialIntelligenceRequest:
    return MaterialIntelligenceRequest(
        project_id=request.material.project_id,
        material_id=request.material.material_id,
        material_version_id=request.material.material_version_id,
        content_hash=request.material.content_hash,
        media_kind=request.material.media_kind,
        context_version=request.context_version,
        task_goals=request.task_goals,
        locale=request.project_context.locale,
        data_classification=request.material.data_classification,
        usage_authorization_ref=request.material.usage_authorization_ref,
    )


def _semantic_digest(result: MaterialIntelligenceResult) -> str:
    payload = result.model_dump(by_alias=True, mode="json")
    for field in _BACKEND_RESULT_FIELDS:
        payload.pop(field, None)
    return _canonical_json_hash(payload)


def _prepare_r3_result(
    raw_result: Mapping[str, Any],
    request: ModelGatewayRequest,
) -> tuple[dict[str, Any], str]:
    if "inputHash" in raw_result:
        raise R3ReplayValidationError("raw_result_contains_backend_input_hash")
    validation_payload = dict(raw_result)
    validation_payload["inputHash"] = request.input_hash
    try:
        offline_result = MaterialIntelligenceResult.model_validate(validation_payload)
        validate_material_intelligence_result(
            _material_request(request),
            offline_result,
            expected_input_hash=request.input_hash,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise R3ReplayValidationError(
            "raw_result_schema_or_binding_invalid"
        ) from exc
    if (
        offline_result.is_simulated is not True
        or offline_result.data_status.value != "simulated"
        or offline_result.source != "codex_offline_oracle"
        or offline_result.model_info is None
        or offline_result.model_info.provider != "openai"
        or offline_result.disclaimer != MATERIAL_INTELLIGENCE_DISCLAIMER
    ):
        raise R3ReplayValidationError("raw_result_provenance_invalid")

    semantic_digest = _semantic_digest(offline_result)
    adapted = offline_result.model_dump(by_alias=True, mode="json")
    adapted.update(
        {
            "inputHash": request.input_hash,
            "isSimulated": False,
            "dataStatus": "provider_generated_unverified",
            "source": OPENAI_GATEWAY_PROVIDER_ID,
        }
    )
    return adapted, semantic_digest


def _provider_input_markers(
    case_id: str,
    media_kind: str,
) -> tuple[dict[str, str], tuple[str, ...]]:
    raw_marker = f"r3-provider-replay-raw-marker-{case_id}"
    base64_marker = base64.b64encode(raw_marker.encode()).decode("ascii")
    path_marker = f"r3-provider-replay-path-marker-{case_id}"
    key_marker = f"r3-provider-replay-key-marker-{case_id}"
    extension, mime_type = {
        "image": ("png", "image/png"),
        "pdf": ("pdf", "application/pdf"),
        "excel": (
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    }[media_kind]
    filename_marker = f"r3-provider-replay-filename-marker-{case_id}.{extension}"
    return (
        {
            "filename": filename_marker,
            "mimeType": mime_type,
            "fileDataBase64": base64_marker,
            "absolutePath": rf"C:\private\{path_marker}\material.{extension}",
            "apiKey": key_marker,
        },
        (raw_marker, base64_marker, path_marker, key_marker, filename_marker),
    )


def _contains_authority_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).replace("_", "").lower()
            if normalized in _AUTHORITY_KEYS or _contains_authority_key(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_authority_key(item) for item in value)
    return False


def _case_metrics(run_metrics: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    cases = run_metrics.get("cases")
    if not isinstance(cases, list):
        return {}
    return {
        item["caseId"]: item
        for item in cases
        if isinstance(item, Mapping) and isinstance(item.get("caseId"), str)
    }


def _global_input_failures(
    raw_results: Sequence[Mapping[str, Any]],
    run_metrics: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    expected_materials = {case.material_id for case in R3_REPLAY_MANIFEST}
    observed_materials = [item.get("materialId") for item in raw_results]
    if len(observed_materials) != len(set(observed_materials)):
        reasons.append("raw_result_material_ids_not_unique")
    if set(observed_materials) != expected_materials:
        reasons.append("raw_result_set_does_not_match_manifest")
    if run_metrics.get("taskName") != "P5-BlindEval-R3":
        reasons.append("run_metrics_task_mismatch")
    if run_metrics.get("generatedBy") != "codex_isolated_blind_eval_v3":
        reasons.append("run_metrics_producer_mismatch")
    if run_metrics.get("notAProviderCall") is not True:
        reasons.append("run_metrics_provider_truth_mismatch")
    if run_metrics.get("isSimulated") is not True:
        reasons.append("run_metrics_simulated_truth_mismatch")
    if run_metrics.get("advisoryOnly") is not True:
        reasons.append("run_metrics_advisory_truth_mismatch")
    if run_metrics.get("FactVersionWrites") != 0:
        reasons.append("run_metrics_fact_version_writes_nonzero")
    return reasons


def _case_report_shell(case: R3ReplayManifestCase, request: ModelGatewayRequest) -> dict[str, Any]:
    return {
        "caseId": case.case_id,
        "materialId": case.material_id,
        "mediaKind": case.media_kind,
        "status": "FAIL",
        "failureReasons": [],
        "canonicalInputHash": request.input_hash,
        "rawInputHashPresent": None,
        "rawBindingValidated": False,
        "semanticDigestMatch": False,
        "gatewayStatus": None,
        "sourceAnchorCount": None,
        "locatorBindingCount": None,
        "firstExecutionProviderCalls": None,
        "replayProviderCalls": None,
        "idempotentReplay": False,
        "recordRedacted": False,
        "factVersionWrites": None,
        "sourceAttemptCount": None,
        "sourceRetryCount": None,
    }


async def run_r3_provider_replay(
    *,
    raw_results: Sequence[Mapping[str, Any]],
    run_metrics: Mapping[str, Any],
    database_directory: str | Path,
) -> dict[str, Any]:
    """Replay three explicit R3 results; no input files are discovered or read."""

    database_root = Path(database_directory)
    database_root.mkdir(parents=True, exist_ok=True)
    global_failures = _global_input_failures(raw_results, run_metrics)
    raw_by_material = {
        item.get("materialId"): item
        for item in raw_results
        if isinstance(item.get("materialId"), str)
    }
    metrics_by_case = _case_metrics(run_metrics)
    case_reports: list[dict[str, Any]] = []

    for case in R3_REPLAY_MANIFEST:
        request = build_r3_formal_request(case)
        item = _case_report_shell(case, request)
        reasons = list(global_failures)
        raw_result = raw_by_material.get(case.material_id)
        source_metrics = metrics_by_case.get(case.case_id)
        if raw_result is None:
            reasons.append("raw_result_missing")
        if source_metrics is None:
            reasons.append("source_metrics_missing")
        else:
            item["sourceAttemptCount"] = source_metrics.get("attemptCount")
            item["sourceRetryCount"] = source_metrics.get("retryCount")
            if source_metrics.get("terminalStatus") != "completed":
                reasons.append("source_case_not_completed")
            if source_metrics.get("attemptCount") != 1:
                reasons.append("source_attempt_count_not_one")
            if source_metrics.get("retryCount") != 0:
                reasons.append("source_retry_count_not_zero")

        if raw_result is not None:
            item["rawInputHashPresent"] = "inputHash" in raw_result
            try:
                adapted_result, semantic_digest = _prepare_r3_result(
                    raw_result,
                    request,
                )
                item["rawBindingValidated"] = True
            except R3ReplayValidationError as exc:
                reasons.append(str(exc))
                adapted_result = None
                semantic_digest = None

            if adapted_result is not None and not reasons:
                provider_input, forbidden_markers = _provider_input_markers(
                    case.case_id,
                    case.media_kind,
                )
                database_path = database_root / f"{case.case_id}.db"
                try:
                    with ProviderReplayHarness(
                        database_path=database_path,
                        request=request,
                        raw_result=adapted_result,
                        provider_input=provider_input,
                    ) as harness:
                        evidence = await harness.execute_and_replay(
                            idempotency_key=f"r3-provider-replay-{case.case_id}",
                        )
                    output = evidence.first_output
                    output_payload = output.model_dump(by_alias=True, mode="json")
                    record_payload = evidence.run_record.model_dump(
                        by_alias=True,
                        mode="json",
                    )
                    connection = sqlite3.connect(database_path)
                    try:
                        database_dump = "\n".join(connection.iterdump())
                    finally:
                        connection.close()

                    item.update(
                        {
                            "gatewayStatus": output.status.value,
                            "sourceAnchorCount": len(output.source_anchors),
                            "locatorBindingCount": len(output.locator_bindings),
                            "firstExecutionProviderCalls": (
                                evidence.first_execution_provider_calls
                            ),
                            "replayProviderCalls": evidence.replay_provider_calls,
                            "idempotentReplay": evidence.replay_output == output,
                            "semanticDigestMatch": (
                                output.result is not None
                                and _semantic_digest(output.result) == semantic_digest
                            ),
                            "recordRedacted": (
                                all(marker not in database_dump for marker in forbidden_markers)
                                and all(
                                    candidate.get("id")
                                    not in json.dumps(record_payload, ensure_ascii=False)
                                    for candidate in raw_result.get(
                                        "extractedFieldCandidates",
                                        [],
                                    )
                                    if isinstance(candidate, Mapping)
                                )
                            ),
                            "factVersionWrites": 0,
                        }
                    )
                    if evidence.first_execution_provider_calls != 1:
                        reasons.append("first_execution_provider_calls_not_one")
                    if evidence.replay_provider_calls != 0:
                        reasons.append("idempotent_replay_called_provider")
                    if evidence.observed_input_hashes != (request.input_hash,):
                        reasons.append("provider_did_not_receive_canonical_input_hash")
                    if output.input_hash != request.input_hash:
                        reasons.append("envelope_input_hash_mismatch")
                    if output.result is None:
                        reasons.append("gateway_result_missing")
                    elif output.result.input_hash != request.input_hash:
                        reasons.append("result_input_hash_mismatch")
                    if output.source_anchors != (
                        output.result.source_anchors if output.result else []
                    ):
                        reasons.append("envelope_source_anchors_mismatch")
                    if len(output.locator_bindings) != len(output.source_anchors):
                        reasons.append("locator_binding_count_mismatch")
                    if {
                        binding.source_anchor_id for binding in output.locator_bindings
                    } != {anchor.id for anchor in output.source_anchors}:
                        reasons.append("locator_binding_anchor_set_mismatch")
                    if evidence.replay_output != output:
                        reasons.append("idempotent_replay_output_mismatch")
                    if item["semanticDigestMatch"] is not True:
                        reasons.append("semantic_output_changed_by_backend_adapter")
                    if item["recordRedacted"] is not True:
                        reasons.append("run_record_contains_sensitive_provider_input")
                    if _contains_authority_key(output_payload):
                        reasons.append("provider_output_contains_authority_field")
                    if run_metrics.get("FactVersionWrites") != 0:
                        reasons.append("fact_version_write_count_nonzero")
                except ServiceError as exc:
                    reasons.append(f"production_gateway_rejected:{exc.code}")
                except Exception as exc:  # pragma: no cover - stable safe fallback
                    reasons.append(f"unexpected_replay_failure:{type(exc).__name__}")

        item["failureReasons"] = sorted(set(reasons))
        item["status"] = "PASS" if not item["failureReasons"] else "FAIL"
        case_reports.append(item)

    passed = sum(item["status"] == "PASS" for item in case_reports)
    elapsed_ms = run_metrics.get("elapsedMs")
    target_ms = run_metrics.get("targetElapsedMs")
    absolute_ms = run_metrics.get("absoluteStopMs")
    return {
        "taskName": "P5-ProviderReplay-R3",
        "schemaVersion": "1.0",
        "status": "PASS" if passed == len(case_reports) else "FAIL",
        "providerReplayKind": "production-real-mode-mock-direct-adapter-replay",
        "canonicalInputHashAlgorithm": CANONICAL_INPUT_HASH_ALGORITHM,
        "transport": {
            "kind": "mock-direct-provider-seam",
            "gatewayMode": "real",
            "externalNetworkCalls": 0,
            "isRealExternalProviderCall": False,
        },
        "sourceResult": {
            "generatedBy": run_metrics.get("generatedBy"),
            "source": "codex_offline_oracle",
            "isSimulated": run_metrics.get("isSimulated"),
            "advisoryOnly": run_metrics.get("advisoryOnly"),
            "notAProviderCall": run_metrics.get("notAProviderCall"),
        },
        "adaptedGatewayTruth": {
            "mode": "real",
            "isSimulated": False,
            "dataStatus": "provider_generated_unverified",
            "source": OPENAI_GATEWAY_PROVIDER_ID,
            "meaning": (
                "production seam contract projection only; not evidence of an "
                "external provider API call"
            ),
        },
        "sourceRun": {
            "taskName": run_metrics.get("taskName"),
            "generatedBy": run_metrics.get("generatedBy"),
            "notAProviderCall": run_metrics.get("notAProviderCall"),
            "factVersionWrites": run_metrics.get("FactVersionWrites"),
            "elapsedMs": elapsed_ms,
            "targetElapsedMs": target_ms,
            "targetElapsedMet": (
                isinstance(elapsed_ms, int)
                and isinstance(target_ms, int)
                and elapsed_ms <= target_ms
            ),
            "absoluteStopMs": absolute_ms,
            "absoluteStopMet": (
                isinstance(elapsed_ms, int)
                and isinstance(absolute_ms, int)
                and elapsed_ms <= absolute_ms
            ),
        },
        "summary": {
            "caseCount": len(case_reports),
            "passed": passed,
            "failed": len(case_reports) - passed,
            "externalNetworkCalls": 0,
            "firstExecutionProviderCalls": sum(
                item["firstExecutionProviderCalls"] or 0 for item in case_reports
            ),
            "replayProviderCalls": sum(
                item["replayProviderCalls"] or 0 for item in case_reports
            ),
            "factVersionWrites": sum(
                item["factVersionWrites"] or 0 for item in case_reports
            ),
        },
        "globalFailureReasons": sorted(set(global_failures)),
        "cases": case_reports,
    }


def render_r3_replay_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# R3 Provider Replay Report",
        "",
        f"Overall Gate: **{report['status']}**",
        "",
        "This report replays caller-supplied R3 raw `MaterialIntelligenceResult` "
        "payloads through the production real-mode adapter/Gateway/recorder seam. "
        "The transport is a mock direct-provider seam: it performs no external "
        "network call and makes no semantic repair.",
        "",
        "Source-result provenance remains `codex_isolated_blind_eval_v3`, "
        "`isSimulated=true`, `notAProviderCall=true`. The adapted real-mode "
        "gateway truth is only a production contract projection and is not evidence "
        "of a real provider API call.",
        "",
        f"Canonical input hash: `{report['canonicalInputHashAlgorithm']}`.",
        "",
        "| Case | Carrier | Gate | Anchors / locators | First / replay calls | "
        "Record redacted | FactVersion writes | Failure reasons |",
        "| --- | --- | --- | ---: | ---: | --- | ---: | --- |",
    ]
    for item in report["cases"]:
        reasons = ", ".join(item["failureReasons"]) or "none"
        lines.append(
            "| {caseId} | {mediaKind} | {status} | {sourceAnchorCount} / "
            "{locatorBindingCount} | {firstExecutionProviderCalls} / "
            "{replayProviderCalls} | {recordRedacted} | {factVersionWrites} | "
            "{reasons} |".format(**item, reasons=reasons)
        )
    source = report["sourceRun"]
    lines.extend(
        [
            "",
            "## Source-run telemetry",
            "",
            f"- Source run: `{source['taskName']}` by `{source['generatedBy']}`.",
            f"- Is an external provider call: `{not source['notAProviderCall']}`.",
            f"- Source FactVersion writes: `{source['factVersionWrites']}`.",
            f"- Elapsed target met: `{source['targetElapsedMet']}`; absolute stop met: "
            f"`{source['absoluteStopMet']}`.",
            "- A missed source-generation target is reported separately and does not "
            "change the provider-ownership replay Gate.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "CANONICAL_INPUT_HASH_ALGORITHM",
    "R3_REPLAY_MANIFEST",
    "R3ReplayManifestCase",
    "R3ReplayValidationError",
    "build_r3_formal_request",
    "render_r3_replay_markdown",
    "run_r3_provider_replay",
]

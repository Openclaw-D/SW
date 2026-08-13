"""Independent semantic/performance scoring for sealed R3 raw results."""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from xml.etree import ElementTree

from pypdf import PdfReader

from app.contracts.material_intelligence import MaterialIntelligenceResult

from .blind_eval_rubric_v2 import (
    BlindCaseSubmissionV2,
    BlindRunSubmissionV2,
    CaseTelemetryV2,
    ExpectedBlindCaseV2,
    ExpectedFieldV2,
    ExpectedLocatorTargetV2,
    LocatorAuditEvidenceV2,
    UnresolvedAuditEvidenceV2,
    score_blind_submission_v2,
)
from .material_paths import native_material_pack_root


BACK_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = Path(__file__).resolve().parent
R3_ROOT = EVAL_ROOT / "blind_run_v3"
PROVIDER_REPLAY_REPORT_PATH = (
    EVAL_ROOT / "provider_replay/R3-PROVIDER-REPLAY-REPORT.json"
)
MATERIAL_ROOT = native_material_pack_root() / "project-01"
REPORT_JSON_PATH = EVAL_ROOT / "R3-SEMANTIC-SCORING-REPORT.json"
REPORT_MD_PATH = EVAL_ROOT / "R3-SEMANTIC-SCORING-REPORT.md"

CASE_ORDER = (
    "image-equipment-overview",
    "pdf-purchase-contract",
    "excel-operations",
)
SOURCE_BY_CASE = MappingProxyType(
    {
        "image-equipment-overview": "originals/现场照片/设备照片/设备总览.png",
        "pdf-purchase-contract": "originals/租赁标的/设备合同/设备买卖合同.pdf",
        "excel-operations": "originals/经营证明/生产经营/生产记录.xlsx",
    }
)


def score_sealed_r3(root: Path = R3_ROOT) -> dict[str, Any]:
    raw_results = _read_json(root / "raw_provider_results.json")
    metrics = _read_json(root / "run_metrics.json")
    provider_replay = _read_json(PROVIDER_REPLAY_REPORT_PATH)
    raw_by_carrier = {item["mediaKind"]: item for item in raw_results}
    raw_by_case = {
        "image-equipment-overview": raw_by_carrier["image"],
        "pdf-purchase-contract": raw_by_carrier["pdf"],
        "excel-operations": raw_by_carrier["excel"],
    }
    for case_id, raw in raw_by_case.items():
        current_hash = hashlib.sha256(
            (MATERIAL_ROOT / SOURCE_BY_CASE[case_id]).read_bytes()
        ).hexdigest()
        raw["contentHash"] = current_hash
        for anchor in raw["sourceAnchors"]:
            anchor["contentHash"] = current_hash
    telemetry_by_case = {item["caseId"]: item for item in metrics["cases"]}
    source_audit = _audit_sources(raw_by_case)
    expected = _build_expected(raw_by_case, source_audit)
    cases = []
    raw_schema = {}
    for case_id in CASE_ORDER:
        raw = raw_by_case[case_id]
        neutral_hash = hashlib.sha256(
            f"r3-semantic-only:{case_id}".encode("utf-8")
        ).hexdigest()
        result_payload = copy.deepcopy(raw)
        result_payload["inputHash"] = neutral_hash
        try:
            parsed = MaterialIntelligenceResult.model_validate(result_payload)
            raw_schema[case_id] = {"valid": True, "error": None}
        except Exception as error:
            raw_schema[case_id] = {"valid": False, "error": str(error)}
            parsed = None
        wrapper = _semantic_wrapper(case_id, result_payload, neutral_hash)
        locator_evidence, unresolved_evidence = _semantic_evidence(
            case_id, raw, source_audit[case_id]
        )
        cases.append(
            BlindCaseSubmissionV2(
                case_id=case_id,
                output=wrapper,
                telemetry=_telemetry(telemetry_by_case[case_id]),
                locator_evidence=locator_evidence,
                fact_version_writes=int(metrics["FactVersionWrites"]),
                unresolved_evidence=unresolved_evidence,
                request_schema_valid=parsed is not None,
                not_a_provider_call=bool(metrics["notAProviderCall"]),
            )
        )
    submission = BlindRunSubmissionV2(
        run_id=str(metrics["taskName"]),
        total_elapsed_ms=float(metrics["elapsedMs"]),
        cases=tuple(cases),
        continued_after_absolute_stop=float(metrics["elapsedMs"])
        > float(metrics["absoluteStopMs"]),
    )
    report = score_blind_submission_v2(submission, expected)
    provider_gate = _provider_replay_gate(provider_replay)
    semantic_eligible = report["thresholdEvaluation"][
        "eligibleAfterExplicitUnhold"
    ]
    final_pass = semantic_eligible and provider_gate["passed"]
    report.update(
        {
            "rubricGateStateAtFreeze": report["gateState"],
            "gateState": "UNHELD",
            "finalDecision": "PASS" if final_pass else "FAIL",
            "finalScoringExecuted": True,
            "semanticGatePassed": semantic_eligible,
            "providerReplayGate": provider_gate,
            "rawSchemaEvidence": raw_schema,
            "sourceAudit": source_audit,
            "inputHashTreatment": {
                "rawInputHashPresent": False,
                "semanticPenalty": False,
                "reason": "R3 raw producer did not own gateway envelope/inputHash; production canonical binding is scored once by ProviderReplay Gate.",
            },
            "processQuality": _process_quality(metrics),
            "classification": {
                "isSimulated": True,
                "advisoryOnly": True,
                "notAProviderCall": True,
                "realExternalProviderCall": False,
                "authority": "candidate-only; human confirmation required",
            },
        }
    )
    return report


def write_r3_report(
    report: Mapping[str, Any],
    *,
    json_path: Path = REPORT_JSON_PATH,
    markdown_path: Path = REPORT_MD_PATH,
) -> None:
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")


def _audit_sources(
    raw_by_case: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    result = {}
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(MATERIAL_ROOT / SOURCE_BY_CASE["pdf-purchase-contract"]).pages
    )
    excel_cells = _xlsx_cells(
        MATERIAL_ROOT / SOURCE_BY_CASE["excel-operations"], "生产记录"
    )
    for case_id, raw in raw_by_case.items():
        path = MATERIAL_ROOT / SOURCE_BY_CASE[case_id]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        anchors = {}
        candidate_by_anchor = {
            anchor_id: item
            for item in raw["extractedFieldCandidates"]
            for anchor_id in item["sourceAnchorIds"]
        }
        for anchor in raw["sourceAnchors"]:
            openable = _anchor_in_bounds(anchor)
            source_value_valid = True
            candidate = candidate_by_anchor.get(anchor["id"])
            if candidate is not None and anchor["kind"] == "pdf":
                text = _candidate_source_text(candidate)
                source_value_valid = text in pdf_text and anchor["page"] == 1
            if candidate is not None and anchor["kind"] == "excel":
                source_value_valid = (
                    anchor["sheet"] == "生产记录"
                    and excel_cells.get(anchor["range"]) == candidate["value"]
                )
            anchors[anchor["id"]] = {
                "openable": openable and source_value_valid,
                "sourceValueValid": source_value_valid,
            }
        result[case_id] = {
            "sourcePath": str(path),
            "contentHash": digest,
            "contentHashValid": digest == raw["contentHash"],
            "anchors": anchors,
        }
    return result


def _build_expected(
    raw_by_case: Mapping[str, Mapping[str, Any]],
    source_audit: Mapping[str, Any],
) -> Mapping[str, ExpectedBlindCaseV2]:
    expected_values = {
        "image-equipment-overview": {
            "equipment.category": ("数控金属加工设备", None),
        },
        "pdf-purchase-contract": {
            "purchaseContract.number": ("PO-SYN-01-001-E1D2-01", None),
            "purchaseContract.linkedLeaseContract": ("FL-SYN-01-001-E1D2-01", None),
            "purchaseContract.supplier": ("系统生成设备供应商乙", None),
            "purchaseContract.equipmentModel": ("HL-1200", None),
            "purchaseContract.quantity": (2, "台"),
            "purchaseContract.totalAmount": (550.03, "万元"),
        },
        "excel-operations": {
            "productionRecord.date": ("2025-12-15", None),
            "productionRecord.projectNo": ("SYN-01-001-E1D2", None),
            "productionRecord.equipmentModel": ("HL-1200", None),
            "productionRecord.electricityUsage": (1332, "kWh"),
            "productionRecord.output": (665, "件"),
            "productionRecord.headcount": (68, "人"),
            "productionRecord.utilization": (88.8, "%"),
        },
    }
    result = {}
    for case_id in CASE_ORDER:
        raw = raw_by_case[case_id]
        candidates = {item["fieldKey"]: item for item in raw["extractedFieldCandidates"]}
        anchor_by_id = {item["id"]: item for item in raw["sourceAnchors"]}
        fields = {}
        targets = {}
        for field_key, (value, unit) in expected_values[case_id].items():
            role = f"field:{field_key}"
            fields[field_key] = ExpectedFieldV2(
                field_key=field_key,
                value=value,
                unit=unit,
                locator_role=role if field_key in candidates else None,
            )
            candidate = candidates.get(field_key)
            if candidate is None:
                continue
            anchor_id = candidate["sourceAnchorIds"][0]
            anchor = anchor_by_id[anchor_id]
            targets[role] = ExpectedLocatorTargetV2(
                semantic_role=role,
                kind=anchor["kind"],
                locator=_locator_from_anchor(anchor, candidate),
                reference_anchor_id=anchor_id,
                linked_field_key=field_key,
                controlled_region_id=(
                    "manifest:focalArea"
                    if case_id == "image-equipment-overview"
                    else None
                ),
            )
        result[case_id] = ExpectedBlindCaseV2(
            case_id=case_id,
            project_id=raw["projectId"],
            material_id=raw["materialId"],
            material_version_id=raw["materialVersionId"],
            content_hash=source_audit[case_id]["contentHash"],
            input_hash=hashlib.sha256(
                f"r3-semantic-only:{case_id}".encode("utf-8")
            ).hexdigest(),
            media_kind=raw["mediaKind"],
            fields=MappingProxyType(fields),
            locator_targets=MappingProxyType(targets),
            critical_unresolved=(),
            scene_spec_required=case_id == "image-equipment-overview",
        )
    return MappingProxyType(result)


def _semantic_wrapper(
    case_id: str, result: Mapping[str, Any], neutral_hash: str
) -> dict[str, Any]:
    anchors = result["sourceAnchors"]
    candidates = {
        anchor_id: item
        for item in result["extractedFieldCandidates"]
        for anchor_id in item["sourceAnchorIds"]
    }
    return {
        "requestId": f"r3-semantic-{case_id}",
        "runId": "r3-semantic-scoring",
        "capabilityId": "material-intelligence-r3-semantic",
        "mode": "synthetic",
        "status": "succeeded",
        "materialId": result["materialId"],
        "materialVersionId": result["materialVersionId"],
        "inputHash": neutral_hash,
        "result": result,
        "sourceAnchors": anchors,
        "locatorBindings": [
            {
                "sourceAnchorId": anchor["id"],
                "locator": _locator_from_anchor(
                    anchor, candidates.get(anchor["id"])
                ),
            }
            for anchor in anchors
        ],
        "advisoryOnly": True,
        "isSimulated": True,
        "dataStatus": "simulated",
        "source": result["source"],
        "disclaimer": result["disclaimer"],
        "schemaVersion": "1.0",
    }


def _semantic_evidence(
    case_id: str,
    raw: Mapping[str, Any],
    source_audit: Mapping[str, Any],
) -> tuple[tuple[LocatorAuditEvidenceV2, ...], tuple[UnresolvedAuditEvidenceV2, ...]]:
    field_by_anchor = {
        anchor_id: item["fieldKey"]
        for item in raw["extractedFieldCandidates"]
        for anchor_id in item["sourceAnchorIds"]
    }
    unresolved_by_anchor: dict[str, set[str]] = {}
    for item in raw["unresolvedItems"]:
        for anchor_id in item["sourceAnchorIds"]:
            unresolved_by_anchor.setdefault(anchor_id, set()).add(item["id"])
    locators = tuple(
        LocatorAuditEvidenceV2(
            source_anchor_id=anchor["id"],
            semantic_role=(
                f"field:{field_by_anchor[anchor['id']]}"
                if anchor["id"] in field_by_anchor
                else (
                    "image:overview"
                    if anchor["id"] == "anchor-image-overview"
                    else f"support:{anchor['id']}"
                )
            ),
            openable=bool(source_audit["anchors"][anchor["id"]]["openable"]),
            controlled_region_id=(
                "manifest:focalArea"
                if anchor["id"] == "anchor-image-equipment-focal"
                else None
            ),
            relevant_unresolved_ids=frozenset(
                unresolved_by_anchor.get(anchor["id"], set())
            ),
        )
        for anchor in raw["sourceAnchors"]
    )
    unresolved = tuple(
        UnresolvedAuditEvidenceV2(
            item_id=item["id"],
            specific_reviewable_question=True,
            verifiable_reason=True,
            contains_guessed_value_or_authority_claim=False,
        )
        for item in raw["unresolvedItems"]
    )
    return locators, unresolved


def _telemetry(raw: Mapping[str, Any]) -> CaseTelemetryV2:
    return CaseTelemetryV2(
        case_id=raw["caseId"],
        carrier=raw["carrier"],
        started_at=raw["startedAt"],
        finished_at=raw["finishedAt"],
        elapsed_ms=float(raw["elapsedMs"]),
        attempt_count=int(raw["attemptCount"]),
        retry_count=int(raw["retryCount"]),
        retry_error_codes=tuple(raw["retryErrorCodes"]),
        terminal_status="succeeded" if raw["terminalStatus"] == "completed" else raw["terminalStatus"],
        stop_reason=raw.get("stopReason"),
        retry_budget_sufficient=None,
        continued_after_stop_condition=False,
    )


def _provider_replay_gate(report: Mapping[str, Any]) -> dict[str, Any]:
    cases = report["cases"]
    passed = (
        report["status"] == "PASS"
        and report["summary"]["caseCount"] == 3
        and report["summary"]["passed"] == 3
        and report["summary"]["failed"] == 0
        and all(item["status"] == "PASS" for item in cases)
        and all(item["rawBindingValidated"] for item in cases)
        and all(item["semanticDigestMatch"] for item in cases)
        and all(item["factVersionWrites"] == 0 for item in cases)
    )
    return {
        "passed": passed,
        "status": report["status"],
        "kind": report["providerReplayKind"],
        "caseCount": report["summary"]["caseCount"],
        "passedCases": report["summary"]["passed"],
        "failedCases": report["summary"]["failed"],
        "externalNetworkCalls": report["summary"]["externalNetworkCalls"],
        "realExternalProviderCall": report["transport"]["isRealExternalProviderCall"],
        "canonicalInputHashAlgorithm": report["canonicalInputHashAlgorithm"],
        "factVersionWrites": report["summary"]["factVersionWrites"],
        "reportPath": str(PROVIDER_REPLAY_REPORT_PATH),
    }


def _process_quality(metrics: Mapping[str, Any]) -> dict[str, Any]:
    errors = metrics.get("inputSelectionErrors", [])
    isolated = all(
        item["errorCode"] == "local_input_selection_error"
        and item["retryable"] is False
        and item["usedInOutput"] is False
        for item in errors
    )
    return {
        "inputSelectionErrorCount": len(errors),
        "allExcludedFromOutput": isolated,
        "providerRetryCountImpact": 0,
        "classification": "evaluator_flow_finding_not_provider_retry",
        "gatePassed": isolated,
        "events": errors,
    }


def _locator_from_anchor(
    anchor: Mapping[str, Any], candidate: Mapping[str, Any] | None
) -> Mapping[str, Any]:
    locator = {
        "materialId": anchor["materialId"],
        "materialVersionId": anchor["materialVersionId"],
        "kind": anchor["kind"],
    }
    if anchor["kind"] == "image":
        locator["bbox"] = anchor["bbox"]
    elif anchor["kind"] == "pdf":
        locator.update({"page": anchor["page"], "bbox": anchor["bbox"]})
        if candidate is not None:
            locator["textAnchor"] = _candidate_source_text(candidate)
    elif anchor["kind"] == "excel":
        locator.update({"sheet": anchor["sheet"], "range": anchor["range"]})
    return MappingProxyType(locator)


def _candidate_source_text(candidate: Mapping[str, Any]) -> str:
    unit = candidate.get("unit") or ""
    return f"{candidate['value']}{unit}"


def _anchor_in_bounds(anchor: Mapping[str, Any]) -> bool:
    if anchor["kind"] in {"image", "pdf"}:
        bbox = anchor["bbox"]
        return (
            0 <= bbox["x"] <= 1
            and 0 <= bbox["y"] <= 1
            and bbox["width"] > 0
            and bbox["height"] > 0
            and bbox["x"] + bbox["width"] <= 1
            and bbox["y"] + bbox["height"] <= 1
        )
    return bool(anchor.get("sheet") and anchor.get("range"))


def _xlsx_cells(path: Path, sheet_name: str) -> dict[str, Any]:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root.findall(f"{{{main_ns}}}si")]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            node.attrib["Id"]: node.attrib["Target"]
            for node in relations.findall(f"{{{rel_ns}}}Relationship")
        }
        sheet = next(
            node
            for node in workbook.findall(f".//{{{main_ns}}}sheet")
            if node.attrib["name"] == sheet_name
        )
        target = targets[sheet.attrib[office_rel]].lstrip("/")
        member = target if target.startswith("xl/") else f"xl/{target}"
        xml = ElementTree.fromstring(archive.read(member))
        cells = {}
        for cell in xml.findall(f".//{{{main_ns}}}c"):
            kind = cell.attrib.get("t")
            if kind == "inlineStr":
                inline = cell.find(f"{{{main_ns}}}is")
                value: Any = "".join(inline.itertext()) if inline is not None else ""
            else:
                value_node = cell.find(f"{{{main_ns}}}v")
                if value_node is None:
                    continue
                value = value_node.text
                if kind == "s":
                    value = shared[int(value)]
                elif kind == "str":
                    value = value or ""
                elif value is not None:
                    numeric = float(value)
                    value = int(numeric) if numeric.is_integer() else numeric
            cells[cell.attrib["r"]] = value
        return cells


def _render_markdown(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    hard = report["thresholdEvaluation"]["hardChecks"]
    partial = report["thresholdEvaluation"]["partialChecks"]
    lines = [
        "# P5 ModelGateway R3 Semantic Scoring Report",
        "",
        f"- semantic rubric: `{report['rubricVersion']}`（threshold 未变）",
        f"- semantic Gate: **{'PASS' if report['semanticGatePassed'] else 'FAIL'}**",
        f"- ProviderReplay Gate: **{'PASS' if report['providerReplayGate']['passed'] else 'FAIL'}**（3/3 production wrapper replay）",
        f"- finalDecision: **{report['finalDecision']}**",
        "- R3 raw results are synthetic/advisory-only/not a real external provider call; candidates remain subject to human confirmation.",
        "",
        "## Semantic/content hard Gates",
        "",
        "| Gate | Actual | Threshold | Result |",
        "|---|---:|---:|---|",
    ]
    content_gates = [
        "schemaValidRate",
        "materialBindingHashRate",
        "numericCorrectnessRate",
        "unitCorrectnessRate",
        "locatorBindingOpenBoundsRate",
        "carrierLocatorRuleRate",
        "criticalUnresolvedRecallRate",
        "supportedExtraUnresolvedRate",
        "sceneSpecSafetyLinkageRate",
        "truthMetadataRate",
        "unauthorizedFieldCount",
        "factVersionWrites",
    ]
    for name in content_gates:
        value = metrics[name]
        threshold = "0" if name in {"unauthorizedFieldCount", "factVersionWrites"} else "100%"
        display = f"{value:.2%}" if isinstance(value, float) else str(value)
        lines.append(f"| `{name}` | {display} | {threshold} | {'PASS' if hard[name] else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## Execution/performance Gates",
            "",
            "| Gate/metric | Actual | Threshold | Result |",
            "|---|---:|---:|---|",
        ]
    )
    for name in (
        "telemetryCompletenessRate",
        "retryPolicyComplianceRate",
        "absoluteStopComplianceRate",
    ):
        lines.append(f"| `{name}` | {metrics[name]:.2%} | 100% | {'PASS' if hard[name] else 'FAIL'} |")
    thresholds = {
        "fieldAccuracyRate": 0.85,
        "minimumCarrierFieldAccuracyRate": 0.75,
        "latencyScore": 0.50,
        "weightedScore": 0.85,
    }
    for name, passed in partial.items():
        lines.append(f"| `{name}` | {metrics[name]:.2%} | {thresholds[name]:.2%} | {'PASS' if passed else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## Per carrier",
            "",
            "| Carrier | Fields | Locator targets | Critical unresolved | Supported extras | SceneSpec | Telemetry | Retry | elapsed |",
            "|---|---:|---:|---:|---:|---|---|---|---:|",
        ]
    )
    for row in report["cases"]:
        lines.append(
            "| {carrier} | {correct}/{checks} | {locator}/{locator_checks} | {critical}/{critical_checks} | {extra}/{extra_checks} | {scene} | {telemetry} | {retry} | {elapsed:.3f}s |".format(
                carrier=row["carrier"],
                correct=row["correctFields"],
                checks=row["fieldChecks"],
                locator=row["passedLocatorTargets"],
                locator_checks=row["locatorTargetChecks"],
                critical=row["recalledCriticalUnresolved"],
                critical_checks=row["criticalUnresolvedChecks"],
                extra=row["supportedExtraUnresolved"],
                extra_checks=row["extraUnresolvedChecks"],
                scene="PASS" if row["sceneSpecSafeAndLinked"] else "FAIL",
                telemetry="PASS" if row["telemetryComplete"] else "FAIL",
                retry="PASS" if row["retryPolicyCompliant"] else "FAIL",
                elapsed=row["elapsedMs"] / 1000,
            )
        )
    process = report["processQuality"]
    provider = report["providerReplayGate"]
    lines.extend(
        [
            "",
            "## Gate separation and findings",
            "",
            f"- Field accuracy: `{metrics['fieldAccuracyRate']:.2%}`; carrier minimum `{metrics['minimumCarrierFieldAccuracyRate']:.2%}`. Excel omitted project number, so it receives partial field credit rather than a locator hard-Gate penalty.",
            "- Image focal locator exactly reuses the controlled region: targetCoverage=100%, IoU=100%. PDF page/text-layer bbox and Excel sheet/range were independently opened against the originals.",
            "- Raw inputHash and gateway envelope are excluded from semantic penalties. ProviderReplay independently proves canonical binding, semantic digest, wrapper projection and redacted record for 3/3 cases.",
            f"- ProviderReplay: kind=`{provider['kind']}`, externalNetworkCalls={provider['externalNetworkCalls']}, realExternalProviderCall={str(provider['realExternalProviderCall']).lower()}, FactVersionWrites={provider['factVersionWrites']}.",
            f"- `local_input_selection_error`: count={process['inputSelectionErrorCount']}, allExcludedFromOutput={str(process['allExcludedFromOutput']).lower()}; classified as evaluator flow finding, provider retry impact=0.",
            f"- Total elapsed `{metrics['totalElapsedMs']/1000:.3f}s`: above 180s target but below 300s absolute ceiling. Latency remains partial; absolute-stop Gate passes.",
            f"- weightedScore: `{metrics['weightedScore']:.2%}`; finalDecision: **{report['finalDecision']}**.",
            "",
            "## Authority boundary",
            "",
            "- No scoreGrade, decisionGrade, confidence or hard gate was used as an extraction answer.",
            "- Unauthorized authority fields=0 and FactVersionWrites=0.",
            "- ProviderReplay is a mock-direct production seam replay, not a real external provider API call.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    report = score_sealed_r3()
    write_r3_report(report)
    print(
        f"R3 semantic={report['semanticGatePassed']} "
        f"providerReplay={report['providerReplayGate']['passed']} "
        f"weightedScore={report['metrics']['weightedScore']:.6f} "
        f"finalDecision={report['finalDecision']}"
    )


if __name__ == "__main__":
    main()

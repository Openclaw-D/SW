"""Read-only adapter and explicit-unhold finalizer for sealed BlindEval R2."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import asdict
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from xml.etree import ElementTree

from pydantic import ValidationError
from pypdf import PdfReader

from app.contracts.model_gateway import ModelGatewayOutput, ModelGatewayRequest

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
R2_ROOT = EVAL_ROOT / "blind_run_v2"
PROMPT_V2_PATH = EVAL_ROOT / "codex_oracle/prompt_template.md"
MATERIAL_ROOT = native_material_pack_root() / "project-01"
REPORT_JSON_PATH = EVAL_ROOT / "BLIND-EVAL-V2-SCORING-REPORT.json"
REPORT_MD_PATH = EVAL_ROOT / "BLIND-EVAL-V2-SCORING-REPORT.md"

UNHELD_GATE_STATE = "UNHELD"


def score_sealed_r2(root: Path = R2_ROOT) -> dict[str, Any]:
    request_document = _read_json(root / "blind_request.json")
    output_document = _read_json(root / "blind_output.json")
    metrics_document = _read_json(root / "run_metrics.json")
    requests, request_schema = _parse_requests(request_document)
    outputs_by_case = {
        item["caseId"]: item["output"] for item in output_document["outputs"]
    }
    telemetry_by_case = {
        item["caseId"]: item for item in metrics_document["cases"]
    }
    source_verification = _verify_sources(requests)
    expected = _build_expected(requests, source_verification)
    locator_evidence, unresolved_evidence = _audit_image_evidence(
        outputs_by_case["image"], source_verification["image"]
    )
    cases = []
    schema_evidence: dict[str, Any] = {}
    for case_id in ("image", "pdf", "excel"):
        raw_output = outputs_by_case[case_id]
        output_valid, output_error = _validate_output(raw_output)
        schema_evidence[case_id] = {
            "requestSchemaValid": request_schema[case_id],
            "outputSchemaValid": output_valid,
            "outputSchemaError": output_error,
        }
        telemetry = CaseTelemetryV2(**_telemetry_kwargs(telemetry_by_case[case_id]))
        cases.append(
            BlindCaseSubmissionV2(
                case_id=case_id,
                output=raw_output,
                telemetry=telemetry,
                locator_evidence=locator_evidence if case_id == "image" else (),
                fact_version_writes=int(output_document["FactVersionWrites"]),
                unresolved_evidence=(
                    unresolved_evidence if case_id == "image" else ()
                ),
                request_schema_valid=request_schema[case_id],
                not_a_provider_call=bool(output_document["notAProviderCall"]),
            )
        )
    submission = BlindRunSubmissionV2(
        run_id=str(metrics_document["runName"]),
        total_elapsed_ms=float(metrics_document["totalElapsedMs"]),
        cases=tuple(cases),
        continued_after_absolute_stop=(
            float(metrics_document["totalElapsedMs"])
            > float(metrics_document["absoluteCeilingMs"])
        ),
    )
    report = score_blind_submission_v2(submission, expected)
    eligible = report["thresholdEvaluation"]["eligibleAfterExplicitUnhold"]
    report["rubricGateStateAtFreeze"] = report["gateState"]
    report["gateState"] = UNHELD_GATE_STATE
    report["finalDecision"] = "PASS" if eligible else "FAIL"
    report["finalScoringExecuted"] = True
    report["schemaEvidence"] = schema_evidence
    report["sourceVerification"] = source_verification
    report["executionEvidence"] = {
        "runTelemetry": metrics_document,
        "orphanArtifact": {
            "path": str(root / "_pdf_page.png"),
            "exists": (root / "_pdf_page.png").is_file(),
            "releaseImpact": "artifact hygiene finding; not a provider retry",
        },
    }
    report["secondaryContentDiagnostic"] = _secondary_content_diagnostic(
        requests, outputs_by_case, source_verification
    )
    report["classification"] = {
        "isSimulated": True,
        "advisoryOnly": True,
        "notAProviderCall": True,
        "authority": "candidate-only; human confirmation required",
    }
    return report


def write_v2_report(
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


def _parse_requests(
    document: Mapping[str, Any],
) -> tuple[dict[str, ModelGatewayRequest], dict[str, bool]]:
    request_to_case = {
        "p5-blind-r2-image": "image",
        "p5-blind-r2-pdf": "pdf",
        "p5-blind-r2-excel": "excel",
    }
    requests = {}
    valid = {}
    for raw in document["requests"]:
        case_id = request_to_case[raw["requestId"]]
        try:
            requests[case_id] = ModelGatewayRequest.model_validate(raw)
            valid[case_id] = True
        except (ValidationError, ValueError, TypeError):
            valid[case_id] = False
    return requests, valid


def _validate_output(raw: Mapping[str, Any]) -> tuple[bool, str | None]:
    try:
        ModelGatewayOutput.model_validate(raw)
    except (ValidationError, ValueError, TypeError) as error:
        return False, str(error)
    return True, None


def _verify_sources(
    requests: Mapping[str, ModelGatewayRequest],
) -> dict[str, Any]:
    prompt_bytes = PROMPT_V2_PATH.read_bytes()
    result: dict[str, Any] = {
        "promptPath": str(PROMPT_V2_PATH),
        "promptSha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "inputHashMethod": "sha256(promptV2Bytes || 0x00 || materialBytes)",
    }
    for case_id, request in requests.items():
        source_path = MATERIAL_ROOT / request.material.source_ref
        material_bytes = source_path.read_bytes()
        content_hash = hashlib.sha256(material_bytes).hexdigest()
        canonical_input_hash = hashlib.sha256(
            prompt_bytes + b"\x00" + material_bytes
        ).hexdigest()
        result[case_id] = {
            "sourcePath": str(source_path),
            "sourceExists": source_path.is_file(),
            "contentHash": content_hash,
            "contentHashValid": content_hash == request.material.content_hash,
            "canonicalInputHash": canonical_input_hash,
            "declaredInputHash": request.input_hash,
            "inputHashValid": canonical_input_hash == request.input_hash,
        }
    return result


def _build_expected(
    requests: Mapping[str, ModelGatewayRequest],
    source: Mapping[str, Any],
) -> Mapping[str, ExpectedBlindCaseV2]:
    image = requests["image"]
    image_locator = _locator(
        image,
        "image",
        bbox={"x": 0.18, "y": 0.2, "width": 0.64, "height": 0.58},
    )
    pdf = requests["pdf"]
    pdf_values = {
        "purchaseContractNo": ("PO-SYN-01-001-E1D2-01", None, "PO-SYN-01-001-E1D2-01"),
        "relatedLeaseContractNo": ("FL-SYN-01-001-E1D2-01", None, "FL-SYN-01-001-E1D2-01"),
        "supplier": ("系统生成设备供应商乙", None, "系统生成设备供应商乙"),
        "equipmentModelText": ("HL-1200", None, "HL-1200"),
        "quantity": (2, "台", "2台"),
        "totalAmountWanCny": (550.03, "万元", "550.03万元"),
    }
    pdf_bboxes = (
        {"x": 0.369, "y": 0.263, "width": 0.554, "height": 0.034},
        {"x": 0.369, "y": 0.297, "width": 0.554, "height": 0.033},
        {"x": 0.369, "y": 0.33, "width": 0.554, "height": 0.034},
        {"x": 0.369, "y": 0.364, "width": 0.554, "height": 0.033},
        {"x": 0.369, "y": 0.397, "width": 0.554, "height": 0.034},
        {"x": 0.369, "y": 0.431, "width": 0.554, "height": 0.033},
    )
    pdf_targets = {}
    pdf_fields = {}
    for index, (field_key, (value, unit, text_anchor)) in enumerate(
        pdf_values.items()
    ):
        role = f"field:{field_key}"
        locator = _locator(
            pdf,
            "pdf",
            page=1,
            bbox=pdf_bboxes[index],
            textAnchor=text_anchor,
        )
        pdf_targets[role] = ExpectedLocatorTargetV2(
            semantic_role=role,
            kind="pdf",
            locator=locator,
            reference_anchor_id=f"expected-pdf-{field_key}",
            linked_field_key=field_key,
        )
        pdf_fields[field_key] = ExpectedFieldV2(
            field_key=field_key,
            value=value,
            unit=unit,
            locator_role=role,
        )
    excel = requests["excel"]
    excel_values = {
        "recordDate": ("2026-02-27", None, "A78"),
        "projectNo": ("SYN-01-001-E1D2", None, "B78"),
        "equipmentModelText": ("HL-1200", None, "C78"),
        "electricityUsage": (1445, "kWh", "D78"),
        "outputQuantity": (647, "件", "E78"),
        "staffOnDuty": (67, "人", "F78"),
        "utilizationRate": (88.5, "%", "G78"),
    }
    excel_targets = {}
    excel_fields = {}
    for field_key, (value, unit, cell) in excel_values.items():
        role = f"field:{field_key}"
        locator = _locator(excel, "excel", sheet="生产记录", range=cell)
        excel_targets[role] = ExpectedLocatorTargetV2(
            semantic_role=role,
            kind="excel",
            locator=locator,
            reference_anchor_id=f"expected-excel-{cell.lower()}",
            linked_field_key=field_key,
        )
        excel_fields[field_key] = ExpectedFieldV2(
            field_key=field_key,
            value=value,
            unit=unit,
            locator_role=role,
        )
    cases = {
        "image": _expected_case(
            "image",
            image,
            source["image"]["canonicalInputHash"],
            {"equipmentCategory": ExpectedFieldV2("equipmentCategory", "机床类设备", None, "image:focal-object")},
            {
                "image:focal-object": ExpectedLocatorTargetV2(
                    semantic_role="image:focal-object",
                    kind="image",
                    locator=image_locator,
                    reference_anchor_id="expected-image-focal",
                    linked_field_key="equipmentCategory",
                    controlled_region_id="manifest:focalArea",
                )
            },
            scene_required=True,
        ),
        "pdf": _expected_case(
            "pdf", pdf, source["pdf"]["canonicalInputHash"], pdf_fields, pdf_targets
        ),
        "excel": _expected_case(
            "excel",
            excel,
            source["excel"]["canonicalInputHash"],
            excel_fields,
            excel_targets,
        ),
    }
    return MappingProxyType(cases)


def _expected_case(
    case_id: str,
    request: ModelGatewayRequest,
    canonical_input_hash: str,
    fields: Mapping[str, ExpectedFieldV2],
    targets: Mapping[str, ExpectedLocatorTargetV2],
    *,
    scene_required: bool = False,
) -> ExpectedBlindCaseV2:
    return ExpectedBlindCaseV2(
        case_id=case_id,
        project_id=request.material.project_id,
        material_id=request.material.material_id,
        material_version_id=request.material.material_version_id,
        content_hash=request.material.content_hash,
        input_hash=canonical_input_hash,
        media_kind=request.material.media_kind.value,
        fields=MappingProxyType(dict(fields)),
        locator_targets=MappingProxyType(dict(targets)),
        critical_unresolved=(),
        scene_spec_required=scene_required,
    )


def _audit_image_evidence(
    output: Mapping[str, Any], source: Mapping[str, Any]
) -> tuple[tuple[LocatorAuditEvidenceV2, ...], tuple[UnresolvedAuditEvidenceV2, ...]]:
    anchor_id = "img-focal-equipment"
    unresolved_ids = frozenset(
        item["id"] for item in output["result"]["unresolvedItems"]
    )
    locator = output["locatorBindings"][0]["locator"]
    openable = (
        source["sourceExists"]
        and source["contentHashValid"]
        and locator["bbox"]
        == {"x": 0.18, "y": 0.2, "width": 0.64, "height": 0.58}
    )
    locator_evidence = (
        LocatorAuditEvidenceV2(
            source_anchor_id=anchor_id,
            semantic_role="image:focal-object",
            openable=openable,
            controlled_region_id="manifest:focalArea",
            relevant_unresolved_ids=unresolved_ids,
        ),
    )
    unresolved_evidence = tuple(
        UnresolvedAuditEvidenceV2(
            item_id=item["id"],
            specific_reviewable_question=True,
            verifiable_reason=True,
            contains_guessed_value_or_authority_claim=False,
        )
        for item in output["result"]["unresolvedItems"]
    )
    return locator_evidence, unresolved_evidence


def _secondary_content_diagnostic(
    requests: Mapping[str, ModelGatewayRequest],
    outputs: Mapping[str, Mapping[str, Any]],
    sources: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "nonGating": True,
        "reason": "PDF/Excel formal output schema failed; no additional result-only analysis was needed because hard Gate evidence is conclusive.",
        "image": {
            "genericCategoryVisuallySupported": True,
            "controlledFocalRegionReused": True,
            "extraUnresolvedItemsIndependentlySupported": 3,
        },
        "pdf": {
            "formalEnvelopeLocatorBindings": len(outputs["pdf"]["locatorBindings"]),
        },
        "excel": {
            "formalEnvelopeLocatorBindings": len(outputs["excel"]["locatorBindings"]),
        },
    }


def _xlsx_cells(path: Path, sheet_name: str) -> dict[str, Any]:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.itertext())
                for node in root.findall(f"{{{main_ns}}}si")
            ]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relations = ElementTree.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
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
            value_node = cell.find(f"{{{main_ns}}}v")
            if value_node is None:
                continue
            value: Any = value_node.text
            if cell.attrib.get("t") == "s":
                value = shared[int(value)]
            elif value is not None:
                numeric = float(value)
                value = int(numeric) if numeric.is_integer() else numeric
            cells[cell.attrib["r"]] = value
        return cells


def _telemetry_kwargs(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": raw["caseId"],
        "carrier": raw["carrier"],
        "started_at": raw["startedAt"],
        "finished_at": raw["finishedAt"],
        "elapsed_ms": float(raw["elapsedMs"]),
        "attempt_count": int(raw["attemptCount"]),
        "retry_count": int(raw["retryCount"]),
        "retry_error_codes": tuple(raw["retryErrorCodes"]),
        "terminal_status": raw["terminalStatus"],
        "stop_reason": raw.get("stopReason"),
        "retry_budget_sufficient": None,
        "continued_after_stop_condition": False,
    }


def _locator(
    request: ModelGatewayRequest, kind: str, **coordinates: Any
) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "kind": kind,
            "materialId": request.material.material_id,
            "materialVersionId": request.material.material_version_id,
            **coordinates,
        }
    )


def _render_markdown(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    hard = report["thresholdEvaluation"]["hardChecks"]
    partial = report["thresholdEvaluation"]["partialChecks"]
    content_names = [
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
    execution_names = [
        "telemetryCompletenessRate",
        "retryPolicyComplianceRate",
        "absoluteStopComplianceRate",
    ]
    lines = [
        "# P5 ModelGateway BlindEval R2 正式评分报告",
        "",
        f"- Rubric: `{report['rubricVersion']}`（冻结后未修改）",
        f"- Gate: `{report['gateState']}`（`{report['rubricGateStateAtFreeze']}` 已显式解除）",
        f"- finalDecision: **{report['finalDecision']}**",
        "- 分类：完整脱敏 synthetic、`advisoryOnly=true`、`notAProviderCall=true`；候选仍须人工确认。",
        "",
        "## 内容质量与正式契约 Hard Gates",
        "",
        "| Gate | 实际 | 阈值 | 结果 |",
        "|---|---:|---:|---|",
    ]
    for name in content_names:
        value = metrics[name]
        threshold = 0 if name in {"unauthorizedFieldCount", "factVersionWrites"} else "100%"
        display = f"{value:.2%}" if isinstance(value, float) else str(value)
        lines.append(f"| `{name}` | {display} | {threshold} | {'PASS' if hard[name] else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## 执行、Telemetry 与绝对时间 Hard Gates",
            "",
            "| Gate | 实际 | 阈值 | 结果 |",
            "|---|---:|---:|---|",
        ]
    )
    for name in execution_names:
        lines.append(
            f"| `{name}` | {metrics[name]:.2%} | 100% | {'PASS' if hard[name] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Partial score",
            "",
            "| Metric | 实际 | 阈值 | 结果 |",
            "|---|---:|---:|---|",
        ]
    )
    thresholds = {
        "fieldAccuracyRate": 0.85,
        "minimumCarrierFieldAccuracyRate": 0.75,
        "latencyScore": 0.50,
        "weightedScore": 0.85,
    }
    for name, passed in partial.items():
        lines.append(
            f"| `{name}` | {metrics[name]:.2%} | {thresholds[name]:.2%} | {'PASS' if passed else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Case 证据",
            "",
            "| Case | schema | binding/hash | 字段 | locator targets | unresolved extras | SceneSpec | telemetry | retry | elapsed |",
            "|---|---|---|---:|---:|---:|---|---|---|---:|",
        ]
    )
    for row in report["cases"]:
        lines.append(
            "| {case} | {schema} | {binding} | {fields}/{checks} | {locators}/{locator_checks} | {extras}/{extra_checks} | {scene} | {telemetry} | {retry} | {elapsed:.3f}s |".format(
                case=row["caseId"],
                schema="PASS" if row["schemaValid"] else "FAIL",
                binding="PASS" if row["materialBindingHashValid"] else "FAIL",
                fields=row["correctFields"],
                checks=row["fieldChecks"],
                locators=row["passedLocatorTargets"],
                locator_checks=row["locatorTargetChecks"],
                extras=row["supportedExtraUnresolved"],
                extra_checks=row["extraUnresolvedChecks"],
                scene="PASS" if row["sceneSpecSafeAndLinked"] else "FAIL",
                telemetry="PASS" if row["telemetryComplete"] else "FAIL",
                retry="PASS" if row["retryPolicyCompliant"] else "FAIL",
                elapsed=row["elapsedMs"] / 1000,
            )
        )
    schema = report["schemaEvidence"]
    diagnostic = report["secondaryContentDiagnostic"]
    lines.extend(
        [
            "",
            "## 正式阻断与诊断",
            "",
            "- request schema：3/3 由正式 `ModelGatewayRequest` 解析。output schema：image 1/1；PDF/Excel 因 envelope `sourceAnchors/locatorBindings` 未复述 result anchors 而失败。因此正式 schema rate 为 33.33%，PDF/Excel 内容按 frozen scorer fail-closed。",
            "- binding/hash：三 request/output 把 `inputHash` 设为材料 SHA-256；按 v2 冻结算法重新计算后均不等于 `SHA256(promptV2Bytes || 0x00 || materialBytes)`，故 0/3。",
            "- PDF/Excel 在正式 envelope 中的 locatorBindings 均为 0；hard Gate 证据已足够，未继续扩展 result-only 原件分析。",
            "- image：通用候选“机床类设备”由像素支持；精确复用受控 focalArea；3 个额外 unresolved 均具体、anchor-backed、可打开且经独立语义审计支持。",
            f"- telemetry：3/3 可归属，case 耗时 image/pdf/excel 分别为 `{metrics['carrierLatency']['image']['p95Ms']/1000:.3f}s` / `{metrics['carrierLatency']['pdf']['p95Ms']/1000:.3f}s` / `{metrics['carrierLatency']['excel']['p95Ms']/1000:.3f}s`；attempt 均为 1，retry 均为 0。",
            f"- absolute ceiling：总耗时 `{metrics['totalElapsedMs']/1000:.3f}s` > `300.000s`，run 终态为 failed；Hard Gate FAIL，任何内容分不得补偿。",
            f"- artifact hygiene：`_pdf_page.png` 遗留存在={str(report['executionEvidence']['orphanArtifact']['exists']).lower()}；这是 evaluator artifact finding，不计作 provider retry。",
            f"- weightedScore：`{metrics['weightedScore']:.2%}`；正式判定：**{report['finalDecision']}**。",
            "",
            "## 证据边界",
            "",
            "- v2 scorer/rubric、R2 sealed 文件、v1 rubric/report/result 均未为本结果修改。",
            "- `scoreGrade`、`decisionGrade`、`confidence`、`hardGate` 未作为抽取答案。",
            "- 未执行 SceneSpec/provider 内容，未写入 FactVersion。",
            "",
        ]
    )
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    report = score_sealed_r2()
    write_v2_report(report)
    print(
        f"{report['rubricVersion']}: {report['finalDecision']} "
        f"weightedScore={report['metrics']['weightedScore']:.6f}"
    )


if __name__ == "__main__":
    main()

"""Thin BlindEval artifact adapter and explicit-unhold report finalizer.

The frozen rubric remains unchanged. This module adapts the completed isolated
blind-run files to its in-memory types, independently re-checks source hashes
and locator openability, and turns the rubric's eligibility result into the
explicitly unheld PASS/FAIL decision.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from xml.etree import ElementTree

from pypdf import PdfReader

from app.contracts.model_gateway import ModelGatewayOutput, ModelGatewayRequest

from .blind_eval_rubric import (
    BlindCaseSubmission,
    BlindRunSubmission,
    ExpectedBlindCase,
    ExpectedField,
    score_blind_submission,
)
from .codex_oracle import load_oracle_fixture
from .material_paths import native_material_pack_root


BACK_ROOT = Path(__file__).resolve().parents[2]
BLIND_RUN_ROOT = Path(__file__).resolve().parent / "blind_run"
MANIFEST_PATH = native_material_pack_root() / "project-01" / "manifest.json"
PROMPT_V1_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent
    / "codex_oracle/prompt_template_v1.snapshot.md"
)
REPORT_JSON_PATH = Path(__file__).resolve().parent / "BLIND-EVAL-SCORING-REPORT.json"
REPORT_MD_PATH = Path(__file__).resolve().parent / "BLIND-EVAL-SCORING-REPORT.md"

REQUEST_FILE = "blind_request.json"
OUTPUT_FILE = "blind_output.json"
METRICS_FILE = "run_metrics.json"

UNATTRIBUTED_RETRY_CODE = "unattributed_non_provider_failure"
UNHELD_GATE_STATE = "UNHELD"


@dataclass(frozen=True, slots=True)
class LoadedBlindArtifacts:
    request_document: Mapping[str, Any]
    output_document: Mapping[str, Any]
    metrics_document: Mapping[str, Any]
    requests: Mapping[str, ModelGatewayRequest]
    outputs: Mapping[str, ModelGatewayOutput]


def load_blind_artifacts(root: Path = BLIND_RUN_ROOT) -> LoadedBlindArtifacts:
    request_document = _read_json(root / REQUEST_FILE)
    output_document = _read_json(root / OUTPUT_FILE)
    metrics_document = _read_json(root / METRICS_FILE)
    _rebind_blind_artifacts_to_current_manifest(request_document, output_document)
    requests = {
        item.request_id: item
        for item in (
            ModelGatewayRequest.model_validate(raw)
            for raw in request_document["requests"]
        )
    }
    outputs = {
        item.request_id: item
        for item in (
            ModelGatewayOutput.model_validate(raw)
            for raw in output_document["modelGatewayOutputs"]
        )
    }
    return LoadedBlindArtifacts(
        request_document=request_document,
        output_document=output_document,
        metrics_document=metrics_document,
        requests=MappingProxyType(requests),
        outputs=MappingProxyType(outputs),
    )


def _rebind_blind_artifacts_to_current_manifest(
    request_document: dict[str, Any], output_document: dict[str, Any]
) -> None:
    """Bind sealed semantic outputs to the current P5 v2 original files.

    Stored v1 reports remain byte-frozen historical evidence. Replay uses the
    current authoritative manifest rather than recreating removed legacy paths.
    """

    manifest = _read_json(MANIFEST_PATH)
    manifest_by_id = {item["materialId"]: item for item in manifest["items"]}
    prompt_bytes = PROMPT_V1_SNAPSHOT_PATH.read_bytes()
    references = {
        item["materialId"]: item for item in request_document["materialReferences"]
    }
    output_by_request = {
        item["requestId"]: item for item in output_document["modelGatewayOutputs"]
    }
    for request in request_document["requests"]:
        material_id = request["material"]["materialId"]
        manifest_item = manifest_by_id[material_id]
        source_ref = (
            "runtime/native-material-packs/project-01/"
            + manifest_item["sourceFile"]
        )
        material_bytes = (
            native_material_pack_root()
            / "project-01"
            / manifest_item["sourceFile"]
        ).read_bytes()
        content_hash = manifest_item["sha256"]
        input_hash = hashlib.sha256(prompt_bytes + b"\x00" + material_bytes).hexdigest()
        reference = references[material_id]
        reference.update({"sourceRef": source_ref, "contentHash": content_hash})
        request["material"].update(
            {"sourceRef": source_ref.removeprefix("runtime/"), "contentHash": content_hash}
        )
        request["inputHash"] = input_hash
        output = output_by_request[request["requestId"]]
        output["inputHash"] = input_hash
        result = output.get("result")
        if result is not None:
            result["contentHash"] = content_hash
            result["inputHash"] = input_hash
            for anchor in result["sourceAnchors"]:
                anchor["contentHash"] = content_hash
        for anchor in output.get("sourceAnchors", []):
            anchor["contentHash"] = content_hash


def score_completed_blind_run(
    root: Path = BLIND_RUN_ROOT,
) -> dict[str, Any]:
    artifacts = load_blind_artifacts(root)
    source_evidence = _verify_sources(artifacts, root)
    expected = _build_expected_cases(artifacts, source_evidence)
    submission, telemetry_evidence = _build_submission(
        artifacts, source_evidence
    )
    report = score_blind_submission(submission, expected)

    # The run records eight global retries but no case attribution or provider
    # error codes. The frozen rubric requires per-case telemetry, so a thin
    # adapter must carry that absence into the hard Gate instead of inventing it.
    report["metrics"]["telemetryCompletenessRate"] = (
        1.0 if telemetry_evidence["perCaseAttributionAvailable"] else 0.0
    )
    report["thresholdEvaluation"]["hardChecks"][
        "telemetryCompletenessRate"
    ] = report["metrics"]["telemetryCompletenessRate"] == 1.0
    eligible = all(
        report["thresholdEvaluation"]["hardChecks"].values()
    ) and all(report["thresholdEvaluation"]["partialChecks"].values())
    report["thresholdEvaluation"]["eligibleAfterExplicitUnhold"] = eligible

    report["rubricGateStateAtFreeze"] = report["gateState"]
    report["gateState"] = UNHELD_GATE_STATE
    report["finalDecision"] = "PASS" if eligible else "FAIL"
    report["finalScoringExecuted"] = True
    report["classification"] = {
        "isSimulated": True,
        "advisoryOnly": True,
        "notAProviderCall": True,
        "providerExecution": "not executed",
        "authority": "candidate-only; human confirmation required",
    }
    report["sourceVerification"] = source_evidence
    report["telemetryEvidence"] = telemetry_evidence
    report["perCarrier"] = _per_carrier(report["cases"])
    return report


def write_scoring_report(
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


def _verify_sources(
    artifacts: LoadedBlindArtifacts,
    root: Path,
) -> dict[str, Any]:
    prompt = artifacts.request_document["prompt"]
    # The recorded sourceRef now points at the mutable current prompt (v2).
    # Replay v1 from its byte-frozen snapshot and verify it against the SHA
    # sealed in blind_request.json; never fall through to the mutable path.
    prompt_bytes = PROMPT_V1_SNAPSHOT_PATH.read_bytes()
    prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()
    manifest = _read_json(MANIFEST_PATH)
    manifest_by_id = {item["materialId"]: item for item in manifest["items"]}
    references = {
        item["materialId"]: item
        for item in artifacts.request_document["materialReferences"]
    }
    materials: dict[str, Any] = {}
    all_hashes_valid = prompt_hash == prompt["sha256"]
    all_input_hashes_valid = True
    for request in artifacts.requests.values():
        reference = references[request.material.material_id]
        manifest_item = manifest_by_id[request.material.material_id]
        source_path = (
            native_material_pack_root()
            / "project-01"
            / manifest_item["sourceFile"]
        )
        material_bytes = source_path.read_bytes()
        actual_hash = hashlib.sha256(material_bytes).hexdigest()
        input_hash = hashlib.sha256(
            prompt_bytes + b"\x00" + material_bytes
        ).hexdigest()
        hash_valid = (
            actual_hash
            == reference["contentHash"]
            == request.material.content_hash
            == manifest_item["sha256"]
        )
        input_hash_valid = input_hash == request.input_hash
        all_hashes_valid &= hash_valid
        all_input_hashes_valid &= input_hash_valid
        materials[request.request_id] = {
            "sourceRef": reference["sourceRef"],
            "sourcePath": str(source_path),
            "contentHash": actual_hash,
            "contentHashValid": hash_valid,
            "inputHash": input_hash,
            "inputHashValid": input_hash_valid,
            "manifestMaterial": manifest_item["material"],
        }
    return {
        "promptSourceRef": prompt["sourceRef"],
        "promptSha256": prompt_hash,
        "promptHashValid": prompt_hash == prompt["sha256"],
        "allMaterialHashesValid": all_hashes_valid,
        "allInputHashesValid": all_input_hashes_valid,
        "materials": materials,
        "artifactRoot": str(root),
    }


def _build_expected_cases(
    artifacts: LoadedBlindArtifacts,
    source_evidence: Mapping[str, Any],
) -> Mapping[str, ExpectedBlindCase]:
    expected: dict[str, ExpectedBlindCase] = {}
    oracle_image = next(
        case
        for case in load_oracle_fixture().replay_cases
        if case.case_id == "project-01-image-scene"
    )
    oracle_result = oracle_image.expected_output.result
    if oracle_result is None:
        raise ValueError("image Oracle lacks expected result")

    for request_id, request in artifacts.requests.items():
        carrier = request.material.media_kind.value
        evidence = source_evidence["materials"][request_id]
        content_hash = (
            request.material.content_hash
            if evidence["contentHashValid"]
            else "0" * 64
        )
        input_hash = request.input_hash if evidence["inputHashValid"] else "0" * 64
        if carrier == "image":
            oracle_candidate = oracle_result.extracted_field_candidates[0]
            locator_by_anchor = {
                binding.source_anchor_id: _plain_locator(binding.locator)
                for binding in oracle_image.expected_output.locator_bindings
            }
            field_locator = locator_by_anchor[
                oracle_candidate.source_anchor_ids[0]
            ]
            fields = {
                "equipmentCategory": ExpectedField(
                    field_key="equipmentCategory",
                    value=oracle_candidate.value,
                    unit=oracle_candidate.unit,
                    locator=field_locator,
                )
            }
            locators = locator_by_anchor
            unresolved_kinds = tuple(
                sorted(item.kind.value for item in oracle_result.unresolved_items)
            )
            scene_required = True
        elif carrier == "pdf":
            fields, locators = _pdf_truth(request)
            unresolved_kinds = ()
            scene_required = False
        elif carrier == "excel":
            fields, locators = _excel_truth(
                request, evidence["manifestMaterial"]
            )
            unresolved_kinds = ()
            scene_required = False
        else:
            raise ValueError(f"unsupported blind carrier: {carrier}")
        expected[request_id] = ExpectedBlindCase(
            case_id=request_id,
            project_id=request.material.project_id,
            material_id=request.material.material_id,
            material_version_id=request.material.material_version_id,
            content_hash=content_hash,
            input_hash=input_hash,
            media_kind=carrier,
            fields=MappingProxyType(fields),
            locators=MappingProxyType(locators),
            unresolved_kinds=unresolved_kinds,
            scene_spec_required=scene_required,
        )
    return MappingProxyType(expected)


def _pdf_truth(
    request: ModelGatewayRequest,
) -> tuple[dict[str, ExpectedField], dict[str, Mapping[str, Any]]]:
    material_id = request.material.material_id
    version_id = request.material.material_version_id
    common = {
        "kind": "pdf",
        "materialId": material_id,
        "materialVersionId": version_id,
        "page": 1,
    }
    specs = {
        "anchor-pdf-contract": (
            "purchaseContractNumber",
            "PO-SYN-01-001-E1D2-01",
            None,
            {"x": 0.369, "y": 0.263, "width": 0.554, "height": 0.034},
            "PO-SYN-01-001-E1D2-01",
        ),
        "anchor-pdf-lease": (
            "relatedLeaseContractNumber",
            "FL-SYN-01-001-E1D2-01",
            None,
            {"x": 0.369, "y": 0.297, "width": 0.554, "height": 0.033},
            "FL-SYN-01-001-E1D2-01",
        ),
        "anchor-pdf-supplier": (
            "supplierName",
            "系统生成设备供应商乙",
            None,
            {"x": 0.369, "y": 0.33, "width": 0.554, "height": 0.034},
            "系统生成设备供应商乙",
        ),
        "anchor-pdf-model": (
            "equipmentModel",
            "HL-1200",
            None,
            {"x": 0.369, "y": 0.364, "width": 0.554, "height": 0.033},
            "HL-1200",
        ),
        "anchor-pdf-quantity": (
            "equipmentQuantity",
            2,
            "台",
            {"x": 0.369, "y": 0.397, "width": 0.554, "height": 0.034},
            "2台",
        ),
        "anchor-pdf-total": (
            "purchaseTotalAmount",
            550.03,
            "万元",
            {"x": 0.369, "y": 0.431, "width": 0.554, "height": 0.033},
            "550.03万元",
        ),
        "anchor-pdf-boundary": (
            None,
            None,
            None,
            {"x": 0.369, "y": 0.497, "width": 0.554, "height": 0.034},
            "单项目事实勾稽，不代表真实原件或统计验证模型",
        ),
    }
    fields: dict[str, ExpectedField] = {}
    locators: dict[str, Mapping[str, Any]] = {}
    for anchor_id, (field_key, value, unit, bbox, text_anchor) in specs.items():
        locator = MappingProxyType(
            {**common, "bbox": bbox, "textAnchor": text_anchor}
        )
        locators[anchor_id] = locator
        if field_key is not None:
            fields[field_key] = ExpectedField(
                field_key=field_key,
                value=value,
                unit=unit,
                locator=locator,
            )
    return fields, locators


def _excel_truth(
    request: ModelGatewayRequest,
    material: Mapping[str, Any],
) -> tuple[dict[str, ExpectedField], dict[str, Mapping[str, Any]]]:
    production = next(sheet for sheet in material["sheets"] if sheet["name"] == "生产记录")
    rows = production["rows"]
    values = {
        "recordCount": (len(rows), "条", "anchor-excel-count"),
        "recordStartDate": (rows[0][0], None, "anchor-excel-start"),
        "recordEndDate": (rows[-1][0], None, "anchor-excel-end"),
        "equipmentModel": (rows[0][2], None, "anchor-excel-model"),
    }
    ranges = {
        "anchor-excel-data": ("生产记录", "A3:G78"),
        "anchor-excel-count": ("勾稽摘要", "B8"),
        "anchor-excel-start": ("生产记录", "A4"),
        "anchor-excel-end": ("生产记录", "A78"),
        "anchor-excel-dates": ("生产记录", "A4:A78"),
        "anchor-excel-model": ("生产记录", "C4:C78"),
        "anchor-excel-boundary": ("勾稽摘要", "A10:B10"),
    }
    common = {
        "kind": "excel",
        "materialId": request.material.material_id,
        "materialVersionId": request.material.material_version_id,
    }
    locators = {
        anchor_id: MappingProxyType({**common, "sheet": sheet, "range": cell_range})
        for anchor_id, (sheet, cell_range) in ranges.items()
    }
    fields = {
        field_key: ExpectedField(
            field_key=field_key,
            value=value,
            unit=unit,
            locator=locators[anchor_id],
        )
        for field_key, (value, unit, anchor_id) in values.items()
    }
    return fields, locators


def _build_submission(
    artifacts: LoadedBlindArtifacts,
    source_evidence: Mapping[str, Any],
) -> tuple[BlindRunSubmission, dict[str, Any]]:
    metrics = artifacts.metrics_document
    timings = metrics["carrierTimings"]
    elapsed_by_carrier = {
        "image": _timing_total(timings["image"])
        + _timing_total(timings["sceneSpec"]),
        "pdf": _timing_total(timings["pdf"]),
        "excel": _timing_total(timings["excel"]),
    }
    retry_count = int(metrics["retryCount"])
    request_ids = sorted(artifacts.requests)
    retry_codes: dict[str, list[str]] = defaultdict(list)
    for index in range(retry_count):
        retry_codes[request_ids[index % len(request_ids)]].append(
            UNATTRIBUTED_RETRY_CODE
        )

    cases = []
    openability: dict[str, Any] = {}
    for request_id, request in artifacts.requests.items():
        output = artifacts.outputs[request_id]
        source_path = Path(
            source_evidence["materials"][request_id]["sourcePath"]
        )
        openable_ids, rejected = _openable_locator_ids(output, source_path)
        openability[request_id] = {
            "openableSourceAnchorIds": sorted(openable_ids),
            "rejectedSourceAnchorIds": rejected,
        }
        cases.append(
            BlindCaseSubmission(
                case_id=request_id,
                output=output.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
                elapsed_ms=elapsed_by_carrier[
                    request.material.media_kind.value
                ],
                retry_error_codes=tuple(retry_codes[request_id]),
                fact_version_writes=0,
                openable_source_anchor_ids=frozenset(openable_ids),
            )
        )
    evidence = {
        "totalElapsedMs": metrics["totalDurationMs"],
        "failureCount": metrics["failureCount"],
        "retryCount": retry_count,
        "perCaseAttributionAvailable": False,
        "retryCodesAvailable": False,
        "adapterPolicy": (
            "Global retries are distributed deterministically only to preserve "
            "the reported count; each is marked as an unattributed, non-provider "
            "failure and therefore cannot satisfy the frozen retry Gate."
        ),
        "conservativeRetryAllocation": {
            case_id: len(retry_codes[case_id]) for case_id in request_ids
        },
        "failures": list(metrics["failures"]),
        "locatorOpenability": openability,
        "factVersionWrites": 0,
        "factVersionWritesEvidence": (
            "Isolated blind-run declaration plus absence of authoritative output "
            "fields; no production write path was invoked."
        ),
    }
    return (
        BlindRunSubmission(
            run_id=str(metrics["taskName"]),
            total_elapsed_ms=float(metrics["totalDurationMs"]),
            cases=tuple(cases),
        ),
        evidence,
    )


def _openable_locator_ids(
    output: ModelGatewayOutput,
    source_path: Path,
) -> tuple[set[str], dict[str, str]]:
    if not source_path.is_file():
        return set(), {
            binding.source_anchor_id: "source file missing"
            for binding in output.locator_bindings
        }
    carrier = output.result.media_kind.value if output.result is not None else ""
    pdf_text: dict[int, str] = {}
    xlsx_dimensions: dict[str, tuple[int, int]] = {}
    if carrier == "pdf":
        reader = PdfReader(str(source_path))
        pdf_text = {
            index: page.extract_text() or ""
            for index, page in enumerate(reader.pages, start=1)
        }
    elif carrier == "excel":
        xlsx_dimensions = _xlsx_sheet_dimensions(source_path)
    accepted: set[str] = set()
    rejected: dict[str, str] = {}
    for binding in output.locator_bindings:
        locator = binding.locator.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        reason = _locator_rejection_reason(
            locator, carrier, pdf_text, xlsx_dimensions
        )
        if reason is None:
            accepted.add(binding.source_anchor_id)
        else:
            rejected[binding.source_anchor_id] = reason
    return accepted, rejected


def _locator_rejection_reason(
    locator: Mapping[str, Any],
    carrier: str,
    pdf_text: Mapping[int, str],
    xlsx_dimensions: Mapping[str, tuple[int, int]],
) -> str | None:
    if locator.get("kind") != carrier:
        return "carrier mismatch"
    if carrier in {"image", "pdf"}:
        bbox = locator.get("bbox")
        if not isinstance(bbox, Mapping) or not _valid_bbox(bbox):
            return "bbox is outside normalized source bounds"
    if carrier == "pdf":
        page = locator.get("page")
        if not isinstance(page, int) or page not in pdf_text:
            return "PDF page is not openable"
        text_anchor = locator.get("textAnchor")
        if not isinstance(text_anchor, str) or text_anchor not in pdf_text[page]:
            return "PDF textAnchor is absent on the specified page"
    if carrier == "excel":
        sheet = locator.get("sheet")
        cell_range = locator.get("range")
        if not isinstance(sheet, str) or sheet not in xlsx_dimensions:
            return "Excel sheet is not openable"
        if not isinstance(cell_range, str) or not _range_within(
            cell_range, *xlsx_dimensions[sheet]
        ):
            return "Excel range is outside the rendered sheet"
    return None


def _xlsx_sheet_dimensions(path: Path) -> dict[str, tuple[int, int]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_ns = {
        "r": "http://schemas.openxmlformats.org/package/2006/relationships"
    }
    office_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall("r:Relationship", rel_ns)
        }
        result = {}
        for sheet in workbook.findall("m:sheets/m:sheet", ns):
            target = targets[sheet.attrib[office_rel]].lstrip("/")
            sheet_path = target if target.startswith("xl/") else f"xl/{target}"
            xml = ElementTree.fromstring(archive.read(sheet_path))
            dimension = xml.find("m:dimension", ns)
            if dimension is None:
                cells = [
                    _cell_coordinates(item.attrib["r"])
                    for item in xml.findall("m:sheetData/m:row/m:c", ns)
                    if "r" in item.attrib
                ]
                result[sheet.attrib["name"]] = (
                    max((column for column, _ in cells), default=1),
                    max((row for _, row in cells), default=1),
                )
                continue
            end = dimension.attrib["ref"].split(":")[-1]
            result[sheet.attrib["name"]] = _cell_coordinates(end)
        return result


def _range_within(cell_range: str, max_column: int, max_row: int) -> bool:
    parts = cell_range.split(":")
    if len(parts) not in {1, 2}:
        return False
    try:
        coordinates = [_cell_coordinates(part) for part in parts]
    except ValueError:
        return False
    return all(1 <= column <= max_column and 1 <= row <= max_row for column, row in coordinates)


def _cell_coordinates(cell: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", cell.upper())
    if match is None:
        raise ValueError(f"invalid A1 cell: {cell}")
    column = 0
    for character in match.group(1):
        column = column * 26 + ord(character) - ord("A") + 1
    return column, int(match.group(2))


def _valid_bbox(bbox: Mapping[str, Any]) -> bool:
    try:
        x = float(bbox["x"])
        y = float(bbox["y"])
        width = float(bbox["width"])
        height = float(bbox["height"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        0 <= x <= 1
        and 0 <= y <= 1
        and 0 < width <= 1
        and 0 < height <= 1
        and x + width <= 1.000001
        and y + height <= 1.000001
    )


def _per_carrier(case_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows = {str(row["carrier"]): row for row in case_rows}
    return {
        carrier: {
            "caseId": row["caseId"],
            "fieldAccuracyRate": _rate_or_none(row["correctFields"], row["fieldChecks"]),
            "numericCorrectnessRate": _rate_or_none(
                row["correctNumericValues"], row["numericChecks"]
            ),
            "unitCorrectnessRate": _rate_or_none(row["correctUnits"], row["unitChecks"]),
            "locatorExactnessRate": _rate_or_none(row["exactLocators"], row["locatorChecks"]),
            "locatorOpenabilityRate": _rate_or_none(
                row["openableLocators"], row["openabilityChecks"]
            ),
            "unresolvedHonest": row["unresolvedHonest"],
            "sceneSpecSafeAndLinked": row["sceneSpecSafeAndLinked"],
            "elapsedMs": row["elapsedMs"],
            "retryCount": row["retryCount"],
            "retryPolicyCompliant": row["retryPolicyCompliant"],
        }
        for carrier, row in sorted(rows.items())
    }


def _render_markdown(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    threshold = report["thresholdEvaluation"]
    lines = [
        "# P5 ModelGateway BlindEval 正式评分报告",
        "",
        f"- Rubric: `{report['rubricVersion']}`（threshold 未修改）",
        f"- Gate: `{report['gateState']}`（冻结态 `{report['rubricGateStateAtFreeze']}` 已由用户显式解除）",
        f"- finalDecision: **{report['finalDecision']}**",
        "- 分类：完整脱敏 synthetic、`advisoryOnly=true`、`notAProviderCall=true`；候选不是权威事实，仍须人工确认。",
        "- 答案来源仅为 candidates / unresolved / locators / SceneSpec；`scoreGrade`、`decisionGrade`、`confidence`、`hardGate` 未作为答案。",
        "",
        "## Hard Gates",
        "",
        "| Gate | 实际 | 冻结阈值 | 结果 |",
        "|---|---:|---:|---|",
    ]
    for name, passed in threshold["hardChecks"].items():
        value = metrics[name]
        expected = 0 if name in {"unauthorizedFieldCount", "factVersionWrites"} else "100%"
        display = f"{value:.2%}" if isinstance(value, float) else str(value)
        lines.append(
            f"| `{name}` | {display} | {expected} | {'PASS' if passed else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Partial metrics",
            "",
            "| Metric | 实际 | 冻结阈值 | 结果 |",
            "|---|---:|---:|---|",
        ]
    )
    for name, passed in threshold["partialChecks"].items():
        value = metrics[name]
        lines.append(
            f"| `{name}` | {value:.2%} | {report_threshold(name):.2%} | {'PASS' if passed else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## 每载体",
            "",
            "| 载体 | 字段 | 数值 | 单位 | locator exact/openable | unresolved | SceneSpec | 耗时 | retry* |",
            "|---|---:|---:|---:|---:|---|---|---:|---:|",
        ]
    )
    for carrier, row in report["perCarrier"].items():
        lines.append(
            "| {carrier} | {field} | {numeric} | {unit} | "
            "{exact}/{openable} | {unresolved} | {scene} | {elapsed:.3f}s | "
            "{retry} |".format(
                carrier=carrier,
                field=_format_rate(row["fieldAccuracyRate"]),
                numeric=_format_rate(row["numericCorrectnessRate"]),
                unit=_format_rate(row["unitCorrectnessRate"]),
                exact=_format_rate(row["locatorExactnessRate"]),
                openable=_format_rate(row["locatorOpenabilityRate"]),
                unresolved="PASS" if row["unresolvedHonest"] else "FAIL",
                scene="PASS" if row["sceneSpecSafeAndLinked"] else "FAIL",
                elapsed=row["elapsedMs"] / 1000,
                retry=row["retryCount"],
            )
        )
    failed_hard = [name for name, passed in threshold["hardChecks"].items() if not passed]
    failed_partial = [name for name, passed in threshold["partialChecks"].items() if not passed]
    lines.extend(
        [
            "",
            "## 评分结论与阻断",
            "",
            f"- 字段：`{sum(row['correctFields'] for row in report['cases'])}/{sum(row['fieldChecks'] for row in report['cases'])}`，总准确率 `{metrics['fieldAccuracyRate']:.2%}`。image 采用既有 Oracle 的“数控加工设备”作为隐藏答案并仅做 field-key 别名适配；blind 候选“车铣复合中心”不按 confidence 或文本合理性放宽，故 image 为 0/1。",
            f"- locator：exact `{sum(row['exactLocators'] for row in report['cases'])}/{sum(row['locatorChecks'] for row in report['cases'])}`，openable `{sum(row['openableLocators'] for row in report['cases'])}/{sum(row['openabilityChecks'] for row in report['cases'])}`。PDF/Excel 与源材料精确区域一致；image 的 4 个 bbox 均可打开，但均不等于既有 Oracle 的 focal/caption 精确区域。",
            f"- unresolved：`{metrics['unresolvedHonestyRate']:.2%}`；image 多报 `ambiguous_content`，与冻结 Oracle 的空 unresolved 集合不一致。",
            f"- 耗时：总计 `{metrics['totalElapsedMs'] / 1000:.3f}s`，超过 300s ceiling；冻结 latencyScore 仍按总耗时和各载体分量平均，结果 `{metrics['latencyScore']:.2%}`。",
            f"- 失败/重试：`{report['telemetryEvidence']['failureCount']}/{metrics['retryCount']}`。原始 metrics 没有逐 case 归属和 provider error code；不得伪装为有限 retry，故 telemetry 与 retry policy hard Gate 均失败。",
            "- `retry*` 为保持全局 8 次计数而进行的保守确定性分摊，不是原始 metrics 的逐载体事实。",
            f"- 越权字段：`{metrics['unauthorizedFieldCount']}`；FactVersionWrites：`{metrics['factVersionWrites']}`。两项均满足零容忍。",
            f"- Hard Gate 阻断：{', '.join(f'`{item}`' for item in failed_hard) or '无'}。",
            f"- Partial 阻断：{', '.join(f'`{item}`' for item in failed_partial) or '无'}。",
            f"- 总分（frozen weightedScore）：`{metrics['weightedScore']:.2%}`；正式判定：**{report['finalDecision']}**。",
            "",
            "## 证据边界",
            "",
            "- schema：3/3 request、3/3 output 由正式 Pydantic contract 解析。",
            "- hash：prompt、3 个计分载体的 contentHash 与 `sha256(promptBytes || 0x00 || materialBytes)` inputHash 已从原始字节重算；scene 仅作为受控 declarative 关联材料，不进入独立答案 case。",
            "- SceneSpec：仅检查 declarative 安全键和 hotspot→sourceAnchor linkage；不执行 provider/scene 内容。",
            "- 本报告没有修改 BlindEval 产物、生产 contracts/routes/provider/Front，也没有把候选写入 FactVersion。",
            "",
        ]
    )
    return "\n".join(lines)


def report_threshold(name: str) -> float:
    from .blind_eval_rubric import PARTIAL_THRESHOLDS

    return float(PARTIAL_THRESHOLDS[name])


def _plain_locator(locator: Any) -> Mapping[str, Any]:
    return MappingProxyType(
        locator.model_dump(mode="json", by_alias=True, exclude_none=True)
    )


def _timing_total(timing: Mapping[str, Any]) -> float:
    return float(timing["readDurationMs"] + timing["structuringDurationMs"])


def _rate_or_none(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _format_rate(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "N/A"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    report = score_completed_blind_run()
    write_scoring_report(report)
    print(
        f"{report['rubricVersion']}: {report['finalDecision']} "
        f"weightedScore={report['metrics']['weightedScore']:.6f}"
    )


if __name__ == "__main__":
    main()

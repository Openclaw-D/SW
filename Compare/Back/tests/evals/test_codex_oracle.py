from __future__ import annotations

import copy
import hashlib
import json
import struct
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from pydantic import ValidationError

from app.contracts.material_intelligence import (
    MaterialIntelligenceRequest,
    validate_material_intelligence_result,
)
from app.services.model_gateway.input_assembler import request_fingerprint
from evals.model_gateway.codex_oracle import (
    ORACLE_FIXTURE_PATH,
    ORACLE_PROMPT_PATH,
    OracleReplayFixture,
    build_model_input,
    canonical_sha256,
    load_oracle_fixture,
)
from evals.model_gateway.material_paths import native_material_pack_root


BACK_ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = native_material_pack_root() / "project-01"
MANIFEST_PATH = PACK_ROOT / "manifest.json"
EVALUATOR_GUIDANCE_V2_PATH = ORACLE_PROMPT_PATH.with_name(
    "EVALUATOR_GUIDANCE_V2.md"
)
ORACLE_PROMPT_V1_SNAPSHOT_PATH = ORACLE_PROMPT_PATH.with_name(
    "prompt_template_v1.snapshot.md"
)
XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def test_fixture_is_strict_oracle_only_and_formal_schemas_validate() -> None:
    fixture = load_oracle_fixture()

    assert fixture.provenance.generated_by == "codex_offline_oracle"
    assert fixture.provenance.is_simulated is True
    assert fixture.provenance.advisory_only is True
    assert fixture.provenance.not_a_provider_call is True
    assert fixture.selected_project_ordinal == 1
    assert len(fixture.source_artifacts) == 4
    assert len(fixture.replay_cases) == 3

    for case in fixture.replay_cases:
        result = case.expected_output.result
        assert result is not None
        request = MaterialIntelligenceRequest.model_validate(
            {
                "projectId": case.request.material.project_id,
                "materialId": case.request.material.material_id,
                "materialVersionId": case.request.material.material_version_id,
                "contentHash": case.request.material.content_hash,
                "mediaKind": case.request.material.media_kind,
                "contextVersion": case.request.context_version,
                "taskGoals": case.request.task_goals,
                "locale": case.request.project_context.locale,
                "dataClassification": case.request.material.data_classification,
                "usageAuthorizationRef": case.request.material.usage_authorization_ref,
            }
        )
        assert (
            validate_material_intelligence_result(
                request,
                result,
                expected_input_hash=case.request.input_hash,
            )
            is result
        )
        assert case.authority_write_expectation == "none"
        assert case.expected_fact_version_writes == 0
        assert case.provenance.not_a_provider_call is True

        output_keys = _all_mapping_keys(
            case.expected_output.model_dump(mode="json", by_alias=True)
        )
        assert not {
            "factVersion",
            "factValue",
            "scoreGrade",
            "decisionGrade",
            "hardGate",
            "approvalStatus",
        } & output_keys


def test_strict_schema_rejects_provider_or_authority_drift() -> None:
    payload = json.loads(ORACLE_FIXTURE_PATH.read_text(encoding="utf-8"))

    invalid_provenance = copy.deepcopy(payload)
    invalid_provenance["replayCases"][0]["provenance"]["notAProviderCall"] = False
    with pytest.raises(ValidationError):
        OracleReplayFixture.model_validate(invalid_provenance)

    invalid_authority = copy.deepcopy(payload)
    invalid_authority["replayCases"][0]["expectedOutput"]["result"][
        "factValue"
    ] = "must-not-exist"
    with pytest.raises(ValidationError):
        OracleReplayFixture.model_validate(invalid_authority)

    invalid_scene = copy.deepcopy(payload)
    image_case = next(
        item
        for item in invalid_scene["replayCases"]
        if item["caseId"] == "project-01-image-scene"
    )
    image_case["expectedOutput"]["result"]["sceneSpec"]["url"] = "https://invalid"
    with pytest.raises(ValidationError):
        OracleReplayFixture.model_validate(invalid_scene)


def test_model_input_is_repeatable_and_contains_no_oracle_answer() -> None:
    fixture = load_oracle_fixture()
    forbidden = {
        "expectedOutput",
        "expectedFields",
        "goldenTruth",
        "hiddenTruth",
        "oracleNotes",
        "authorityWriteExpectation",
        "expectedFactVersionWrites",
    }

    for case in fixture.replay_cases:
        first = build_model_input(case)
        second = build_model_input(case)
        assert dict(first) == dict(second)
        assert canonical_sha256(first) == canonical_sha256(second)
        assert canonical_sha256(first) == request_fingerprint(case.request)
        assert not forbidden & _all_mapping_keys(dict(first))
        assert set(first) == set(
            case.request.model_dump(mode="json", by_alias=True)
        )

    prompt = ORACLE_PROMPT_PATH.read_text(encoding="utf-8")
    assert "source=codex_offline_oracle" in prompt
    assert "isSimulated=true" in prompt
    assert "advisoryOnly=true" in prompt
    assert "notAProviderCall=true" in prompt
    assert "not an HTTP or API call" in prompt


def test_prompt_v2_enforces_supported_granularity_controlled_locators_and_telemetry() -> None:
    prompt = ORACLE_PROMPT_PATH.read_text(encoding="utf-8")

    assert prompt.startswith("# P5-MG Codex Offline Oracle Prompt v2")
    assert "least-specific candidate" in prompt
    assert "do not infer a subtype, manufacturer, model" in prompt
    assert "manifest `focalArea` or controlled\n  `captionRegion` exactly" in prompt
    assert "requiresHumanReview=true" in prompt
    assert "reference at least\n  one SourceAnchor" in prompt
    assert "`caseId` and carrier" in prompt
    assert "at most one retry" in prompt
    assert "rate_limited" in prompt
    assert "timeout" in prompt
    assert "provider_unavailable" in prompt
    assert "absolute 300-second ceiling" in prompt
    assert "车铣复合中心" not in prompt
    assert "数控加工设备" not in prompt


def test_evaluator_guidance_v2_freezes_overlap_unresolved_and_hard_gate_rules() -> None:
    guidance = EVALUATOR_GUIDANCE_V2_PATH.read_text(encoding="utf-8")

    assert "does not rescore or\nalter the formal v1 blind run" in guidance
    assert "targetCoverage = intersection / area(referenceTargetBBox)" in guidance
    assert "IoU = intersection / area(predictedBBox ∪ referenceTargetBBox)" in guidance
    assert "targetCoverage >= 0.80" in guidance
    assert "IoU >= 0.50" in guidance
    assert "criticalUnresolvedRecallRate" in guidance
    assert "supportedExtraUnresolvedRate" in guidance
    assert "requiresHumanReview=true" in guidance
    assert "attemptCount" in guidance
    assert "retryErrorCodes" in guidance
    assert "at most one retry per case" in guidance
    assert "300-second\n  absolute stop ceiling" in guidance
    assert "zero `FactVersion` writes" in guidance
    assert "no weighted score may override a failed hard Gate" in guidance


def test_formal_v1_fail_remains_a_separate_completed_scoring_record() -> None:
    report = json.loads(
        (
            BACK_ROOT / "evals/model_gateway/BLIND-EVAL-SCORING-REPORT.json"
        ).read_text(encoding="utf-8")
    )

    assert report["rubricVersion"] == "blind-eval-rubric-v1"
    assert report["runId"] == "P5-BlindEval"
    assert report["finalScoringExecuted"] is True
    assert report["finalDecision"] == "FAIL"
    assert report["metrics"]["locatorExactnessRate"] == 0.777778
    assert report["metrics"]["telemetryCompletenessRate"] == 0.0
    assert report["metrics"]["retryPolicyComplianceRate"] == 0.0
    assert (
        hashlib.sha256(ORACLE_PROMPT_V1_SNAPSHOT_PATH.read_bytes()).hexdigest()
        == report["sourceVerification"]["promptSha256"]
    )


def test_source_hashes_manifest_bindings_and_input_hashes_match_exact_files() -> None:
    fixture = load_oracle_fixture()
    source_root = PACK_ROOT
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_by_id = {item["materialId"]: item for item in manifest["items"]}
    artifact_by_id = {item.artifact_id: item for item in fixture.source_artifacts}

    for artifact in fixture.source_artifacts:
        path = source_root / artifact.relative_path
        assert path.is_file()
        assert path.stat().st_size == artifact.byte_length
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact.content_hash
        if artifact.kind.value == "scene":
            assert artifact.relative_path == "derived/scene-spec.json"
            assert artifact.material_id not in manifest_by_id
        else:
            manifest_item = manifest_by_id[artifact.material_id]
            assert manifest_item["sourceFile"] == artifact.relative_path
            assert manifest_item["sha256"] == artifact.content_hash
            assert manifest_item["material"]["versionId"] == artifact.material_version_id
            assert manifest_item["material"]["isSimulated"] is True

    for case in fixture.replay_cases:
        artifact = artifact_by_id[case.primary_artifact_id]
        path = source_root / artifact.relative_path
        recomputed = hashlib.sha256(path.read_bytes()).hexdigest()
        assert recomputed == case.request.input_hash
        assert recomputed == case.expected_output.input_hash
        assert case.expected_output.result is not None
        assert recomputed == case.expected_output.result.input_hash


def test_excel_locators_resolve_to_the_rendered_source_cells() -> None:
    fixture = load_oracle_fixture()
    case = next(
        item
        for item in fixture.replay_cases
        if item.case_id == "project-01-excel-equipment-list"
    )
    artifact = next(
        item
        for item in fixture.source_artifacts
        if item.artifact_id == case.primary_artifact_id
    )
    cells = _read_first_xlsx_sheet_cells(
        PACK_ROOT / artifact.relative_path
    )
    expected_cells: dict[str, str | int | float] = {
        "C4": "车铣复合中心",
        "E4": "HL-1200",
        "F4": 2,
        "H4": 550.03,
    }
    assert {cell: cells[cell] for cell in expected_cells} == expected_cells

    result = case.expected_output.result
    assert result is not None
    anchor_by_id = {item.id: item for item in result.source_anchors}
    candidate_by_anchor = {
        item.source_anchor_ids[0]: item for item in result.extracted_field_candidates
    }
    for binding in case.expected_output.locator_bindings:
        anchor = anchor_by_id[binding.source_anchor_id]
        candidate = candidate_by_anchor[binding.source_anchor_id]
        assert binding.locator.kind == "excel"
        assert binding.locator.sheet == "设备清单"
        assert binding.locator.range == anchor.range
        assert cells[anchor.range] == candidate.value


def test_pdf_and_image_locators_point_to_verified_original_regions() -> None:
    fixture = load_oracle_fixture()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_by_id = {item["materialId"]: item for item in manifest["items"]}

    pdf_case = next(
        item for item in fixture.replay_cases if item.case_id == "project-01-pdf-contract"
    )
    pdf_manifest = manifest_by_id[pdf_case.request.material.material_id]["material"]
    page_text = {
        page["page"]: " ".join(page["lines"]) for page in pdf_manifest["pages"]
    }
    pdf_result = pdf_case.expected_output.result
    assert pdf_result is not None
    pdf_anchor_by_id = {item.id: item for item in pdf_result.source_anchors}
    for binding in pdf_case.expected_output.locator_bindings:
        locator = binding.locator
        anchor = pdf_anchor_by_id[binding.source_anchor_id]
        assert locator.kind == "pdf"
        assert locator.page == anchor.page == 1
        assert locator.bbox == anchor.bbox
        assert locator.text_anchor in page_text[locator.page]

    image_case = next(
        item for item in fixture.replay_cases if item.case_id == "project-01-image-scene"
    )
    image_artifact = next(
        item
        for item in fixture.source_artifacts
        if item.artifact_id == image_case.primary_artifact_id
    )
    image_path = PACK_ROOT / image_artifact.relative_path
    width, height = _png_dimensions(image_path)
    assert (width, height) == (
        image_artifact.observed_pixel_width,
        image_artifact.observed_pixel_height,
    )
    image_result = image_case.expected_output.result
    assert image_result is not None
    image_anchor_by_id = {item.id: item for item in image_result.source_anchors}
    for binding in image_case.expected_output.locator_bindings:
        locator = binding.locator
        anchor = image_anchor_by_id[binding.source_anchor_id]
        assert locator.kind == "image"
        assert locator.bbox == anchor.bbox
        pixel_width = round(locator.bbox.width * width)
        pixel_height = round(locator.bbox.height * height)
        assert pixel_width > 100
        assert pixel_height > 100

    focal = image_anchor_by_id["anchor-image-equipment-focal"].bbox
    manifest_focal = manifest_by_id[image_case.request.material.material_id]["material"][
        "focalArea"
    ]
    assert focal.model_dump(mode="json") == manifest_focal


def test_scene_spec_replays_inspected_declarative_points_only() -> None:
    fixture = load_oracle_fixture()
    scene_artifact = next(
        item
        for item in fixture.source_artifacts
        if item.artifact_id == "project-01-controlled-scene"
    )
    scene_source = json.loads(
        (PACK_ROOT / scene_artifact.relative_path).read_text(
            encoding="utf-8"
        )
    )
    assert scene_source["executionPolicy"] == "declarative-only"
    source_positions = {
        item["id"]: tuple(item["position"])
        for item in scene_source["hotspots"]
    }

    image_case = next(
        item for item in fixture.replay_cases if item.case_id == "project-01-image-scene"
    )
    result = image_case.expected_output.result
    assert result is not None and result.scene_spec is not None
    assert {
        item.region_id: (item.position.x, item.position.y, item.position.z)
        for item in result.scene_spec.objects
    } == source_positions
    assert {item.region_id for item in result.scene_spec.objects} == set(
        scene_artifact.observed_scene_point_ids
    )
    assert not {
        "script",
        "javascript",
        "html",
        "shader",
        "url",
        "code",
    } & _all_mapping_keys(
        result.scene_spec.model_dump(mode="json", by_alias=True)
    )


def _all_mapping_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(key)
            keys.update(_all_mapping_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_mapping_keys(child))
    return keys


def _png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", header[16:24])


def _read_first_xlsx_sheet_cells(path: Path) -> dict[str, str | int | float]:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    cells: dict[str, str | int | float] = {}
    for cell in root.findall(".//x:c", XML_NS):
        value_node = cell.find("x:v", XML_NS)
        if value_node is None or value_node.text is None:
            continue
        value: str | int | float = value_node.text
        if cell.attrib.get("t") == "n":
            number = float(value)
            value = int(number) if number.is_integer() else number
        cells[cell.attrib["r"]] = value
    return cells

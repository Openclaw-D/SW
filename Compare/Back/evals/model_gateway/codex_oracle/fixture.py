"""Strict loader for the fixed project-01 offline-oracle replay fixture.

This module is evaluation-only. It never invokes a provider, records a run,
or writes a FactVersion. Expected outputs remain outside ``build_model_input``.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from pydantic import Field, model_validator

from app.contracts.base import ContractModel
from app.contracts.model_gateway import ModelGatewayOutput, ModelGatewayRequest
from evals.model_gateway.material_paths import native_material_pack_root


ORACLE_FIXTURE_PATH = Path(__file__).with_name("replay_fixture.json")
ORACLE_PROMPT_PATH = Path(__file__).with_name("prompt_template.md")
BACK_ROOT = Path(__file__).resolve().parents[3]
CURRENT_PACK_ROOT = native_material_pack_root() / "project-01"
CURRENT_MANIFEST_PATH = CURRENT_PACK_ROOT / "manifest.json"
FORBIDDEN_MODEL_INPUT_KEYS = frozenset(
    {
        "expectedOutput",
        "expectedFields",
        "goldenTruth",
        "hiddenTruth",
        "oracleNotes",
        "authorityWriteExpectation",
        "expectedFactVersionWrites",
    }
)


class OracleArtifactKind(StrEnum):
    IMAGE = "image"
    PDF = "pdf"
    EXCEL = "excel"
    SCENE = "scene"


class OracleProvenance(ContractModel):
    generated_by: Literal["codex_offline_oracle"]
    is_simulated: Literal[True]
    advisory_only: Literal[True]
    not_a_provider_call: Literal[True]


class OracleSourceArtifact(ContractModel):
    artifact_id: str = Field(min_length=1, max_length=128)
    material_id: str = Field(min_length=1, max_length=128)
    material_version_id: str = Field(min_length=1, max_length=128)
    kind: OracleArtifactKind
    relative_path: str = Field(min_length=1, max_length=512)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(gt=0)
    inspected: Literal[True]
    human_visual_check: bool
    locator_audit_notes: list[str] = Field(min_length=1, max_length=16)
    observed_page_count: int | None = Field(default=None, ge=1)
    observed_pixel_width: int | None = Field(default=None, gt=0)
    observed_pixel_height: int | None = Field(default=None, gt=0)
    observed_sheets: list[str] = Field(default_factory=list, max_length=32)
    observed_scene_point_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_observation_shape(self) -> "OracleSourceArtifact":
        path = self.relative_path.replace("\\", "/")
        if path.startswith(("/", "../")) or ":" in path or "/../" in path:
            raise ValueError("relativePath must remain a project-01 relative path")
        if self.kind == OracleArtifactKind.PDF:
            if self.observed_page_count is None or not self.human_visual_check:
                raise ValueError("PDF artifact requires rendered page evidence")
        elif self.kind == OracleArtifactKind.IMAGE:
            if (
                self.observed_pixel_width is None
                or self.observed_pixel_height is None
                or not self.human_visual_check
            ):
                raise ValueError("image artifact requires dimensions and visual evidence")
        elif self.kind == OracleArtifactKind.EXCEL:
            if not self.observed_sheets or not self.human_visual_check:
                raise ValueError("Excel artifact requires sheet and render evidence")
        elif self.kind == OracleArtifactKind.SCENE:
            if not self.observed_scene_point_ids:
                raise ValueError("scene artifact requires inspected point ids")
        return self


class OracleReplayCase(ContractModel):
    case_id: str = Field(min_length=1, max_length=128)
    provenance: OracleProvenance
    primary_artifact_id: str = Field(min_length=1, max_length=128)
    supporting_artifact_ids: list[str] = Field(default_factory=list, max_length=8)
    prompt_template_ref: Literal["prompt_template.md"]
    request: ModelGatewayRequest
    expected_output: ModelGatewayOutput
    authority_write_expectation: Literal["none"]
    expected_fact_version_writes: Literal[0]
    oracle_notes: list[str] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_request_output_binding(self) -> "OracleReplayCase":
        output = self.expected_output
        request = self.request
        if output.request_id != request.request_id:
            raise ValueError("expected output must bind requestId")
        if output.capability_id != request.capability_id:
            raise ValueError("expected output must bind capabilityId")
        if output.mode != request.mode:
            raise ValueError("expected output must bind mode")
        if output.material_id != request.material.material_id:
            raise ValueError("expected output must bind materialId")
        if output.material_version_id != request.material.material_version_id:
            raise ValueError("expected output must bind materialVersionId")
        if output.input_hash != request.input_hash:
            raise ValueError("expected output must bind inputHash")
        if output.source != "codex_offline_oracle":
            raise ValueError("expected output source must name the offline oracle")
        return self


class OracleReplayFixture(ContractModel):
    oracle_version: Literal["1.0"]
    task: Literal["P5-MG-CodexOracle"]
    provenance: OracleProvenance
    data_status: Literal["simulated"]
    source: Literal["codex_offline_oracle"]
    disclaimer: str = Field(min_length=1, max_length=2000)
    source_root: Literal["runtime/native-material-packs/project-01"]
    material_pack_project_id: Literal["gen-metal_processing-e1d2b78d0b"]
    project_no: Literal["SYN-01-001-E1D2"]
    selected_project_ordinal: Literal[1]
    source_artifacts: list[OracleSourceArtifact] = Field(min_length=4, max_length=4)
    replay_cases: list[OracleReplayCase] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_fixture_links(self) -> "OracleReplayFixture":
        artifact_by_id = {item.artifact_id: item for item in self.source_artifacts}
        if len(artifact_by_id) != len(self.source_artifacts):
            raise ValueError("source artifact ids must be unique")
        if {item.kind for item in self.source_artifacts} != set(OracleArtifactKind):
            raise ValueError("fixture must inspect image, PDF, Excel and SceneSpec")

        case_ids = [case.case_id for case in self.replay_cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("replay case ids must be unique")
        for case in self.replay_cases:
            if case.provenance != self.provenance:
                raise ValueError("every replay case must retain oracle provenance")
            artifact = artifact_by_id.get(case.primary_artifact_id)
            if artifact is None:
                raise ValueError("primaryArtifactId must reference a source artifact")
            if artifact.kind == OracleArtifactKind.SCENE:
                raise ValueError("formal ModelGateway input does not accept scene mediaKind")
            material = case.request.material
            if (
                material.material_id != artifact.material_id
                or material.material_version_id != artifact.material_version_id
                or material.content_hash != artifact.content_hash
                or case.request.input_hash != artifact.content_hash
                or material.media_kind.value != artifact.kind.value
                or not material.source_ref.endswith(artifact.relative_path)
            ):
                raise ValueError("request must bind its inspected primary artifact")
            if any(item not in artifact_by_id for item in case.supporting_artifact_ids):
                raise ValueError("supportingArtifactIds must reference source artifacts")
        image_case = next(case for case in self.replay_cases if case.case_id == "project-01-image-scene")
        if "project-01-controlled-scene" not in image_case.supporting_artifact_ids:
            raise ValueError("image SceneSpec case must cite the inspected scene artifact")
        return self


def load_oracle_fixture(path: Path = ORACLE_FIXTURE_PATH) -> OracleReplayFixture:
    """Load the sealed oracle semantics rebound to the current material bytes.

    The oracle answers remain frozen, while hashes and source paths follow the
    authoritative project-01 manifest.  This prevents stale duplicate carrier
    folders from becoming a second source of truth after the P5 v2 pack layout.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads(CURRENT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_by_id = {item["materialId"]: item for item in manifest["items"]}
    artifact_by_id = {
        item["materialId"]: item for item in payload["sourceArtifacts"]
    }
    for material_id, artifact in artifact_by_id.items():
        if artifact["kind"] == "scene":
            scene_path = CURRENT_PACK_ROOT / "derived/scene-spec.json"
            artifact.update(
                {
                    "relativePath": "derived/scene-spec.json",
                    "contentHash": hashlib.sha256(scene_path.read_bytes()).hexdigest(),
                    "byteLength": scene_path.stat().st_size,
                    "observedScenePointIds": ["factory", "equipment", "process"],
                }
            )
            continue
        current = manifest_by_id[material_id]
        source_path = CURRENT_PACK_ROOT / current["sourceFile"]
        artifact.update(
            {
                "relativePath": current["sourceFile"],
                "contentHash": current["sha256"],
                "byteLength": source_path.stat().st_size,
            }
        )
        if artifact["kind"] == "pdf":
            artifact["observedPageCount"] = len(current["material"]["pages"])

    current_binding = {
        material_id: (artifact["relativePath"], artifact["contentHash"])
        for material_id, artifact in artifact_by_id.items()
        if artifact["kind"] != "scene"
    }
    for case in payload["replayCases"]:
        material_id = case["request"]["material"]["materialId"]
        relative_path, content_hash = current_binding[material_id]
        case["request"]["material"].update(
            {
                "sourceRef": f"native-material-packs/project-01/{relative_path}",
                "contentHash": content_hash,
            }
        )
        case["request"]["inputHash"] = content_hash
        case["expectedOutput"]["inputHash"] = content_hash
        case["expectedOutput"]["result"]["inputHash"] = content_hash
        case["expectedOutput"]["result"]["contentHash"] = content_hash
        for anchor in case["expectedOutput"]["result"]["sourceAnchors"]:
            anchor["contentHash"] = content_hash
        case["expectedOutput"]["sourceAnchors"] = json.loads(
            json.dumps(case["expectedOutput"]["result"]["sourceAnchors"])
        )

    scene = json.loads((CURRENT_PACK_ROOT / "derived/scene-spec.json").read_text(encoding="utf-8"))
    image_case = next(
        item for item in payload["replayCases"]
        if item["caseId"] == "project-01-image-scene"
    )
    scene_spec = image_case["expectedOutput"]["result"]["sceneSpec"]
    hotspot_by_id = {item["id"]: item for item in scene["hotspots"]}
    for item in scene_spec["objects"]:
        region_id = item["id"].removeprefix("scene-object-")
        item["regionId"] = region_id
        x, y, z = hotspot_by_id[region_id]["position"]
        item["position"] = {"x": x, "y": y, "z": z}

    return OracleReplayFixture.model_validate(payload)


def build_model_input(case: OracleReplayCase) -> Mapping[str, Any]:
    """Return only the formal request; expected output never crosses this boundary."""

    payload = case.request.model_dump(mode="json", by_alias=True)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if any(key in serialized for key in FORBIDDEN_MODEL_INPUT_KEYS):
        raise AssertionError("oracle answer data crossed the model-input boundary")
    return MappingProxyType(payload)


def canonical_sha256(value: Mapping[str, Any]) -> str:
    """Return a repeatable SHA-256 for a JSON mapping."""

    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

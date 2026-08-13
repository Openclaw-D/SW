from __future__ import annotations

import json
import sys
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parent
BACK_DIR = RUN_DIR.parents[2]
sys.path.insert(0, str(BACK_DIR))

from app.contracts.material_intelligence import (  # noqa: E402
    MaterialIntelligenceRequest,
    MaterialIntelligenceResult,
    validate_material_intelligence_result,
)
from app.contracts.model_gateway import ModelGatewayRequest  # noqa: E402


def load_json(name: str) -> dict:
    with (RUN_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main() -> None:
    request_doc = load_json("blind_request.json")
    output_doc = load_json("blind_output.json")
    metrics = load_json("run_metrics.json")

    assert request_doc["generatedBy"] == "codex_isolated_blind_eval_v2"
    assert output_doc["generatedBy"] == "codex_isolated_blind_eval_v2"
    assert metrics["generatedBy"] == "codex_isolated_blind_eval_v2"
    assert request_doc["notAProviderCall"] is True
    assert output_doc["notAProviderCall"] is True
    assert metrics["notAProviderCall"] is True
    assert output_doc["FactVersionWrites"] == metrics["FactVersionWrites"] == 0
    assert metrics["isSimulated"] is True and metrics["advisoryOnly"] is True

    requests = {
        item["requestId"]: ModelGatewayRequest.model_validate(item)
        for item in request_doc["requests"]
    }
    assert len(requests) == 3
    assert {item["caseId"] for item in output_doc["outputs"]} == {"image", "pdf", "excel"}

    for case in output_doc["outputs"]:
        raw_output = case["output"]
        request = requests[raw_output["requestId"]]
        assert raw_output["materialId"] == request.material.material_id
        assert raw_output["materialVersionId"] == request.material.material_version_id
        assert raw_output["inputHash"] == request.input_hash
        parsed_result = MaterialIntelligenceResult.model_validate(raw_output["result"])
        result_request = MaterialIntelligenceRequest(
            projectId=request.material.project_id,
            materialId=request.material.material_id,
            materialVersionId=request.material.material_version_id,
            contentHash=request.material.content_hash,
            mediaKind=request.material.media_kind,
            contextVersion=request.context_version,
            taskGoals=request.task_goals,
            locale=request.project_context.locale,
            dataClassification=request.material.data_classification,
            usageAuthorizationRef=request.material.usage_authorization_ref,
        )
        validate_material_intelligence_result(
            result_request,
            parsed_result,
            expected_input_hash=request.input_hash,
        )
        assert parsed_result.status.value == "needs_review"
        assert parsed_result.unresolved_items
        assert all(item.requires_human_review for item in parsed_result.unresolved_items)
        assert all(item.source_anchor_ids for item in parsed_result.unresolved_items)

    image = next(item for item in output_doc["outputs"] if item["caseId"] == "image")["output"]
    assert image["result"]["sourceAnchors"][0]["bbox"] == {"x": 0.18, "y": 0.2, "width": 0.64, "height": 0.58}
    assert image["result"]["extractedFieldCandidates"][0]["value"] == "机床类设备"
    assert image["result"]["sceneSpec"] is not None

    pdf = next(item for item in output_doc["outputs"] if item["caseId"] == "pdf")["output"]
    assert all(anchor["page"] == 1 for anchor in pdf["result"]["sourceAnchors"])
    excel = next(item for item in output_doc["outputs"] if item["caseId"] == "excel")["output"]
    assert all(anchor["sheet"] == "生产记录" for anchor in excel["result"]["sourceAnchors"])
    assert {anchor["range"] for anchor in excel["result"]["sourceAnchors"]} >= {"A78", "B78", "C78", "D78", "E78", "F78", "G78"}

    forbidden_keys = {"scoreGrade", "decisionGrade", "confidenceOverride", "hardGate", "approval", "FactVersion"}
    for node in walk(output_doc):
        assert forbidden_keys.isdisjoint(node.keys())

    telemetry = metrics["cases"]
    assert {item["caseId"] for item in telemetry} == {"image", "pdf", "excel"}
    retryable = {"rate_limited", "timeout", "provider_unavailable"}
    for item in telemetry:
        assert item["attemptCount"] in {1, 2}
        assert item["retryCount"] in {0, 1}
        assert item["retryCount"] == len(item["retryErrorCodes"])
        assert set(item["retryErrorCodes"]).issubset(retryable)
        assert item["finishedAt"] >= item["startedAt"]
        assert item["elapsedMs"] >= 0
        assert item["terminalStatus"] in {"succeeded", "needs_review", "failed", "unavailable"}
    assert metrics["totalElapsedMs"] >= metrics["absoluteCeilingMs"]
    assert metrics["terminalStatus"] == "failed"
    assert metrics["stopReason"] == "absolute_time_ceiling_exceeded_during_artifact_assembly"

    expected_files = {
        "README.md",
        "blind_request.json",
        "blind_output.json",
        "run_metrics.json",
        "validate_blind_run.py",
    }
    actual_files = {path.name for path in RUN_DIR.iterdir() if path.is_file()}
    assert actual_files == expected_files, (actual_files, expected_files)
    print("blind_run_v2 validation completed: schemas and local invariants accepted")


if __name__ == "__main__":
    main()

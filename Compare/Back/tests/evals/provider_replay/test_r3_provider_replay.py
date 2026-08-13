from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path

from evals.model_gateway.provider_replay import (
    R3_REPLAY_MANIFEST,
    build_r3_formal_request,
    render_r3_replay_markdown,
    run_r3_provider_replay,
)


BACK_ROOT = Path(__file__).resolve().parents[3]
RAW_RESULTS_PATH = (
    BACK_ROOT
    / "evals"
    / "model_gateway"
    / "blind_run_v3"
    / "raw_provider_results.json"
)
RUN_METRICS_PATH = (
    BACK_ROOT / "evals" / "model_gateway" / "blind_run_v3" / "run_metrics.json"
)
REPORT_JSON_PATH = (
    BACK_ROOT
    / "evals"
    / "model_gateway"
    / "provider_replay"
    / "R3-PROVIDER-REPLAY-REPORT.json"
)
REPORT_MARKDOWN_PATH = REPORT_JSON_PATH.with_suffix(".md")


def _explicit_r3_inputs() -> tuple[list[dict], dict]:
    return (
        json.loads(RAW_RESULTS_PATH.read_text(encoding="utf-8")),
        json.loads(RUN_METRICS_PATH.read_text(encoding="utf-8")),
    )


def test_r3_manifest_builds_backend_canonical_hash_without_raw_result() -> None:
    raw_results, _run_metrics = _explicit_r3_inputs()
    raw_by_material = {item["materialId"]: item for item in raw_results}
    hashes = []
    for case in R3_REPLAY_MANIFEST:
        request = build_r3_formal_request(case)
        hashes.append(request.input_hash)
        assert "inputHash" not in raw_by_material[case.material_id]
        assert request.input_hash != request.material.content_hash
        assert request.material.content_hash == case.content_hash
    assert len(set(hashes)) == 3


def test_r3_provider_replay_three_cases_pass_and_reports_are_frozen(tmp_path) -> None:
    raw_results, run_metrics = _explicit_r3_inputs()
    report = asyncio.run(
        run_r3_provider_replay(
            raw_results=raw_results,
            run_metrics=run_metrics,
            database_directory=tmp_path / "r3-provider-replay",
        )
    )

    assert report["status"] == "PASS"
    assert report["transport"] == {
        "kind": "mock-direct-provider-seam",
        "gatewayMode": "real",
        "externalNetworkCalls": 0,
        "isRealExternalProviderCall": False,
    }
    assert report["sourceResult"] == {
        "generatedBy": "codex_isolated_blind_eval_v3",
        "source": "codex_offline_oracle",
        "isSimulated": True,
        "advisoryOnly": True,
        "notAProviderCall": True,
    }
    assert report["adaptedGatewayTruth"]["meaning"].endswith(
        "not evidence of an external provider API call"
    )
    assert report["summary"] == {
        "caseCount": 3,
        "passed": 3,
        "failed": 0,
        "externalNetworkCalls": 0,
        "firstExecutionProviderCalls": 3,
        "replayProviderCalls": 0,
        "factVersionWrites": 0,
    }
    expected_counts = {
        "image-equipment-overview": 2,
        "pdf-purchase-contract": 6,
        "excel-operations": 7,
    }
    for item in report["cases"]:
        assert item["status"] == "PASS"
        assert item["failureReasons"] == []
        assert item["rawInputHashPresent"] is False
        assert item["rawBindingValidated"] is True
        assert item["semanticDigestMatch"] is True
        assert item["sourceAnchorCount"] == expected_counts[item["caseId"]]
        assert item["locatorBindingCount"] == expected_counts[item["caseId"]]
        assert item["firstExecutionProviderCalls"] == 1
        assert item["replayProviderCalls"] == 0
        assert item["idempotentReplay"] is True
        assert item["recordRedacted"] is True
        assert item["factVersionWrites"] == 0

    assert report == json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8"))
    assert render_r3_replay_markdown(report) == REPORT_MARKDOWN_PATH.read_text(
        encoding="utf-8"
    )


def test_r3_invalid_raw_anchor_fails_closed_without_semantic_repair(tmp_path) -> None:
    raw_results, run_metrics = _explicit_r3_inputs()
    invalid = deepcopy(raw_results)
    invalid[0]["sourceAnchors"][0]["materialVersionId"] = "invented-version-v2"

    report = asyncio.run(
        run_r3_provider_replay(
            raw_results=invalid,
            run_metrics=run_metrics,
            database_directory=tmp_path / "r3-invalid-anchor",
        )
    )

    image = report["cases"][0]
    assert report["status"] == "FAIL"
    assert image["status"] == "FAIL"
    assert image["rawBindingValidated"] is False
    assert image["failureReasons"] == ["raw_result_schema_or_binding_invalid"]
    assert image["firstExecutionProviderCalls"] is None
    assert image["factVersionWrites"] is None

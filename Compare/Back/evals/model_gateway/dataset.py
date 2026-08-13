"""Load physically separated public inputs and hidden golden truth.

Only :class:`PublicEvalCase` is allowed to cross the fake-provider boundary.
The runner deliberately loads golden truth after all provider calls complete.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


DATA_DIR = Path(__file__).with_name("data")
PUBLIC_DATASET_PATH = DATA_DIR / "public_cases.json"
HIDDEN_TRUTH_PATH = DATA_DIR / "hidden" / "golden_truth.json"


@dataclass(frozen=True, slots=True)
class PublicEvalCase:
    case_id: str
    industry: str
    smoke: bool
    provider_input: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class HiddenGoldenTruth:
    case_id: str
    expected_fields: Mapping[str, Any]


def load_public_cases(path: Path = PUBLIC_DATASET_PATH) -> tuple[PublicEvalCase, ...]:
    payload = _read_json(path)
    _validate_dataset_header(payload, path)
    template = payload["materialTemplate"]
    cases: list[PublicEvalCase] = []
    seen_ids: set[str] = set()
    for item in payload["cases"]:
        case_id = _required_text(item, "caseId")
        if case_id in seen_ids:
            raise ValueError(f"duplicate public caseId: {case_id}")
        seen_ids.add(case_id)
        source_values = dict(item["sourceValues"])
        regions = []
        for region in template["regions"]:
            field_key = _required_text(region, "fieldKey")
            if field_key not in source_values:
                raise ValueError(f"{case_id} missing source value for {field_key}")
            regions.append(
                {
                    **region,
                    "value": source_values[field_key],
                    "anchorId": f"anchor-{case_id}-{field_key}",
                }
            )
        content_hash = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
        provider_input = {
            "caseId": case_id,
            "projectId": _required_text(item, "projectId"),
            "industry": _required_text(item, "industry"),
            "materialId": f"material-{case_id}",
            "materialVersionId": f"material-{case_id}-v1",
            "contentHash": content_hash,
            "mediaKind": template["mediaKind"],
            "contextVersion": "eval-context-v1",
            "taskGoals": list(template["taskGoals"]),
            "locale": "zh-CN",
            "dataClassification": "synthetic_demo",
            "isSimulated": True,
            "dataStatus": "synthetic_demo",
            "source": "deterministic_offline_eval_fixture",
            "disclaimer": payload["disclaimer"],
            "regions": regions,
        }
        cases.append(
            PublicEvalCase(
                case_id=case_id,
                industry=provider_input["industry"],
                smoke=bool(item["smoke"]),
                provider_input=MappingProxyType(provider_input),
            )
        )
    if len(cases) != 24:
        raise ValueError(f"public dataset must contain 24 cases, got {len(cases)}")
    smoke_industries = {case.industry for case in cases if case.smoke}
    if len([case for case in cases if case.smoke]) != 6 or len(smoke_industries) != 6:
        raise ValueError("public dataset must mark one smoke case for each of six industries")
    return tuple(cases)


def load_hidden_truth(
    path: Path = HIDDEN_TRUTH_PATH,
) -> Mapping[str, HiddenGoldenTruth]:
    payload = _read_json(path)
    _validate_dataset_header(payload, path)
    truths: dict[str, HiddenGoldenTruth] = {}
    for item in payload["cases"]:
        case_id = _required_text(item, "caseId")
        if case_id in truths:
            raise ValueError(f"duplicate hidden caseId: {case_id}")
        truths[case_id] = HiddenGoldenTruth(
            case_id=case_id,
            expected_fields=MappingProxyType(dict(item["expectedFields"])),
        )
    if len(truths) != 24:
        raise ValueError(f"hidden truth must contain 24 cases, got {len(truths)}")
    return MappingProxyType(truths)


def assert_dataset_alignment(
    public_cases: tuple[PublicEvalCase, ...],
    truths: Mapping[str, HiddenGoldenTruth],
) -> None:
    public_ids = {case.case_id for case in public_cases}
    truth_ids = set(truths)
    if public_ids != truth_ids:
        missing_truth = sorted(public_ids - truth_ids)
        missing_public = sorted(truth_ids - public_ids)
        raise ValueError(
            "public/hidden case alignment failed: "
            f"missingTruth={missing_truth}, missingPublic={missing_public}"
        )


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError(f"dataset must be a JSON object: {path}")
    return payload


def _validate_dataset_header(payload: Mapping[str, Any], path: Path) -> None:
    if payload.get("datasetVersion") != "1.0":
        raise ValueError(f"unsupported datasetVersion in {path}")
    if payload.get("isSimulated") is not True:
        raise ValueError(f"dataset must be explicitly simulated: {path}")
    if payload.get("dataStatus") != "synthetic_demo":
        raise ValueError(f"dataset dataStatus must be synthetic_demo: {path}")
    for field in ("source", "disclaimer"):
        _required_text(payload, field)


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field} must be non-blank trimmed text")
    return value

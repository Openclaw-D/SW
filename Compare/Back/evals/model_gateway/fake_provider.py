"""Deterministic fake provider for offline evaluation only."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


class OfflineSyntheticFakeProvider:
    """Convert explicit synthetic regions into candidate-only contract output."""

    identity = "compare-eval-fake"
    advisory_only = True
    is_real_provider = False

    def __init__(self) -> None:
        self.calls = 0
        self.received_inputs: list[Mapping[str, Any]] = []

    async def predict(self, provider_input: Mapping[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.received_inputs.append(provider_input)
        regions = list(provider_input["regions"])
        anchors = [
            {
                "id": region["anchorId"],
                "kind": "image",
                "materialId": provider_input["materialId"],
                "materialVersionId": provider_input["materialVersionId"],
                "contentHash": provider_input["contentHash"],
                "page": 1,
                "bbox": region["bbox"],
                "ocrTokenIds": [f"ocr-{region['fieldKey']}"],
                "charStart": 0,
                "charEnd": max(1, len(str(region["value"]))),
            }
            for region in regions
        ]
        candidates = [
            {
                "id": f"candidate-{provider_input['caseId']}-{region['fieldKey']}",
                "fieldKey": region["fieldKey"],
                "label": region["label"],
                "value": region["value"],
                "unit": region["unit"],
                "status": "candidate",
                "sourceAnchorIds": [region["anchorId"]],
            }
            for region in regions
        ]
        first_region = regions[0]
        return {
            "projectId": provider_input["projectId"],
            "materialId": provider_input["materialId"],
            "materialVersionId": provider_input["materialVersionId"],
            "contentHash": provider_input["contentHash"],
            "mediaKind": provider_input["mediaKind"],
            "contextVersion": provider_input["contextVersion"],
            "dataClassification": provider_input["dataClassification"],
            "status": "completed",
            "confidence": 0.99,
            "observations": [
                {
                    "id": f"observation-{provider_input['caseId']}",
                    "kind": "structure",
                    "text": "脱敏合成图像包含三个明确标注的评测字段。",
                    "sourceAnchorIds": [item["id"] for item in anchors],
                }
            ],
            "extractedFieldCandidates": candidates,
            "unresolvedItems": [],
            "sourceAnchors": anchors,
            "sceneSpec": {
                "cameraPreset": "front",
                "objects": [
                    {
                        "id": f"object-{provider_input['caseId']}",
                        "kind": "plane",
                        "regionId": "synthetic-review-region",
                        "position": {"x": 0, "y": 0, "z": 0},
                        "size": {"x": 4, "y": 2, "z": 0.1},
                        "rotation": {"x": 0, "y": 0, "z": 0},
                    }
                ],
                "hotspots": [
                    {
                        "id": f"hotspot-{provider_input['caseId']}",
                        "objectId": f"object-{provider_input['caseId']}",
                        "regionId": "synthetic-review-region",
                        "sourceAnchorId": first_region["anchorId"],
                    }
                ],
            },
            "modelInfo": {
                "provider": self.identity,
                "model": "deterministic-no-inference",
                "modelVersion": "eval-v1",
            },
            "promptVersion": "offline-synthetic-v1",
            "schemaVersion": "1.0",
            "inputHash": calculate_public_input_hash(provider_input),
            "isSimulated": True,
        }


def calculate_public_input_hash(provider_input: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(provider_input),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

from __future__ import annotations

import json
from pathlib import Path

from app.contracts.model_gateway import ModelGatewayOutput, ModelGatewayRequest


ROOT = Path(__file__).resolve().parent
FORBIDDEN_KEYS = {
    "scoreGrade",
    "decisionGrade",
    "confidenceOverride",
    "hardGate",
    "hardGates",
    "approval",
    "factVersion",
    "factVersionWrites",
    "reviewTransition",
}


def walk_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys.update(walk_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(walk_keys(child))
        return keys
    return set()


request_document = json.loads((ROOT / "blind_request.json").read_text(encoding="utf-8"))
output_document = json.loads((ROOT / "blind_output.json").read_text(encoding="utf-8"))

requests = {
    item["requestId"]: ModelGatewayRequest.model_validate(item)
    for item in request_document["requests"]
}
outputs = [ModelGatewayOutput.model_validate(item) for item in output_document["modelGatewayOutputs"]]

assert len(requests) == 3
assert len(outputs) == 3
assert {item.request_id for item in outputs} == set(requests)
for output in outputs:
    request = requests[output.request_id]
    assert output.material_id == request.material.material_id
    assert output.material_version_id == request.material.material_version_id
    assert output.input_hash == request.input_hash

forbidden_found = FORBIDDEN_KEYS.intersection(walk_keys(output_document))
assert not forbidden_found, f"forbidden output keys: {sorted(forbidden_found)}"

print("blind_request: 3/3 ModelGatewayRequest parsed")
print("blind_output: 3/3 ModelGatewayOutput parsed")
print("bindings: request/material/version/inputHash passed")
print("forbidden authoritative keys: none")

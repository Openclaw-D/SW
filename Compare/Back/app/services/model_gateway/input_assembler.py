from __future__ import annotations

import json
import re

from app.contracts.errors import BusinessValidationError
from app.contracts.material_intelligence import DataClassification
from app.contracts.model_gateway import (
    ModelGatewayCapability,
    ModelGatewayMode,
    ModelGatewayRequest,
)
from app.ports.model_gateway import AssembledGatewayInput


_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def assemble_input(
    request: ModelGatewayRequest,
    capability: ModelGatewayCapability,
    *,
    max_input_tokens: int,
) -> AssembledGatewayInput:
    """Assemble the provider input from the public metadata-only request.

    The frozen request deliberately contains no expected answer, ground truth,
    original bytes or extracted text. P5-MG-Router additionally rejects real
    mode, non-synthetic classifications and absolute source paths.
    """

    if request.mode != ModelGatewayMode.SYNTHETIC:
        raise BusinessValidationError(
            "real_provider_not_enabled",
            "P5-MG-Router 仅允许 synthetic 模式。",
            field="mode",
        )
    if request.material.data_classification != DataClassification.SYNTHETIC_DEMO:
        raise BusinessValidationError(
            "authorization_required",
            "本阶段只接受明确标记的脱敏合成演示材料。",
            field="material.dataClassification",
        )
    if request.material.media_kind not in capability.input_kinds:
        raise BusinessValidationError(
            "content_unsupported",
            "该 capability 不支持当前材料类型。",
            field="material.mediaKind",
        )
    source_ref = request.material.source_ref
    if (
        _WINDOWS_ABSOLUTE_PATH.match(source_ref)
        or source_ref.startswith(("/home/", "/Users/", "/tmp/"))
        or ".." in source_ref.replace("\\", "/").split("/")
    ):
        raise BusinessValidationError(
            "request_invalid",
            "sourceRef 必须是脱敏逻辑引用，不能包含绝对路径或目录穿越。",
            field="material.sourceRef",
        )
    payload = request.model_dump(mode="json", by_alias=True)
    # inputHash binds externally prepared material bytes; it is carried but is
    # never replaced by an answer-bearing evaluation label.
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    estimated_tokens = max(1, (len(encoded) + 3) // 4)
    if estimated_tokens > max_input_tokens:
        raise BusinessValidationError(
            "model_budget_exceeded",
            "组装后的输入超过 capability 预算。",
            details={
                "estimatedInputTokens": estimated_tokens,
                "maxInputTokens": max_input_tokens,
            },
        )
    return AssembledGatewayInput(
        payload=payload,
        input_hash=request.input_hash,
        estimated_input_tokens=estimated_tokens,
    )


def request_fingerprint(request: ModelGatewayRequest) -> str:
    import hashlib

    encoded = json.dumps(
        request.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

from __future__ import annotations

from pydantic import ValidationError

from app.contracts.errors import ServiceError
from app.contracts.model_gateway import (
    ModelGatewayMode,
    ModelGatewayOutput,
    ModelGatewayRequest,
)


def validate_output(
    raw_output: object,
    *,
    request: ModelGatewayRequest,
    provider_id: str,
) -> ModelGatewayOutput:
    try:
        output = ModelGatewayOutput.model_validate(raw_output)
        if output.request_id != request.request_id:
            raise ValueError("requestId mismatch")
        if output.capability_id != request.capability_id:
            raise ValueError("capabilityId mismatch")
        if output.mode != ModelGatewayMode.SYNTHETIC or output.mode != request.mode:
            raise ValueError("mode mismatch")
        if output.material_id != request.material.material_id:
            raise ValueError("materialId mismatch")
        if output.material_version_id != request.material.material_version_id:
            raise ValueError("materialVersionId mismatch")
        if output.input_hash != request.input_hash:
            raise ValueError("inputHash mismatch")
        if output.source != provider_id or output.is_simulated is not True:
            raise ValueError("provider truth metadata mismatch")
        if output.result is not None:
            if output.result.project_id != request.material.project_id:
                raise ValueError("result projectId mismatch")
            if output.result.context_version != request.context_version:
                raise ValueError("result contextVersion mismatch")
            if output.result.data_classification != request.material.data_classification:
                raise ValueError("result dataClassification mismatch")
            allowed_fields = {item.field_key for item in request.field_schemas}
            if any(
                candidate.field_key not in allowed_fields
                for candidate in output.result.extracted_field_candidates
            ):
                raise ValueError("candidate fieldKey was not requested")
        return output
    except (ValidationError, ValueError, TypeError) as exc:
        raise ServiceError(
            code="invalid_output",
            message="Model Gateway provider 返回了不符合严格契约的结果。",
            category="internal",
            status_code=502,
        ) from exc

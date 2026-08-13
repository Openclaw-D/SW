from __future__ import annotations

from fastapi import Request

from app.contracts.envelope import ApiEnvelope, ResponseMeta
from app.core.config import Settings


def response_meta(request: Request) -> ResponseMeta:
    settings: Settings = request.app.state.settings
    return ResponseMeta(
        request_id=request.state.request_id,
        schema_version=settings.schema_version,
        data_status="simulated",
        source=settings.source,
        disclaimer=settings.disclaimer,
    )


def success(request: Request, data: object) -> dict[str, object]:
    return ApiEnvelope[object](
        data=data,
        meta=response_meta(request),
        errors=[],
    ).model_dump(mode="json", by_alias=True)

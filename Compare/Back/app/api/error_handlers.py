from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.responses import response_meta
from app.contracts.envelope import ApiEnvelope, ApiError
from app.contracts.errors import ServiceError


def _error_response(
    request: Request,
    *,
    status_code: int,
    error: ApiError,
) -> JSONResponse:
    envelope = ApiEnvelope[object](
        data=None,
        meta=response_meta(request),
        errors=[error],
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(envelope.model_dump(mode="json", by_alias=True)),
    )


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        error=ApiError(
            code=exc.code,
            category=exc.category,
            message=exc.message,
            field=exc.field,
            details=exc.details,
        ),
    )


async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    compact_errors: list[dict[str, object]] = []
    for item in exc.errors():
        compact_errors.append(
            {
                "field": ".".join(str(part) for part in item.get("loc", ())),
                "type": str(item.get("type", "validation_error")),
                "message": str(item.get("msg", "请求字段无效")),
            }
        )
    first_field = compact_errors[0]["field"] if compact_errors else None
    missing_idempotency_key = any(
        tuple(item.get("loc", ())) == ("header", "Idempotency-Key")
        and item.get("type") == "missing"
        for item in exc.errors()
    )
    return _error_response(
        request,
        status_code=422,
        error=ApiError(
            code=("idempotency_key_required" if missing_idempotency_key else "validation_error"),
            category="validation",
            message=(
                "写操作必须提供 Idempotency-Key。"
                if missing_idempotency_key
                else "请求字段校验失败。"
            ),
            field=(
                "Idempotency-Key"
                if missing_idempotency_key
                else (str(first_field) if first_field else None)
            ),
            details={"errors": compact_errors},
        ),
    )


async def http_error_handler(
    request: Request, exc: StarletteHTTPException | HTTPException
) -> JSONResponse:
    if exc.status_code == 404:
        code, category, message = "route_not_found", "not_found", "请求路径不存在。"
    elif exc.status_code == 405:
        code, category, message = "method_not_allowed", "validation", "请求方法不允许。"
    else:
        code = "http_error"
        category = "validation" if exc.status_code < 500 else "internal"
        message = str(exc.detail)
    return _error_response(
        request,
        status_code=exc.status_code,
        error=ApiError(code=code, category=category, message=message),
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Do not expose stack traces, credentials, headers or runtime paths.
    return _error_response(
        request,
        status_code=500,
        error=ApiError(
            code="internal_error",
            category="internal",
            message="服务处理失败，请携带 requestId 排查。",
        ),
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, service_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unexpected_error_handler)

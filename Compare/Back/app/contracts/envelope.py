from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import Field

from app.contracts.base import ContractModel


T = TypeVar("T")
ErrorCategory = Literal["not_found", "validation", "forbidden", "conflict", "internal"]


class ApiError(ContractModel):
    code: str = Field(min_length=1, max_length=96)
    category: ErrorCategory
    message: str = Field(min_length=1, max_length=1000)
    field: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class ResponseMeta(ContractModel):
    request_id: str = Field(min_length=1, max_length=128)
    schema_version: str = "1.0"
    data_status: Literal["simulated"] = "simulated"
    source: str = "deterministic_business_rules"
    disclaimer: str


class ApiEnvelope(ContractModel, Generic[T]):
    data: T | None
    meta: ResponseMeta
    errors: list[ApiError] = Field(default_factory=list)


class ErrorEnvelope(ContractModel):
    data: None = None
    meta: ResponseMeta
    errors: list[ApiError] = Field(min_length=1)

from __future__ import annotations

from typing import Any, Literal


ErrorCategory = Literal["not_found", "validation", "forbidden", "conflict", "internal"]


class ServiceError(Exception):
    """Stable service-to-HTTP error boundary shared with Back-2."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        category: ErrorCategory,
        status_code: int,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.category = category
        self.status_code = status_code
        self.field = field
        self.details = details or {}


class NotFoundError(ServiceError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=code,
            message=message,
            category="not_found",
            status_code=404,
            details=details,
        )


class ConflictError(ServiceError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=code,
            message=message,
            category="conflict",
            status_code=409,
            details=details,
        )


class BusinessValidationError(ServiceError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            category="validation",
            status_code=422,
            field=field,
            details=details,
        )


class ForbiddenError(ServiceError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            category="forbidden",
            status_code=403,
            details=details,
        )


class VersionConflictError(ConflictError):
    def __init__(self, *, expected_version: int, actual_version: int) -> None:
        super().__init__(
            "version_conflict",
            "expectedVersion 与服务端当前版本不一致，请刷新后重试。",
            details={
                "expectedVersion": expected_version,
                "actualVersion": actual_version,
            },
        )


class IdempotencyConflictError(ConflictError):
    def __init__(self) -> None:
        super().__init__(
            "idempotency_key_reused",
            "同一 Idempotency-Key 已用于不同请求载荷。",
        )


class HardGateBlockedError(ConflictError):
    def __init__(self, blocking_rule_ids: list[str]) -> None:
        super().__init__(
            "hard_gate_blocked",
            "仍有 hard gate 阻断或人工复核项，任何角色均不能完成审批。",
            details={"blockingRuleIds": blocking_rule_ids},
        )

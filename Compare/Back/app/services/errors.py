from __future__ import annotations

from typing import Any

from app.contracts.errors import (
    BusinessValidationError,
    ConflictError,
    HardGateBlockedError,
    IdempotencyConflictError,
    NotFoundError,
    ServiceError,
    VersionConflictError,
)


class ProjectIsolationError(NotFoundError):
    def __init__(self, entity: str, entity_id: str) -> None:
        super().__init__(
            "project_mismatch",
            "请求对象不存在于当前项目。",
            details={"entity": entity, "entityId": entity_id},
        )


class InvalidLocatorError(BusinessValidationError):
    def __init__(self, message: str, *, evidence_id: str | None = None) -> None:
        details: dict[str, Any] = {}
        if evidence_id is not None:
            details["evidenceRef"] = evidence_id
        super().__init__(
            "invalid_locator",
            message,
            field="locator",
            details=details,
        )


class VersionMismatchError(ConflictError):
    def __init__(
        self,
        *,
        material_id: str,
        requested_version_id: str,
        current_version_id: str | None,
    ) -> None:
        super().__init__(
            "version_mismatch",
            "证据定位引用的材料版本与当前材料版本不一致。",
            details={
                "materialId": material_id,
                "materialVersionId": requested_version_id,
                "currentMaterialVersionId": current_version_id,
            },
        )


class EvidenceSelectionError(BusinessValidationError):
    def __init__(
        self,
        *,
        status: str,
        failed_target: dict[str, Any],
        message: str,
    ) -> None:
        super().__init__(
            "evidence_selection_failed",
            message,
            field="selectionGroup",
            details={"status": status, "failedTarget": failed_target},
        )


__all__ = [
    "BusinessValidationError",
    "ConflictError",
    "EvidenceSelectionError",
    "HardGateBlockedError",
    "IdempotencyConflictError",
    "InvalidLocatorError",
    "NotFoundError",
    "ProjectIsolationError",
    "ServiceError",
    "VersionConflictError",
    "VersionMismatchError",
]

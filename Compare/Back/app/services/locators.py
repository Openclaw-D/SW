from __future__ import annotations

import re
import sqlite3
from dataclasses import replace
from typing import Any

from app.models import (
    DocumentLocator,
    EvidenceReference,
    EvidenceResolution,
    ExcelLocator,
    ImageLocator,
    Material,
    MaterialVersion,
    MediaLocator,
    NormalizedBBox,
    PdfLocator,
    SceneLocator,
)
from app.repositories import SQLiteStateRepository

from .errors import InvalidLocatorError


_CELL_RANGE = re.compile(
    r"^\s*([A-Za-z]+)([1-9]\d*):([A-Za-z]+)([1-9]\d*)\s*$"
)


def _column_number(label: str) -> int:
    value = 0
    for character in label.upper():
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def parse_excel_range(value: str) -> tuple[int, int, int, int] | None:
    match = _CELL_RANGE.fullmatch(value)
    if match is None:
        return None
    start_column = _column_number(match.group(1))
    start_row = int(match.group(2))
    end_column = _column_number(match.group(3))
    end_row = int(match.group(4))
    return (
        min(start_column, end_column),
        max(start_column, end_column),
        min(start_row, end_row),
        max(start_row, end_row),
    )


def _valid_bbox(bbox: NormalizedBBox) -> bool:
    values = (bbox.x, bbox.y, bbox.width, bbox.height)
    return (
        all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values)
        and bbox.x >= 0
        and bbox.y >= 0
        and bbox.width > 0
        and bbox.height > 0
        and bbox.x + bbox.width <= 1
        and bbox.y + bbox.height <= 1
    )


class LocatorService:
    def __init__(self, repository: SQLiteStateRepository) -> None:
        self.repository = repository

    def validate_reference(
        self,
        project_id: str,
        evidence: EvidenceReference,
        connection: sqlite3.Connection,
        *,
        require_current_version: bool = False,
    ) -> tuple[Material | None, MaterialVersion | None]:
        locator = evidence.locator
        if locator is None:
            if evidence.location_status not in {"pending", "unverifiable"}:
                raise InvalidLocatorError(
                    "无 locator 的证据只能标记为 pending 或 unverifiable。",
                    evidence_id=evidence.id,
                )
            return None, None

        material = self.repository.get_material(project_id, locator.material_id, connection)
        version = self.repository.get_material_version(
            project_id, locator.material_version_id, connection
        )
        if version.material_id != material.id:
            raise InvalidLocatorError(
                "materialVersionId 与 locator.materialId 不属于同一材料。",
                evidence_id=evidence.id,
            )
        if evidence.location_status == "located" and material.availability != "available":
            raise InvalidLocatorError(
                "不可用材料不能产生 located 证据。", evidence_id=evidence.id
            )
        if require_current_version and material.current_version_id != version.id:
            raise InvalidLocatorError(
                "locator 引用的不是材料当前版本。", evidence_id=evidence.id
            )
        self._validate_bounds(evidence, material, version)
        return material, version

    def _validate_bounds(
        self,
        evidence: EvidenceReference,
        material: Material,
        version: MaterialVersion,
    ) -> None:
        locator = evidence.locator
        if locator is None:
            return
        payload = version.payload
        payload_kind = payload.get("kind", material.kind)
        if material.kind != locator.kind or payload_kind != locator.kind:
            raise InvalidLocatorError(
                "locator kind 与材料类型不一致。", evidence_id=evidence.id
            )
        if isinstance(locator, ExcelLocator):
            sheets = payload.get("sheets")
            if not isinstance(sheets, list):
                raise InvalidLocatorError("Excel 材料缺少 sheets。", evidence_id=evidence.id)
            sheet = next(
                (
                    item
                    for item in sheets
                    if isinstance(item, dict) and item.get("name") == locator.sheet
                ),
                None,
            )
            bounds = parse_excel_range(locator.range)
            if sheet is None or bounds is None:
                raise InvalidLocatorError(
                    "Excel sheet 或 range 无效。", evidence_id=evidence.id
                )
            start_column, end_column, start_row, end_row = bounds
            columns = sheet.get("columns")
            rows = sheet.get("rows")
            if not isinstance(columns, list) or not isinstance(rows, list):
                raise InvalidLocatorError(
                    "Excel sheet 缺少 columns/rows。", evidence_id=evidence.id
                )
            # Front 的前三行是模拟工作簿标题区，业务表从第 4 行开始。
            if start_row < 4 or end_row > len(rows) + 3 or end_column > len(columns):
                raise InvalidLocatorError(
                    "Excel range 超出当前工作表边界。", evidence_id=evidence.id
                )
            selected_rows = rows[start_row - 4 : end_row - 3]
            if any(not isinstance(row, list) or len(row) < end_column for row in selected_rows):
                raise InvalidLocatorError(
                    "Excel range 指向不完整行。", evidence_id=evidence.id
                )
            return
        if isinstance(locator, PdfLocator):
            page_count = payload.get("pageCount", payload.get("page_count"))
            pages = payload.get("pages")
            page_ids = {
                item.get("page")
                for item in pages or []
                if isinstance(item, dict)
            }
            if (
                isinstance(page_count, bool)
                or not isinstance(page_count, int)
                or locator.page < 1
                or locator.page > page_count
                or locator.page not in page_ids
                or not _valid_bbox(locator.bbox)
            ):
                raise InvalidLocatorError(
                    "PDF page/bbox 超出当前材料边界。", evidence_id=evidence.id
                )
            return
        if isinstance(locator, ImageLocator):
            if not _valid_bbox(locator.bbox):
                raise InvalidLocatorError(
                    "图片 bbox 超出归一化边界。", evidence_id=evidence.id
                )
            return
        if isinstance(locator, DocumentLocator):
            if (
                not locator.paragraph_id.strip()
                or not locator.run_id.strip()
                or locator.rendered_page < 1
                or not _valid_bbox(locator.rendered_page_bbox)
            ):
                raise InvalidLocatorError(
                    "Word paragraph/run/renderedPageBbox 无效。",
                    evidence_id=evidence.id,
                )
            return
        if isinstance(locator, MediaLocator):
            duration = payload.get("durationSeconds", payload.get("duration_seconds"))
            valid = locator.start_seconds >= 0 and locator.end_seconds >= locator.start_seconds
            if duration is None:
                valid = valid and locator.start_seconds == 0 and locator.end_seconds == 0
            elif isinstance(duration, (int, float)) and not isinstance(duration, bool):
                valid = valid and locator.end_seconds <= float(duration)
            else:
                valid = False
            if not valid:
                raise InvalidLocatorError(
                    "媒体时间范围超出当前材料边界。", evidence_id=evidence.id
                )
            return
        if isinstance(locator, SceneLocator):
            point_ids = locator.point_ids
            points = payload.get("points")
            available = {
                item.get("id") for item in points or [] if isinstance(item, dict)
            }
            if (
                not point_ids
                or len(set(point_ids)) != len(point_ids)
                or any(point_id not in available for point_id in point_ids)
            ):
                raise InvalidLocatorError(
                    "scene pointIds 包含重复或不存在的点。", evidence_id=evidence.id
                )
            return
        raise InvalidLocatorError("不支持的 locator 类型。", evidence_id=evidence.id)

    def resolve(
        self,
        project_id: str,
        evidence_id: str,
        connection: sqlite3.Connection,
    ) -> EvidenceResolution:
        evidence = self.repository.get_evidence_reference(
            project_id, evidence_id, connection
        )
        if evidence.locator is None:
            status = (
                "pending" if evidence.location_status == "pending" else "unverifiable"
            )
            message = "证据尚未完成定位。" if status == "pending" else "证据无法可靠定位。"
            return EvidenceResolution(status, evidence, None, None, message)
        locator = evidence.locator
        material = self.repository.get_material(project_id, locator.material_id, connection)
        version = self.repository.get_material_version(
            project_id, locator.material_version_id, connection
        )
        if version.material_id != material.id:
            raise InvalidLocatorError(
                "materialVersionId 与 locator.materialId 不属于同一材料。",
                evidence_id=evidence.id,
            )
        # The frozen Front resolves a stale material version before attempting
        # to interpret locator bounds.  Preserve that stable conflict signal
        # even when an old payload would no longer be displayable.
        if (
            material.current_version_id != version.id
            or evidence.location_status == "version_mismatch"
        ):
            return EvidenceResolution(
                "version_mismatch",
                evidence,
                material,
                version,
                "证据与当前材料版本不一致。",
            )
        material, version = self.validate_reference(project_id, evidence, connection)
        if material is None or version is None:
            raise AssertionError("located evidence must resolve material and version")
        if evidence.location_status != "located":
            return EvidenceResolution(
                evidence.location_status,
                evidence,
                material,
                version,
                "证据无法可靠定位。",
            )
        return EvidenceResolution("located", evidence, material, version, "证据定位成功。")

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


_CELL_RANGE = re.compile(r"^([A-Za-z]+)([1-9][0-9]*):([A-Za-z]+)([1-9][0-9]*)$")


def _column_index(label: str) -> int:
    value = 0
    for char in label.upper():
        value = value * 26 + ord(char) - ord("A") + 1
    return value


def build_evidence_targets(
    *,
    evidence_refs: Iterable[str],
    dimension_id: str,
    review_target_id: str | None,
    fact_version_id: str | None,
    unavailable_reason: str | None = None,
) -> list[dict[str, Any]]:
    refs = list(dict.fromkeys(evidence_refs))
    if not refs:
        return []
    return [
        {
            "evidenceRef": evidence_ref,
            "evidenceRefs": refs,
            "dimensionId": dimension_id,
            "reviewTargetId": review_target_id,
            "factVersionId": fact_version_id,
            **({"unavailableReason": unavailable_reason} if unavailable_reason else {}),
        }
        for evidence_ref in refs
    ]


def build_selection_group(targets: list[dict[str, Any]]) -> dict[str, Any]:
    if not targets:
        raise ValueError("a selection group requires at least one target")
    first = targets[0]
    refs = [str(target["evidenceRef"]) for target in targets]
    for target in targets:
        if (
            target["dimensionId"] != first["dimensionId"]
            or target.get("reviewTargetId") != first.get("reviewTargetId")
            or target.get("factVersionId") != first.get("factVersionId")
            or target.get("evidenceRefs") != refs
        ):
            raise ValueError("selection targets must be an atomic evidence group")
    group_id = "::".join(
        [
            str(first["dimensionId"]),
            str(first.get("reviewTargetId") or "review"),
            str(first.get("factVersionId") or "fact"),
            *refs,
        ]
    )
    return {
        "id": group_id,
        "dimensionId": first["dimensionId"],
        "reviewTargetId": first.get("reviewTargetId"),
        "factVersionId": first.get("factVersionId"),
        "targets": targets,
    }


def collect_evidence_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "evidenceRef" and isinstance(item, str):
                refs.add(item)
            elif key == "evidenceRefs" and isinstance(item, list):
                refs.update(str(ref) for ref in item)
            else:
                refs.update(collect_evidence_refs(item))
    elif isinstance(value, list | tuple):
        for item in value:
            refs.update(collect_evidence_refs(item))
    return refs


def validate_locators(materials: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
    material_by_id = {item["id"]: item for item in materials}
    for reference in evidence:
        locator = reference.get("locator")
        status = reference["locationStatus"]
        if locator is None:
            if status == "located":
                raise ValueError(f"{reference['id']} is located without a locator")
            continue
        material = material_by_id.get(locator["materialId"])
        if material is None:
            raise ValueError(f"{reference['id']} references an unknown material")
        if locator["kind"] != material["kind"]:
            raise ValueError(f"{reference['id']} locator kind does not match material")
        if status == "located" and locator["materialVersionId"] != material["versionId"]:
            raise ValueError(f"{reference['id']} located version is stale")
        if locator["kind"] == "excel":
            sheet = next((item for item in material["sheets"] if item["name"] == locator["sheet"]), None)
            if sheet is None:
                raise ValueError(f"{reference['id']} references an unknown sheet")
            match = _CELL_RANGE.fullmatch(locator["range"])
            if match is None:
                raise ValueError(f"{reference['id']} has an invalid Excel range")
            first_column = _column_index(match.group(1))
            second_column = _column_index(match.group(3))
            first_row = int(match.group(2))
            second_row = int(match.group(4))
            start_column, end_column = sorted((first_column, second_column))
            start_row, end_row = sorted((first_row, second_row))
            # The frozen Front renderer reserves rows 1-3 and maps business
            # data row 4 to sheets.rows[0].  Keep backend validation identical.
            if start_row < 4 or end_column > len(sheet["columns"]) or end_row > len(sheet["rows"]) + 3:
                raise ValueError(f"{reference['id']} Excel range exceeds material bounds")
            material_rows = sheet["rows"][start_row - 4 : end_row - 3]
            if start_column < 1 or any(len(row) < end_column for row in material_rows):
                raise ValueError(f"{reference['id']} Excel range exceeds material bounds")
        elif locator["kind"] == "pdf":
            if locator["page"] > material["pageCount"]:
                raise ValueError(f"{reference['id']} PDF page exceeds material bounds")
        elif locator["kind"] == "media":
            duration = material.get("durationSeconds")
            if duration is not None and locator["endSeconds"] > duration:
                raise ValueError(f"{reference['id']} media range exceeds duration")
        elif locator["kind"] == "scene":
            point_ids = {point["id"] for point in material["points"]}
            if not set(locator["pointIds"]) <= point_ids:
                raise ValueError(f"{reference['id']} references unknown scene points")


__all__ = [
    "build_evidence_targets",
    "build_selection_group",
    "collect_evidence_refs",
    "validate_locators",
]

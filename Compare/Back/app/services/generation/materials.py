from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MaterialBinding:
    material_id: str
    material_version_id: str


@dataclass
class EvidenceRegistry:
    project_id: str
    excel_material_id: str
    excel_version_id: str
    pdf_material_id: str
    pdf_version_id: str
    image_material_id: str
    image_version_id: str
    items: list[dict[str, Any]] = field(default_factory=list)
    bindings: dict[str, MaterialBinding] = field(default_factory=dict)

    def bind(self, key: str, material_id: str, material_version_id: str) -> None:
        if key in self.bindings:
            raise ValueError(f"duplicate material binding: {key}")
        self.bindings[key] = MaterialBinding(material_id, material_version_id)

    def _binding(
        self,
        kind: str,
        key: str | None,
    ) -> MaterialBinding:
        if key is not None:
            try:
                return self.bindings[key]
            except KeyError as exc:
                raise ValueError(f"unknown material binding: {key}") from exc
        defaults = {
            "excel": MaterialBinding(self.excel_material_id, self.excel_version_id),
            "pdf": MaterialBinding(self.pdf_material_id, self.pdf_version_id),
            "image": MaterialBinding(self.image_material_id, self.image_version_id),
        }
        try:
            return defaults[kind]
        except KeyError as exc:
            raise ValueError(f"{kind} evidence requires an explicit material binding") from exc

    def excel(
        self,
        suffix: str,
        label: str,
        sheet: str,
        cell_range: str,
        *,
        material_status: str = "confirmed",
        material_key: str | None = None,
    ) -> str:
        binding = self._binding("excel", material_key)
        evidence_id = f"ev-{self.project_id}-{suffix}"
        self.items.append(
            {
                "id": evidence_id,
                "label": label,
                "locator": {
                    "kind": "excel",
                    "materialId": binding.material_id,
                    "materialVersionId": binding.material_version_id,
                    "sheet": sheet,
                    "range": cell_range,
                },
                "locationStatus": "located",
                "materialStatus": material_status,
            }
        )
        return evidence_id

    def pdf(
        self,
        suffix: str,
        label: str,
        page: int,
        bbox: dict[str, float],
        *,
        text_anchor: str | None = None,
        material_status: str = "confirmed",
        material_key: str | None = None,
    ) -> str:
        binding = self._binding("pdf", material_key)
        evidence_id = f"ev-{self.project_id}-{suffix}"
        locator: dict[str, Any] = {
            "kind": "pdf",
            "materialId": binding.material_id,
            "materialVersionId": binding.material_version_id,
            "page": page,
            "bbox": bbox,
        }
        if text_anchor:
            locator["textAnchor"] = text_anchor
        self.items.append(
            {
                "id": evidence_id,
                "label": label,
                "locator": locator,
                "locationStatus": "located",
                "materialStatus": material_status,
            }
        )
        return evidence_id

    def image(
        self,
        suffix: str,
        label: str,
        bbox: dict[str, float],
        *,
        material_status: str = "confirmed",
        material_key: str | None = None,
    ) -> str:
        binding = self._binding("image", material_key)
        evidence_id = f"ev-{self.project_id}-{suffix}"
        self.items.append(
            {
                "id": evidence_id,
                "label": label,
                "locator": {
                    "kind": "image",
                    "materialId": binding.material_id,
                    "materialVersionId": binding.material_version_id,
                    "bbox": bbox,
                },
                "locationStatus": "located",
                "materialStatus": material_status,
            }
        )
        return evidence_id

    def media(
        self,
        suffix: str,
        label: str,
        start_seconds: float,
        end_seconds: float,
        *,
        material_key: str,
        material_status: str = "confirmed",
    ) -> str:
        binding = self._binding("media", material_key)
        evidence_id = f"ev-{self.project_id}-{suffix}"
        self.items.append(
            {
                "id": evidence_id,
                "label": label,
                "locator": {
                    "kind": "media",
                    "materialId": binding.material_id,
                    "materialVersionId": binding.material_version_id,
                    "startSeconds": start_seconds,
                    "endSeconds": end_seconds,
                },
                "locationStatus": "located",
                "materialStatus": material_status,
            }
        )
        return evidence_id

    def scene(
        self,
        suffix: str,
        label: str,
        point_ids: list[str],
        *,
        material_key: str,
        material_status: str = "confirmed",
    ) -> str:
        binding = self._binding("scene", material_key)
        evidence_id = f"ev-{self.project_id}-{suffix}"
        self.items.append(
            {
                "id": evidence_id,
                "label": label,
                "locator": {
                    "kind": "scene",
                    "materialId": binding.material_id,
                    "materialVersionId": binding.material_version_id,
                    "pointIds": point_ids,
                },
                "locationStatus": "located",
                "materialStatus": material_status,
            }
        )
        return evidence_id

    def pending(self, suffix: str, label: str, *, material_status: str = "review") -> str:
        evidence_id = f"ev-{self.project_id}-{suffix}"
        self.items.append(
            {
                "id": evidence_id,
                "label": label,
                "locator": None,
                "locationStatus": "pending",
                "materialStatus": material_status,
            }
        )
        return evidence_id


__all__ = ["EvidenceRegistry", "MaterialBinding"]

"""Resolve evaluation-only material fixtures after repository externalization."""

from __future__ import annotations

import os
from pathlib import Path


BACK_ROOT = Path(__file__).resolve().parents[2]


def native_material_pack_root() -> Path:
    """Return the physical pack root without changing logical fixture refs."""

    import_root = os.getenv("COMPARE_IMPORT_ROOT", "").strip()
    if import_root:
        candidate = Path(import_root)
        if not candidate.is_absolute():
            candidate = BACK_ROOT / candidate
        return candidate.resolve()

    material_root = os.getenv("COMPARE_MATERIAL_ROOT", "").strip()
    if material_root:
        return (Path(material_root) / "native-material-packs").resolve()

    return (BACK_ROOT / "runtime" / "native-material-packs").resolve()

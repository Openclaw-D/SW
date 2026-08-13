from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.config import Settings


MaterialRootStatus = Literal["available", "not_configured", "invalid_root"]


@dataclass(frozen=True, slots=True)
class ExternalMaterialRoot:
    """Validated, non-browsable location for archived P5 material packages."""

    status: MaterialRootStatus
    pack_root: Path | None


def resolve_external_material_root(settings: Settings) -> ExternalMaterialRoot:
    """Validate only the fixed archive layout; never disclose its filesystem path."""
    configured_root = settings.material_root
    if configured_root is None:
        return ExternalMaterialRoot(
            status="invalid_root" if settings.material_root_config_invalid else "not_configured",
            pack_root=None,
        )
    if not configured_root.is_absolute() or configured_root.is_symlink():
        return ExternalMaterialRoot(status="invalid_root", pack_root=None)
    try:
        root = configured_root.resolve(strict=True)
        pack_root = root / "native-material-packs"
        if not root.is_dir() or pack_root.is_symlink():
            return ExternalMaterialRoot(status="invalid_root", pack_root=None)
        pack_root = pack_root.resolve(strict=True)
    except OSError:
        return ExternalMaterialRoot(status="invalid_root", pack_root=None)
    if not pack_root.is_dir() or root not in pack_root.parents:
        return ExternalMaterialRoot(status="invalid_root", pack_root=None)
    return ExternalMaterialRoot(status="available", pack_root=pack_root)

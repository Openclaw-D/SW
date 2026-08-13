from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path

from pydantic import ValidationError

from app.contracts.data_pack import ControlledImportManifest


@dataclass(frozen=True, slots=True)
class NativeSourceBinding:
    project_id: str
    material_id: str
    content_hash: str
    source_file_ref: str
    byte_size: int
    classification: str
    authorization_ref: str
    folder_path: str | None
    business_path: str | None


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


@lru_cache(maxsize=16)
def _load_native_source_bindings_cached(
    root_value: str,
    signature: tuple[tuple[str, int, int], ...],
) -> dict[tuple[str, str], NativeSourceBinding]:
    root = Path(root_value)
    del signature  # cache invalidation input; manifests are read below
    if not root.is_dir():
        return {}
    bindings: dict[tuple[str, str], NativeSourceBinding] = {}
    for manifest_path in sorted(root.glob("project-*/manifest.json")):
        try:
            manifest = ControlledImportManifest.model_validate_json(manifest_path.read_bytes())
        except (OSError, ValidationError, ValueError) as exc:
            raise RuntimeError(f"invalid native material manifest: {manifest_path}") from exc
        manifest_parent = manifest_path.parent.resolve()
        if root not in manifest_parent.parents:
            raise RuntimeError(f"native manifest escaped import root: {manifest_path}")
        for item in manifest.items:
            source = (manifest_parent / item.source_file).resolve()
            if manifest_parent not in source.parents or not source.is_file():
                raise RuntimeError(f"native material source is unavailable: {item.source_file}")
            digest, byte_size = _hash_file(source)
            if digest != item.sha256:
                raise RuntimeError(f"native material hash mismatch: {item.source_file}")
            key = (manifest.project_id, item.material_id)
            if key in bindings:
                raise RuntimeError(f"duplicate native material binding: {key}")
            bindings[key] = NativeSourceBinding(
                project_id=manifest.project_id,
                material_id=item.material_id,
                content_hash=digest,
                source_file_ref=source.relative_to(root).as_posix(),
                byte_size=byte_size,
                classification=item.classification.value,
                authorization_ref=item.authorization_ref,
                folder_path=item.material.get("folderPath"),
                business_path=item.material.get("businessPath"),
            )
    return bindings


def load_native_source_bindings(import_root: Path) -> dict[tuple[str, str], NativeSourceBinding]:
    """Read verified project-level demo manifests without scanning upload staging."""

    root = import_root.resolve()
    if not root.is_dir():
        return {}
    manifests = sorted(root.glob("project-*/manifest.json"))
    signature = tuple(
        (path.parent.name, path.stat().st_mtime_ns, path.stat().st_size)
        for path in manifests
    )
    return _load_native_source_bindings_cached(str(root), signature)


__all__ = ["NativeSourceBinding", "load_native_source_bindings"]

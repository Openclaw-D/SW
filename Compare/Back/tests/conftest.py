"""Test collection policy for optional, external offline evaluation packs.

The public source tree deliberately excludes the 24 native carrier packages.
They are required only by the frozen offline/oracle evaluation suite, never by
the application runtime.  Keep those assertions intact when an authorized pack
root is supplied, and make their absence explicit in a fresh public clone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.model_gateway.material_paths import native_material_pack_root


_NATIVE_PACK_EVAL_MODULES = {
    "test_blind_eval_release.py",
    "test_blind_eval_release_v3.py",
    "test_blind_eval_rubric.py",
    "test_blind_eval_rubric_v2.py",
    "test_codex_oracle.py",
    "test_model_gateway_runner.py",
}


def _native_pack_is_available() -> bool:
    root = native_material_pack_root()
    return (root / "package-index.json").is_file() and (
        root / "project-01" / "manifest.json"
    ).is_file()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip only asset-dependent offline evaluations when their packs are absent."""

    if _native_pack_is_available():
        return

    marker = pytest.mark.skip(
        reason=(
            "optional external native-material-packs are not configured; "
            "the public clone keeps production material import behavior unchanged"
        )
    )
    for item in items:
        if Path(str(item.fspath)).name in _NATIVE_PACK_EVAL_MODULES:
            item.add_marker(marker)

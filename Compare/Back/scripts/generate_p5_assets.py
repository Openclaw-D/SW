"""Legacy entrypoint for the project-unique P5 image generator.

Use ``build_native_material_packs.py`` for the complete 24-package build. This
module remains as a focused image-only utility and no longer copies the same
industry image into four project folders.
"""

from __future__ import annotations

from pathlib import Path

from build_native_material_packs import image_font, render_project_image


PROJECT_COUNT = 24
CATEGORIES = (
    "nameplate",
    "equipment-line",
    "raw-material",
    "process",
    "finished-product",
    "site",
)
INDUSTRIES = (
    "metal-processing",
    "plastic-processing",
    "textile",
    "printing-packaging",
    "electronics-manufacturing",
    "glass-processing",
)
MIN_BASE_BYTES = 80_000


def generate(root: Path) -> int:
    count = 0
    for project_index in range(1, PROJECT_COUNT + 1):
        project_dir = root / f"project-{project_index:02d}"
        project_dir.mkdir(parents=True, exist_ok=True)
        industry = INDUSTRIES[(project_index - 1) // 4]
        for category in CATEGORIES:
            source = root / "industry-base" / industry / f"{category}.png"
            if not source.is_file() or source.stat().st_size < MIN_BASE_BYTES:
                raise RuntimeError(f"missing or low-information synthetic base image: {source}")
            target = project_dir / f"{category}.png"
            render_project_image(
                source,
                target,
                project_index=project_index,
                project_no=f"SYN-P{project_index:02d}",
                material_label=category,
                category=category,
            )
            count += 1
    return count


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[1]
    asset_root = backend.parent / "Front" / "public" / "p5-materials"
    generated = generate(asset_root)
    print(f"generated {generated} synthetic PNG assets under {asset_root}")

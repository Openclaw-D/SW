"""Build the 24 refined P5 synthetic native-material packages.

The package mirrors the Windows business-folder structure supplied for review:
``基本证照 / 经营证明 / 现场照片 / 增信 / 租赁标的``.  Only browser-safe
business originals are declared by ``manifest.json``.  SceneSpec, GLB and
provenance records are generated below ``derived/`` and are never counted as
original material.

All people, companies, identifiers and values are deterministic synthetic demo
fixtures.  The builder never consumes or reproduces the user's screenshots.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps, PngImagePlugin
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


BACK_ROOT = Path(__file__).resolve().parents[1]
COMPARE_ROOT = BACK_ROOT.parent
FRONT_ASSET_ROOT = COMPARE_ROOT / "Front" / "public" / "p5-materials"
SOURCE_SHEET_ROOT = Path(__file__).resolve().parent / "assets" / "p5-contact-sheets"
DEFAULT_OUTPUT_ROOT = BACK_ROOT / "runtime" / "native-material-packs"
DEFAULT_ARTIFACT_TOOL = (
    Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime"
    / "dependencies" / "node" / "node_modules" / "@oai" / "artifact-tool"
    / "dist" / "artifact_tool.mjs"
)
PROJECT_COUNT = 24
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
DISPLAY_IMAGE_SIZE = (2048, 1152)
BUSINESS_ROOTS = ("基本证照", "经营证明", "现场照片", "增信", "租赁标的")

SITE_CELLS = {
    "site": 0,
    "site-front": 1,
    "site-overhead": 2,
    "site-rear": 3,
    "site-left": 4,
    "site-right": 5,
    "equipment-line": 6,
}
EQUIPMENT_CELLS = {
    "base-equipment-image": 0,
    "equipment-front": 1,
    "equipment-side": 2,
    "equipment-rear": 4,
}
INDUSTRY_BASE_IMAGES = {
    "raw-material": "raw-material.png",
    "process": "process.png",
    "finished-product": "finished-product.png",
    "nameplate": "nameplate.png",
}
CARD_IMAGES = {
    "business-license", "identity-front", "identity-back", "authorization",
    "property-summary", "property-detail",
}
IMAGE_FILE_CATEGORIES = {
    "设备总览.png": "base-equipment-image",
    "营业执照.png": "business-license",
    "法定代表人身份证正面.png": "identity-front",
    "法定代表人身份证背面.png": "identity-back",
    "持证授权确认.png": "authorization",
    "设备铭牌.png": "nameplate",
    "产线总览.png": "equipment-line",
    "原材料.png": "raw-material",
    "工艺过程.png": "process",
    "成品.png": "finished-product",
    "厂区总览.png": "site",
    "厂区俯视图.png": "site-overhead",
    "厂区正面平视图.png": "site-front",
    "厂区左侧平视图.png": "site-left",
    "厂区右侧平视图.png": "site-right",
    "厂区背面平视图.png": "site-rear",
    "设备正视图.png": "equipment-front",
    "设备侧视图.png": "equipment-side",
    "设备背视图.png": "equipment-rear",
    "房产信息截图.png": "property-summary",
    "房产明细截图.png": "property-detail",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_replace_directory(source: Path, target: Path, allowed_parent: Path) -> None:
    source, target, allowed_parent = source.resolve(), target.resolve(), allowed_parent.resolve()
    if target.parent != allowed_parent or not target.name.startswith("project-"):
        raise RuntimeError(f"refusing to replace unexpected directory: {target}")
    if target.exists():
        shutil.rmtree(target)
    source.replace(target)


def image_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    names = ("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "simhei.ttf")
    for name in names:
        candidate = Path("C:/Windows/Fonts") / name
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def industry_slug(project_id: str) -> str:
    return project_id.removeprefix("gen-").rsplit("-", 1)[0].replace("_", "-")


def contact_cell(path: Path, index: int) -> Image.Image:
    with Image.open(path) as source:
        sheet = source.convert("RGB")
    cell_width, cell_height = sheet.width / 4, sheet.height / 2
    column, row = index % 4, index // 4
    pad_x, pad_y = max(2, int(cell_width * 0.008)), max(2, int(cell_height * 0.008))
    box = (
        int(column * cell_width) + pad_x,
        int(row * cell_height) + pad_y,
        int((column + 1) * cell_width) - pad_x,
        int((row + 1) * cell_height) - pad_y,
    )
    return sheet.crop(box)


def project_photo(
    source: Image.Image,
    target: Path,
    *,
    project_number: int,
    project_no: str,
    label: str,
    category: str,
    provenance: str,
) -> None:
    # A small project-specific crop changes composition without pretending that
    # one contact-sheet cell is a separately generated photograph.
    source = source.convert("RGB")
    centering = (0.47 + (project_number % 4) * 0.02, 0.48 + (project_number % 3) * 0.02)
    image = ImageOps.fit(source, DISPLAY_IMAGE_SIZE, method=Image.Resampling.LANCZOS, centering=centering)
    image = ImageEnhance.Color(image).enhance(0.94 + (project_number % 3) * 0.025)
    image = ImageEnhance.Brightness(image).enhance(0.92 + (project_number % 4) * 0.018)
    draw = ImageDraw.Draw(image, "RGBA")
    band_top = image.height - 132
    draw.rectangle((0, band_top, image.width, image.height), fill=(8, 14, 24, 220))
    draw.rectangle((0, 0, image.width, 10), fill=(32, 112 + project_number % 48, 184, 235))
    draw.text((42, band_top + 24), f"{project_no} · {label}", font=image_font(34, bold=True), fill="#F8FAFC")
    draw.text((42, band_top + 78), "完整脱敏模拟原始图像 · 非真实客户现场", font=image_font(22), fill="#CBD5E1")
    token = hashlib.sha256(f"{project_no}:{category}".encode()).hexdigest()[:12].upper()
    draw.text((image.width - 330, band_top + 82), f"DEMO {token}", font=image_font(18, bold=True), fill="#7DD3FC")
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("compare_project", project_no)
    metadata.add_text("compare_category", category)
    metadata.add_text("data_status", "synthetic_demo")
    metadata.add_text("synthetic_source", provenance)
    image.save(target, format="PNG", optimize=True, pnginfo=metadata)


def render_card_image(
    target: Path,
    *,
    category: str,
    project_number: int,
    project_no: str,
    company_name: str,
    label: str,
) -> None:
    palette = {
        "business-license": ("#F7F1E8", "#B91C1C"),
        "identity-front": ("#E9F2F7", "#2563EB"),
        "identity-back": ("#E9F2F7", "#2563EB"),
        "authorization": ("#EFF6FF", "#0F766E"),
        "property-summary": ("#F8FAFC", "#4F46E5"),
        "property-detail": ("#F8FAFC", "#7C3AED"),
    }
    background, accent = palette[category]
    image = Image.new("RGB", DISPLAY_IMAGE_SIZE, background)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((74, 68, 1974, 1058), radius=30, fill="#FFFFFF", outline=accent, width=5)
    draw.rectangle((74, 68, 1974, 218), fill=accent)
    draw.text((120, 103), label, font=image_font(46, bold=True), fill="#FFFFFF")
    draw.text((120, 245), company_name, font=image_font(38, bold=True), fill="#111827")
    token = hashlib.sha256(f"{project_no}:{category}".encode()).hexdigest()[:18].upper()
    if category.startswith("identity") or category == "authorization":
        draw.rounded_rectangle((130, 340, 610, 850), radius=28, fill="#DBEAFE", outline="#93C5FD", width=3)
        # Deliberately non-biometric silhouette: it cannot resemble a person.
        draw.ellipse((280, 425, 460, 605), fill="#94A3B8")
        draw.rounded_rectangle((220, 620, 520, 785), radius=70, fill="#94A3B8")
        fields = [
            ("证件标识", f"SYN-DEMO-{token[:10]}"),
            ("关联项目", project_no),
            ("材料状态", "完整脱敏模拟"),
            ("核验说明", "无真人脸 · 无真实证件号码"),
        ]
        start_x = 690
    elif category.startswith("property"):
        draw.rounded_rectangle((130, 340, 610, 850), radius=18, fill="#EEF2FF", outline="#C7D2FE", width=3)
        draw.rectangle((205, 430, 535, 690), fill="#CBD5E1", outline="#64748B", width=4)
        draw.polygon([(180, 440), (370, 300), (560, 440)], fill="#94A3B8")
        fields = [
            ("资产标识", f"SYN-PROP-{project_number:03d}"),
            ("权属主体", company_name),
            ("权利状态", "待人工核验"),
            ("页面性质", "模拟信息界面 · 非权属证明"),
        ]
        start_x = 690
    else:
        draw.ellipse((145, 350, 410, 615), fill="#FEE2E2", outline="#DC2626", width=8)
        draw.text((212, 427), "演示", font=image_font(52, bold=True), fill="#B91C1C")
        fields = [
            ("统一标识", f"SYN-{token}"),
            ("主体类型", "系统生成演示企业"),
            ("登记状态", "模拟有效"),
            ("使用边界", "非真实企业登记材料"),
        ]
        start_x = 530
    y = 360
    for field, value in fields:
        draw.text((start_x, y), field, font=image_font(25, bold=True), fill="#475569")
        draw.text((start_x + 235, y), value, font=image_font(29), fill="#111827")
        draw.line((start_x, y + 58, 1840, y + 58), fill="#E2E8F0", width=2)
        y += 112
    draw.text((120, 950), "SYNTHETIC DEMO / 完整脱敏模拟 / 禁止作为真实凭证使用", font=image_font(25, bold=True), fill=accent)
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("compare_project", project_no)
    metadata.add_text("compare_category", category)
    metadata.add_text("data_status", "synthetic_demo")
    image.save(target, format="PNG", optimize=True, pnginfo=metadata)


def image_category(material: dict) -> str:
    try:
        return IMAGE_FILE_CATEGORIES[material["fileName"]]
    except KeyError as exc:
        raise RuntimeError(f"unmapped image original: {material.get('businessPath')}") from exc


def render_material_image(material: dict, catalog: dict, target: Path, project_number: int) -> dict[str, str | int]:
    category = image_category(material)
    slug = industry_slug(catalog["projectId"])
    if category in CARD_IMAGES:
        render_card_image(
            target, category=category, project_number=project_number,
            project_no=catalog["projectNo"], company_name=catalog["companyName"], label=material["label"],
        )
        return {"category": category, "sourceType": "deterministic-card", "sourceCell": -1}
    if category in SITE_CELLS:
        cell = SITE_CELLS[category]
        source_path = SOURCE_SHEET_ROOT / f"{slug}-site.png"
        source = contact_cell(source_path, cell)
        provenance = f"imagegen-contact-sheet:{source_path.name}:cell-{cell + 1}"
    elif category in EQUIPMENT_CELLS:
        cell = EQUIPMENT_CELLS[category]
        source_path = SOURCE_SHEET_ROOT / f"{slug}-equipment.png"
        source = contact_cell(source_path, cell)
        provenance = f"imagegen-contact-sheet:{source_path.name}:cell-{cell + 1}"
    else:
        cell = -1
        source_path = FRONT_ASSET_ROOT / "industry-base" / slug / INDUSTRY_BASE_IMAGES[category]
        with Image.open(source_path) as base:
            source = base.convert("RGB")
        provenance = f"existing-synthetic-industry-base:{source_path.name}"
    if not source_path.is_file():
        raise RuntimeError(f"missing synthetic image source: {source_path}")
    project_photo(
        source, target, project_number=project_number, project_no=catalog["projectNo"],
        label=material["label"], category=category, provenance=provenance,
    )
    return {"category": category, "sourceType": provenance.split(":", 1)[0], "sourceCell": cell + 1}


def _line_pair(line: object, ordinal: int) -> tuple[str, str]:
    value = str(line)
    for separator in ("：", ":", "（"):
        if separator in value:
            left, right = value.split(separator, 1)
            return left.strip() or f"核验项 {ordinal}", right.strip(" ）") or "已记录"
    return f"核验项 {ordinal}", value


def _draw_pdf_table(document: canvas.Canvas, rows: list[tuple[str, str]], *, top: float, page_width: float) -> None:
    left, right, row_height = 46, page_width - 46, 28
    document.setFillColor(HexColor("#E8EEF7"))
    document.rect(left, top - row_height, right - left, row_height, fill=1, stroke=0)
    document.setFillColor(HexColor("#334155")); document.setFont("STSong-Light", 9)
    document.drawString(left + 10, top - 18, "核验字段"); document.drawString(left + 190, top - 18, "项目级脱敏模拟值")
    y = top - row_height
    for ordinal, (label, value) in enumerate(rows):
        document.setFillColor(HexColor("#FFFFFF") if ordinal % 2 == 0 else HexColor("#F8FAFC"))
        document.rect(left, y - row_height, right - left, row_height, fill=1, stroke=0)
        document.setStrokeColor(HexColor("#CBD5E1")); document.rect(left, y - row_height, right - left, row_height, fill=0, stroke=1)
        document.line(left + 174, y - row_height, left + 174, y)
        document.setFillColor(HexColor("#334155")); document.setFont("STSong-Light", 9)
        document.drawString(left + 10, y - 18, label[:24]); document.drawString(left + 184, y - 18, value[:52])
        y -= row_height


def render_pdf(material: dict, catalog: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except KeyError:
        pass
    page_width, page_height = A4
    document = canvas.Canvas(str(target), pagesize=A4, pageCompression=1, invariant=1)
    document.setTitle(material["label"]); document.setAuthor("Compare synthetic demo generator")
    document.setSubject("Synthetic and de-identified P5 material")
    for page in material["pages"]:
        document.setFillColor(HexColor("#F4F6F9")); document.rect(0, 0, page_width, page_height, fill=1, stroke=0)
        document.setFillColor(HexColor("#162033")); document.rect(0, page_height - 74, page_width, 74, fill=1, stroke=0)
        document.setFillColor(HexColor("#FFFFFF")); document.setFont("STSong-Light", 16)
        document.drawString(38, page_height - 44, "COMPARE · P5 原始材料")
        document.setFont("STSong-Light", 9); document.drawRightString(page_width - 38, page_height - 43, "完整脱敏模拟 · 非真实客户材料")
        document.setFillColor(HexColor("#172033")); document.setFont("STSong-Light", 18)
        document.drawString(46, page_height - 120, str(page.get("title") or material["label"]))
        document.setStrokeColor(HexColor("#CBD5E1")); document.line(46, page_height - 137, page_width - 46, page_height - 137)
        rows = [_line_pair(line, ordinal + 1) for ordinal, line in enumerate(page.get("lines", []))]
        rows.extend([("数据状态", "完整脱敏模拟 · synthetic_demo"), ("核验边界", "单项目事实勾稽，不代表真实原件或统计验证模型")])
        _draw_pdf_table(document, rows, top=page_height - 166, page_width=page_width)
        document.setFillColor(HexColor("#2563EB")); document.roundRect(46, 102, 194, 24, 4, fill=1, stroke=0)
        document.setFillColor(HexColor("#FFFFFF")); document.setFont("STSong-Light", 9)
        document.drawCentredString(143, 110, "DE-IDENTIFIED SYNTHETIC")
        document.saveState(); document.setFillColor(Color(0.12, 0.18, 0.29, alpha=0.055)); document.setFont("Helvetica-Bold", 44)
        document.translate(page_width / 2, page_height / 2); document.rotate(32); document.drawCentredString(0, 0, "SYNTHETIC DEMO"); document.restoreState()
        document.setFillColor(HexColor("#64748B")); document.setFont("STSong-Light", 8)
        footer = f"{catalog['projectNo']} | {catalog['companyName']} | {material['businessPath']} | page {page['page']}/{material['pageCount']}"
        document.drawString(38, 30, footer[:125]); document.showPage()
    document.save()


def write_factory_glb(target: Path, *, project_number: int, project_no: str) -> None:
    """Write a safe, compact derived factory-layout GLB (not a raw original)."""
    boxes = [
        (0.0, -0.2, 0.0, 15.0, 0.3, 10.0),
        (-5.0, 0.0, 0.5, 2.8, 2.5, 2.6), (0.0, 0.0, 0.5, 2.8, 2.5, 2.6), (5.0, 0.0, 0.5, 2.8, 2.5, 2.6),
        (-4.0, 0.0, -3.0, 2.2, 1.2, 1.4), (0.0, 0.0, -3.0, 2.2, 1.2, 1.4), (4.0, 0.0, -3.0, 2.2, 1.2, 1.4),
    ]
    positions: list[float] = []; indices: list[int] = []; normals: list[float] = []
    vertices = ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))
    faces = ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7))
    for box_index, (cx, cy, cz, sx, sy, sz) in enumerate(boxes):
        base = box_index * 8
        for x, y, z in vertices:
            positions.extend((cx + x * sx / 2, cy + (y + 1) * sy / 2, cz + z * sz / 2)); normals.extend((0.0, 1.0, 0.0))
        for a, b, c, d in faces:
            indices.extend((base + a, base + b, base + c, base + a, base + c, base + d))
    position_bin = struct.pack(f"<{len(positions)}f", *positions); normal_bin = struct.pack(f"<{len(normals)}f", *normals); index_bin = struct.pack(f"<{len(indices)}H", *indices)
    binary = position_bin + normal_bin + index_bin
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    accent = [0.16 + (project_number % 4) * 0.05, 0.38 + (project_number % 3) * 0.06, 0.62, 1.0]
    payload = {
        "asset": {"version": "2.0", "generator": "COMPARE derived synthetic factory", "copyright": f"Synthetic demo only: {project_no}"},
        "scene": 0, "scenes": [{"name": f"{project_no} derived factory", "nodes": [0]}],
        "nodes": [{"name": "derived-factory-layout", "mesh": 0}],
        "meshes": [{"name": "floor-and-equipment", "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}]}],
        "materials": [{"name": "synthetic-industrial-blue", "pbrMetallicRoughness": {"baseColorFactor": accent, "metallicFactor": 0.55, "roughnessFactor": 0.42}}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bin), "target": 34962},
            {"buffer": 0, "byteOffset": len(position_bin), "byteLength": len(normal_bin), "target": 34962},
            {"buffer": 0, "byteOffset": len(position_bin) + len(normal_bin), "byteLength": len(index_bin), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(positions) // 3, "type": "VEC3", "min": [-7.5, -0.2, -5.0], "max": [7.5, 2.5, 5.0]},
            {"bufferView": 1, "componentType": 5126, "count": len(normals) // 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
    }
    json_chunk = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(struct.pack("<4sII", b"glTF", 2, total_length) + struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk + struct.pack("<I4s", len(binary), b"BIN\x00") + binary)


def write_derived(project_root: Path, catalog: dict, materials: list[dict], project_number: int, provenance: list[dict]) -> dict[str, str]:
    by_file = {entry["material"]["fileName"]: entry["material"]["id"] for entry in materials}
    derived = project_root / "derived"
    scene_path = derived / "scene-spec.json"; model_path = derived / "factory-layout.glb"
    site_ids = [entry["material"]["id"] for entry in materials if entry["material"].get("folderPath", "").startswith("现场照片/")]
    write_json(scene_path, {
        "schemaVersion": "compare-scene-spec-v2", "projectId": catalog["projectId"], "projectNo": catalog["projectNo"],
        "isSimulated": True, "dataStatus": "derived_synthetic", "executionPolicy": "declarative-only",
        "sourceMaterialIds": site_ids,
        "hotspots": [
            {"id": "factory", "label": "厂区", "position": [0, 0, 0], "materialId": by_file.get("厂区总览.png")},
            {"id": "equipment", "label": "租赁设备", "position": [0, 1, 1], "materialId": by_file.get("设备正视图.png")},
            {"id": "process", "label": "工艺", "position": [-3, 1, -2], "materialId": by_file.get("工艺过程.png")},
        ],
        "disclaimer": "由模拟原始图片派生的受控展示数据；不是原始材料、扫描重建、CAD 或 3DGS。",
    })
    write_factory_glb(model_path, project_number=project_number, project_no=catalog["projectNo"])
    write_json(derived / "image-provenance.json", {
        "schemaVersion": "compare-image-provenance-v1", "isSimulated": True,
        "note": "contact-sheet cell is the generation source; project crop is not claimed as an independent ImageGen call",
        "items": provenance,
    })
    return {"sceneSpec": "derived/scene-spec.json", "factoryModel": "derived/factory-layout.glb", "imageProvenance": "derived/image-provenance.json"}


def validate_business_path(material: dict) -> Path:
    folder_path, business_path, file_name = material.get("folderPath"), material.get("businessPath"), material.get("fileName")
    if not folder_path or not business_path or business_path != f"{folder_path}/{file_name}":
        raise RuntimeError(f"invalid business path contract: {material.get('id')}")
    relative = Path(business_path)
    if relative.parts[0] not in BUSINESS_ROOTS or relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"business path outside frozen roots: {business_path}")
    return relative


def build_packages(staging_root: Path, front_staging: Path, project_numbers: tuple[int, ...]) -> tuple[list[dict], list[dict]]:
    sys.path.insert(0, str(BACK_ROOT))
    from app.services.generation.generator import DEFAULT_GENERATOR_SEED, generate_project_bundle

    package_specs: list[dict] = []; workbook_specs: list[dict] = []
    qa_projects = {1, 5, 9, 13, 17, 21}
    for project_number in project_numbers:
        bundle = generate_project_bundle(DEFAULT_GENERATOR_SEED, project_number - 1).to_mapping()
        catalog = bundle["catalog"]; folder_name = f"project-{project_number:02d}"
        project_root = staging_root / folder_name; project_front = front_staging / folder_name
        entries: list[dict] = []; provenance: list[dict] = []
        for material in bundle["workbench"]["materials"]:
            business_relative = validate_business_path(material)
            relative = Path("originals") / business_relative
            target = project_root / relative; kind = material["kind"]
            if kind == "excel":
                render_dir = (
                    staging_root / "_qa" / "xlsx" / folder_name / target.stem
                    if project_number in qa_projects and material["id"].endswith("-data")
                    else None
                )
                workbook_specs.append({
                    "outputPath": str(target.resolve()), "renderDir": str(render_dir.resolve()) if render_dir else None,
                    "projectNo": catalog["projectNo"], "label": material["label"], "businessPath": material["businessPath"],
                    "sheets": material["sheets"],
                })
            elif kind == "pdf":
                render_pdf(material, catalog, target)
            elif kind == "image":
                source_record = render_material_image(material, catalog, target, project_number)
                source_record.update({"materialId": material["id"], "businessPath": material["businessPath"]})
                provenance.append(source_record)
                project_front.mkdir(parents=True, exist_ok=True)
                category = image_category(material)
                shutil.copy2(target, project_front / f"{category}.png")
                # P5 Front 的既有公开 URL 仍使用 equipment-overview；该别名只服务前端兼容，
                # 不属于 originals，也不会进入 manifest 或 ZIP 的原始材料清单。
                if category == "base-equipment-image":
                    shutil.copy2(target, project_front / "equipment-overview.png")
            else:
                raise RuntimeError(f"derived/non-original kind is forbidden in manifest: {kind}")
            entries.append({"material": material, "relative": relative.as_posix()})
        companions = write_derived(project_root, catalog, entries, project_number, provenance)
        package_specs.append({
            "folderName": folder_name, "catalog": catalog, "generation": bundle["generation"],
            "materialEntries": entries, "expectedCounts": dict(Counter(entry["material"]["kind"] for entry in entries)),
            "companionAssets": companions,
        })
        write_json(project_root / "package-summary.json", {
            "schemaVersion": "compare-native-pack-summary-v2", "project": catalog,
            "originalMaterialCount": len(entries), "carrierCounts": dict(Counter(entry["material"]["kind"] for entry in entries)),
            "businessRoots": list(BUSINESS_ROOTS), "isSimulated": True,
            "disclaimer": "本目录仅含固定种子的完整脱敏模拟材料；originals 是输入，derived/控制文件不计原始材料。",
            "companionAssets": companions,
        })
    return package_specs, workbook_specs


def finalize_packages(staging_root: Path, package_specs: list[dict]) -> list[dict]:
    archives = staging_root / "archives"; archives.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []; all_hashes: set[str] = set()
    for spec in package_specs:
        project_root = staging_root / spec["folderName"]; items: list[dict] = []; project_hashes: set[str] = set(); counts: Counter[str] = Counter()
        for entry in spec["materialEntries"]:
            source = project_root / entry["relative"]
            if not source.is_file() or source.stat().st_size <= 0:
                raise RuntimeError(f"native source was not generated: {source}")
            digest = sha256_file(source)
            if digest in project_hashes or digest in all_hashes:
                raise RuntimeError(f"business-original content must be globally distinct: {source}")
            project_hashes.add(digest); all_hashes.add(digest)
            material = entry["material"]; counts[material["kind"]] += 1
            items.append({
                "materialId": material["id"], "sourceFile": entry["relative"], "sha256": digest,
                "classification": "synthetic_demo", "authorizationRef": "compare-p5-synthetic-v2", "material": material,
            })
        if dict(counts) != spec["expectedCounts"]:
            raise RuntimeError(f"unexpected carrier counts for {spec['folderName']}: {counts}")
        write_json(project_root / "manifest.json", {"manifestVersion": "1.0", "projectId": spec["catalog"]["projectId"], "items": items})
        archive = archives / f"{spec['folderName']}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
            for source in sorted(project_root.rglob("*")):
                if source.is_file():
                    package.write(source, source.relative_to(project_root).as_posix())
        directory_bytes = sum(path.stat().st_size for path in project_root.rglob("*") if path.is_file())
        if directory_bytes > MAX_PACKAGE_BYTES or archive.stat().st_size > MAX_PACKAGE_BYTES:
            raise RuntimeError(f"100 MiB project gate failed: {project_root}")
        index.append({
            "folder": spec["folderName"], "projectId": spec["catalog"]["projectId"], "projectNo": spec["catalog"]["projectNo"],
            "companyName": spec["catalog"]["companyName"], "industry": spec["catalog"]["industry"],
            "manifestRef": f"{spec['folderName']}/manifest.json", "archive": f"archives/{archive.name}",
            "archiveBytes": archive.stat().st_size, "directoryBytes": directory_bytes, "archiveSha256": sha256_file(archive),
            "materialCount": len(items), "carrierCounts": dict(counts), "businessRoots": list(BUSINESS_ROOTS),
            "companionAssets": spec["companionAssets"],
        })
    expected_hashes = sum(len(spec["materialEntries"]) for spec in package_specs)
    if len(all_hashes) != expected_hashes:
        raise RuntimeError(f"source hash gate failed: {len(all_hashes)} != {expected_hashes}")
    write_json(staging_root / "package-index.json", {
        "schemaVersion": "compare-native-pack-index-v2", "projectCount": len(index),
        "materialCount": expected_hashes, "uniqueSourceHashCount": len(all_hashes), "isSimulated": True, "packages": index,
    })
    return index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--artifact-tool", type=Path, default=DEFAULT_ARTIFACT_TOOL)
    parser.add_argument("--node", default="node")
    parser.add_argument("--projects", default="all", help="all or comma-separated 1..24; partial builds are visual QA only")
    args = parser.parse_args(); output_root = args.output_root.resolve()
    if output_root.parent.resolve() != (BACK_ROOT / "runtime").resolve():
        raise RuntimeError("output root must be a direct child of Compare/Back/runtime")
    if not args.artifact_tool.is_file():
        raise RuntimeError("@oai/artifact-tool not found; pass the configured workspace dependency runtime path")
    if args.projects == "all":
        project_numbers = tuple(range(1, PROJECT_COUNT + 1))
    else:
        project_numbers = tuple(sorted({int(value.strip()) for value in args.projects.split(",") if value.strip()}))
        if not project_numbers or any(number < 1 or number > PROJECT_COUNT for number in project_numbers):
            raise RuntimeError("--projects must contain values from 1 through 24")
    for slug in ("metal-processing", "plastic-processing", "textile", "printing-packaging", "electronics-manufacturing", "glass-processing"):
        for suffix in ("site", "equipment"):
            if not (SOURCE_SHEET_ROOT / f"{slug}-{suffix}.png").is_file():
                raise RuntimeError(f"missing contact sheet: {slug}-{suffix}")
    runtime_root = BACK_ROOT / "runtime"; runtime_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="compare-p5-native-", dir=runtime_root) as temporary:
        staging_root = Path(temporary) / "native-material-packs"; front_staging = Path(temporary) / "front-assets"
        staging_root.mkdir(parents=True); front_staging.mkdir(parents=True)
        package_specs, workbook_specs = build_packages(staging_root, front_staging, project_numbers)
        workbook_spec_path = Path(temporary) / "workbook-specs.json"
        write_json(workbook_spec_path, {"workbooks": workbook_specs})
        subprocess.run([args.node, str(BACK_ROOT / "scripts" / "build_native_workbooks.mjs"), "--spec", str(workbook_spec_path), "--artifact-tool", str(args.artifact_tool.resolve())], check=True)
        index = finalize_packages(staging_root, package_specs)
        if output_root.exists():
            shutil.rmtree(output_root)
        staging_root.replace(output_root)
        for project_number in project_numbers:
            name = f"project-{project_number:02d}"
            safe_replace_directory(front_staging / name, FRONT_ASSET_ROOT / name, FRONT_ASSET_ROOT)
    print(json.dumps({
        "outputRoot": str(output_root), "projectCount": len(index),
        "materialCount": sum(item["materialCount"] for item in index),
        "largestArchiveBytes": max(item["archiveBytes"] for item in index),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

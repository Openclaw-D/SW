"""Verify the refined P5 native material packages without starting FastAPI."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

from PIL import Image
from pypdf import PdfReader


MAX_PACKAGE_BYTES = 100 * 1024 * 1024
EXPECTED_PROJECTS = 24
EXPECTED_MATERIALS_PER_PROJECT = 56
EXPECTED_COUNTS = {"excel": 21, "pdf": 14, "image": 21}
BUSINESS_ROOTS = ("基本证照", "经营证明", "现场照片", "增信", "租赁标的")
REQUIRED_BUSINESS_PATHS = {
    "基本证照/营业执照.png",
    "基本证照/身份证明/法定代表人身份证正面.png",
    "基本证照/身份证明/法定代表人身份证背面.png",
    "基本证照/身份证明/持证授权确认.png",
    "经营证明/厂房租赁合同/厂房租赁合同.pdf",
    "经营证明/电费/电费及用电明细.xlsx",
    "经营证明/工资/工资发放明细.xlsx",
    "经营证明/纳税申报表/纳税申报表.xlsx",
    "经营证明/开票资料/销项发票.xlsx",
    "经营证明/开票资料/进项发票.xlsx",
    "经营证明/财务报表/资产负债表.xlsx",
    "经营证明/财务报表/利润表.xlsx",
    "经营证明/开票资料/主要上下游.xlsx",
    "现场照片/厂区照片/厂区俯视图.png",
    "现场照片/厂区照片/厂区正面平视图.png",
    "现场照片/厂区照片/厂区左侧平视图.png",
    "现场照片/厂区照片/厂区右侧平视图.png",
    "现场照片/厂区照片/厂区背面平视图.png",
    "现场照片/设备照片/设备正视图.png",
    "现场照片/设备照片/设备侧视图.png",
    "现场照片/设备照片/设备背视图.png",
    "增信/企业征信/企业征信报告.pdf",
    "增信/个人征信/个人征信报告.pdf",
    "增信/资产证明/房产信息截图.png",
    "增信/流水信息/银行流水.xlsx",
    "租赁标的/设备合同/设备买卖合同.pdf",
    "租赁标的/设备报价/设备报价单.pdf",
    "租赁标的/设备清单/设备清单.xlsx",
    "租赁标的/设备铭牌/设备铭牌.png",
}
VIEW_NAMES = {
    "厂区俯视图.png", "厂区正面平视图.png", "厂区左侧平视图.png", "厂区右侧平视图.png", "厂区背面平视图.png",
    "设备正视图.png", "设备侧视图.png", "设备背视图.png",
}
FORMULA_TOKENS = {
    "资产负债表.xlsx": ("资产=负债+权益",),
    "利润表.xlsx": ("收入-成本费用=净利润",),
    "电费及用电明细.xlsx": (),
    "销项发票.xlsx": ("发票金额", "确认收入"),
    "进项发票.xlsx": ("税额",),
    "银行流水.xlsx": ("净额",),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def visual_fingerprint(path: Path) -> str:
    """忽略底部演示标记后计算画面指纹，防止仅靠改字或元数据制造“多视角”。"""
    with Image.open(path) as image:
        grayscale = image.convert("L").crop((0, 0, image.width, 960))
        reduced = grayscale.resize((16, 16), Image.Resampling.LANCZOS)
        pixels = list(reduced.get_flattened_data())
    average = sum(pixels) / len(pixels)
    return "".join("1" if value >= average else "0" for value in pixels)


def assert_glb(path: Path) -> None:
    header = path.read_bytes()[:12]
    if len(header) != 12 or header[:4] != b"glTF":
        raise AssertionError(f"invalid GLB header: {path}")
    _, version, declared_length = struct.unpack("<4sII", header)
    if version != 2 or declared_length != path.stat().st_size:
        raise AssertionError(f"invalid GLB version/length: {path}")


def workbook_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as workbook:
        names = set(workbook.namelist())
        if "xl/workbook.xml" not in names or not any(name.startswith("xl/worksheets/") for name in names):
            raise AssertionError(f"invalid workbook: {path}")
        return "\n".join(
            workbook.read(name).decode("utf-8", "replace")
            for name in sorted(names)
            if name.endswith(".xml")
        )


def has_formula_element(xml: str) -> bool:
    """Accept both default-namespace ``<f>`` and prefixed ``<x:f>`` OOXML."""
    return re.search(r"<(?:[A-Za-z_][\w.-]*:)?f(?:\s|>)", xml) is not None


def verify(root: Path) -> dict:
    index = json.loads((root / "package-index.json").read_text(encoding="utf-8"))
    packages = index["packages"]
    if index["projectCount"] != EXPECTED_PROJECTS or len(packages) != EXPECTED_PROJECTS:
        raise AssertionError("exactly 24 packages are required")
    global_hashes: set[str] = set(); project_signatures: set[tuple[str, ...]] = set()
    largest_archive = largest_directory = image_count = pdf_pages = formula_workbooks = 0
    root_counter: Counter[str] = Counter(); carrier_counter: Counter[str] = Counter()
    for package in packages:
        project_root = root / package["folder"]
        manifest = json.loads((project_root / "manifest.json").read_text(encoding="utf-8"))
        items = manifest["items"]
        if len(items) != EXPECTED_MATERIALS_PER_PROJECT or package["materialCount"] != EXPECTED_MATERIALS_PER_PROJECT:
            raise AssertionError(f"unexpected material count: {package['folder']}")
        counts = Counter(item["material"]["kind"] for item in items)
        if dict(counts) != EXPECTED_COUNTS or package["carrierCounts"] != EXPECTED_COUNTS:
            raise AssertionError(f"carrier mismatch: {package['folder']} {counts}")
        carrier_counter.update(counts)
        business_paths: set[str] = set(); project_hashes: list[str] = []
        for item in items:
            material = item["material"]; kind = material["kind"]
            business_path = material.get("businessPath"); folder_path = material.get("folderPath")
            if not business_path or business_path != f"{folder_path}/{material['fileName']}":
                raise AssertionError(f"invalid business path pair: {item['materialId']}")
            if business_path.split("/", 1)[0] not in BUSINESS_ROOTS:
                raise AssertionError(f"unexpected business root: {business_path}")
            if item["sourceFile"] != f"originals/{business_path}":
                raise AssertionError(f"sourceFile must mirror originals/businessPath: {item['sourceFile']}")
            if kind in {"scene", "media"} or re.search(r"(^|/)(scene|media)(/|$)", item["sourceFile"], re.I):
                raise AssertionError(f"derived carrier declared as original: {item['sourceFile']}")
            source = project_root / item["sourceFile"]
            digest = sha256_file(source) if source.is_file() else ""
            if digest != item["sha256"] or digest in global_hashes:
                raise AssertionError(f"invalid or duplicate original/hash: {source}")
            global_hashes.add(digest); project_hashes.append(digest); business_paths.add(business_path)
            root_counter[business_path.split("/", 1)[0]] += 1
            if item["classification"] != "synthetic_demo" or item["authorizationRef"] != "compare-p5-synthetic-v2":
                raise AssertionError(f"synthetic boundary missing: {source}")
            if kind == "excel":
                xml = workbook_xml(source)
                if "#REF!" in xml or "#DIV/0!" in xml or "#VALUE!" in xml or "#NAME?" in xml:
                    raise AssertionError(f"formula error token in workbook: {source}")
                if material["fileName"] in FORMULA_TOKENS and not has_formula_element(xml):
                    raise AssertionError(f"workbook formula missing: {source}")
                for token in FORMULA_TOKENS.get(material["fileName"], ()):
                    if token not in xml:
                        raise AssertionError(f"workbook reconciliation/formula token {token!r} missing: {source}")
                if material["fileName"] in FORMULA_TOKENS:
                    formula_workbooks += 1
            elif kind == "pdf":
                reader = PdfReader(str(source)); pdf_pages += len(reader.pages)
                if not reader.pages:
                    raise AssertionError(f"empty PDF: {source}")
                if "完整脱敏模拟" not in "".join(page.extract_text() or "" for page in reader.pages):
                    raise AssertionError(f"PDF simulation mark missing: {source}")
            elif kind == "image":
                with Image.open(source) as image:
                    if image.format != "PNG" or image.size != (2048, 1152):
                        raise AssertionError(f"image format/resolution mismatch: {source} {image.size}")
                    if image.info.get("data_status") != "synthetic_demo":
                        raise AssertionError(f"image metadata simulation mark missing: {source}")
                image_count += 1
        if not REQUIRED_BUSINESS_PATHS <= business_paths:
            raise AssertionError(f"required screenshot-aligned originals missing: {package['folder']} {sorted(REQUIRED_BUSINESS_PATHS - business_paths)}")
        view_items = [item for item in items if item["material"]["fileName"] in VIEW_NAMES]
        view_hashes = {item["sha256"] for item in view_items}
        if len(view_hashes) != len(VIEW_NAMES):
            raise AssertionError(f"view images are not distinct: {package['folder']}")
        view_fingerprints = {
            visual_fingerprint(project_root / item["sourceFile"])
            for item in view_items
        }
        if len(view_fingerprints) != len(VIEW_NAMES):
            raise AssertionError(f"view images only differ by overlay/metadata: {package['folder']}")
        project_signature = tuple(sorted(project_hashes))
        if project_signature in project_signatures:
            raise AssertionError(f"cross-project package duplication: {package['folder']}")
        project_signatures.add(project_signature)
        scene_spec = project_root / package["companionAssets"]["sceneSpec"]
        glb = project_root / package["companionAssets"]["factoryModel"]
        provenance = project_root / package["companionAssets"]["imageProvenance"]
        spec = json.loads(scene_spec.read_text(encoding="utf-8")); prov = json.loads(provenance.read_text(encoding="utf-8"))
        if not scene_spec.is_relative_to(project_root / "derived") or spec.get("executionPolicy") != "declarative-only" or "url" in json.dumps(spec).lower():
            raise AssertionError(f"unsafe/misplaced derived scene: {project_root}")
        if len(prov.get("items", [])) != EXPECTED_COUNTS["image"]:
            raise AssertionError(f"incomplete image provenance: {project_root}")
        assert_glb(glb)
        archive = root / package["archive"]
        if sha256_file(archive) != package["archiveSha256"]:
            raise AssertionError(f"archive hash mismatch: {archive}")
        with zipfile.ZipFile(archive) as zip_file:
            zip_names = set(zip_file.namelist())
            if "manifest.json" not in zip_names or not all(item["sourceFile"] in zip_names for item in items):
                raise AssertionError(f"archive is not controlled-import compatible: {archive}")
        directory_bytes = sum(path.stat().st_size for path in project_root.rglob("*") if path.is_file())
        if directory_bytes > MAX_PACKAGE_BYTES or archive.stat().st_size > MAX_PACKAGE_BYTES:
            raise AssertionError(f"100 MiB gate failed: {package['folder']}")
        if package["directoryBytes"] != directory_bytes or package["archiveBytes"] != archive.stat().st_size:
            raise AssertionError(f"size metadata mismatch: {package['folder']}")
        largest_archive = max(largest_archive, archive.stat().st_size); largest_directory = max(largest_directory, directory_bytes)
    expected_total = EXPECTED_PROJECTS * EXPECTED_MATERIALS_PER_PROJECT
    if index["materialCount"] != expected_total or index["uniqueSourceHashCount"] != expected_total or len(global_hashes) != expected_total:
        raise AssertionError("index/hash total mismatch")
    return {
        "projects": len(packages), "materials": len(global_hashes), "carrierCounts": dict(carrier_counter),
        "businessRootCounts": dict(root_counter), "images": image_count, "pdfPages": pdf_pages,
        "formulaCheckedWorkbooks": formula_workbooks,
        "largestArchiveBytes": largest_archive, "largestDirectoryBytes": largest_directory,
    }


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("root", type=Path); args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()

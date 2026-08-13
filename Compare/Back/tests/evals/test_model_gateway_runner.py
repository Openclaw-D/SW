from __future__ import annotations

import asyncio
import json
from pathlib import Path

from evals.model_gateway.runner import run_offline_eval
from evals.model_gateway.material_paths import native_material_pack_root


def test_two_phase_offline_release_gate_passes_without_real_provider() -> None:
    report = asyncio.run(run_offline_eval())

    assert report["releaseGatePassed"] is True
    assert report["realProviderCalled"] is False
    assert report["providerCallCount"] == 30
    assert report["advisoryOnly"] is True
    assert report["isSimulated"] is True
    assert report["dataStatus"] == "synthetic_demo"
    assert report["phases"]["sixIndustrySmoke"]["caseCount"] == 6
    assert report["phases"]["twentyFourProjectStandard"]["caseCount"] == 24
    assert report["failureDegradation"]["rate"] == 1.0


def test_native_24_package_baseline_is_complete_and_synthetic() -> None:
    pack_root = native_material_pack_root()
    index = json.loads((pack_root / "package-index.json").read_text(encoding="utf-8"))
    assert index["schemaVersion"] == "compare-native-pack-index-v2"
    assert index["projectCount"] == 24
    assert index["materialCount"] == 1344
    assert index["uniqueSourceHashCount"] == 1344
    assert index["isSimulated"] is True
    assert len(index["packages"]) == 24

    industries: set[str] = set()
    for package in index["packages"]:
        folder = pack_root / package["folder"]
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest["items"]) == 56
        assert package["materialCount"] == 56
        assert sum(package["carrierCounts"].values()) == 56
        assert set(package["carrierCounts"]) == {"excel", "pdf", "image"}
        assert not any(item["material"]["kind"] == "scene" for item in manifest["items"])
        assert not any(
            item["material"]["kind"] == "media"
            and item["material"].get("mediaKind") != "video"
            for item in manifest["items"]
        )
        assert all(item["material"].get("businessPath") for item in manifest["items"])
        assert all(item["classification"] == "synthetic_demo" for item in manifest["items"])
        assert all(item["material"]["isSimulated"] is True for item in manifest["items"])
        assert all((folder / item["sourceFile"]).is_file() for item in manifest["items"])
        industries.add(package["industry"])
    assert len(industries) == 6

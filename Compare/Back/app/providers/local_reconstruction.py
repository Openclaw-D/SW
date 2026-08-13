from __future__ import annotations

"""Fail-closed discovery for optional local photogrammetry engines.

This module intentionally does not turn a detected executable into a successful
job.  A real adapter also needs a project-isolated material staging resolver and
engine-specific quality-output parser; until those are configured, detection is
reported as unavailable rather than producing a schematic asset.
"""

import shutil
from dataclasses import dataclass

from app.contracts.reconstruction import (
    RECONSTRUCTION_DISCLAIMER,
    ReconstructionEngineStatus,
    ReconstructionJobRequest,
    ReconstructionPipeline,
)
from app.services.reconstruction import ProviderReconstructionResult, ReconstructionProviderFailure
from app.contracts.reconstruction import ReconstructionErrorCode


_KNOWN_EXECUTABLES: tuple[tuple[str, str], ...] = (
    ("COLMAP", "colmap"),
    ("Meshroom/AliceVision", "Meshroom"),
    ("Meshroom/AliceVision", "aliceVision_meshroom"),
    ("OpenMVG", "openMVG_main_SfMInit_ImageListing"),
    ("Blender", "blender"),
)


@dataclass(frozen=True, slots=True)
class LocalEngineDiscovery:
    engine: str | None

    @property
    def executable_detected(self) -> bool:
        return self.engine is not None


def discover_local_engine() -> LocalEngineDiscovery:
    """Check only executable names on PATH; no subprocess or network access."""

    for engine, executable in _KNOWN_EXECUTABLES:
        if shutil.which(executable):
            return LocalEngineDiscovery(engine=engine)
    return LocalEngineDiscovery(engine=None)


class UnavailableLocalReconstructionProvider:
    """Default API provider: discover safely, then refuse to fabricate output."""

    def __init__(self, discovery: LocalEngineDiscovery | None = None) -> None:
        self.discovery = discovery or discover_local_engine()

    def supports(self, pipeline: ReconstructionPipeline) -> bool:
        del pipeline
        return False

    def status(self) -> ReconstructionEngineStatus:
        if self.discovery.executable_detected:
            detail = (
                f"检测到 {self.discovery.engine} 可执行文件，但尚未配置项目隔离的"
                "原图 staging、固定参数适配器和输出指标解析；因此拒绝运行。"
            )
            engine = self.discovery.engine or "local_engine"
        else:
            detail = "未在本机 PATH 中发现 COLMAP、Meshroom/AliceVision、OpenMVG 或 Blender。"
            engine = "none_detected"
        return ReconstructionEngineStatus(
            engine=engine,
            available=False,
            supports_multi_view=False,
            detail=detail,
            disclaimer=(
                "发现状态不代表已完成重建；本地默认适配器不联网、不启动 shell，"
                "也不会生成 GLB、点云或网格。"
            ),
        )

    def reconstruct(
        self,
        job_id: str,
        request: ReconstructionJobRequest,
    ) -> ProviderReconstructionResult:
        del job_id, request
        raise ReconstructionProviderFailure(
            ReconstructionErrorCode.PROVIDER_NOT_CONFIGURED,
            self.status().detail,
            retryable=True,
        )


__all__ = [
    "LocalEngineDiscovery",
    "UnavailableLocalReconstructionProvider",
    "discover_local_engine",
]

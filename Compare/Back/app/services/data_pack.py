from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
from typing import Any, Mapping, Sequence
from collections.abc import AsyncIterable
import shutil
import zipfile

from pydantic import TypeAdapter, ValidationError

from app.contracts.data_pack import (
    ControlledImportManifest,
    MaterialImportPreflight,
    MaterialImportPreview,
    MaterialImportResult,
    MaterialUploadReceipt,
    MaterialIntelligenceRunCommand,
    StoredMaterialIntelligence,
    StoredSceneSpec,
)
from app.contracts.errors import BusinessValidationError, ConflictError, NotFoundError, ServiceError, VersionConflictError
from app.contracts.material_intelligence import (
    DataClassification,
    MATERIAL_INTELLIGENCE_DISCLAIMER,
    MaterialIntelligenceDataStatus,
    MaterialIntelligenceRequest,
    MaterialIntelligenceResult,
    MaterialIntelligenceTaskGoal,
    MaterialMediaKind,
)
from app.contracts.model_gateway import ModelGatewayMode, ModelGatewayRequest
from app.contracts.workbench import (
    Material as MaterialContract,
    MaterialOriginalAccess,
)
from app.core.config import Settings
from app.models import EvidenceReference, Material, MaterialVersion, locator_from_mapping, new_id, utc_now
from app.repositories import RepositoryNotFound, RepositoryProjectMismatch, SQLiteStateRepository

from .locators import LocatorService
from .material_intelligence import (
    DeterministicSyntheticMaterialProvider,
    MaterialIntelligenceHarnessConfig,
    MaterialIntelligenceProviderPort,
    calculate_material_intelligence_input_hash,
    execute_material_intelligence,
)
from .native_sources import load_native_source_bindings
from .external_material_root import resolve_external_material_root


_MATERIAL = TypeAdapter(MaterialContract)
_DIMENSION_FACTS = {
    "compliance": "compliance.registration_valid",
    "transaction": "transaction.financing_ratio",
    "production": "production.equipment_utilization",
    "revenue": "revenue.collection_invoice_ratio",
    "debt": "debt.debt_revenue_ratio",
    "cashflow": "cashflow.collection_cash_match",
}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_PROJECT_BYTES = MAX_UPLOAD_BYTES
MAX_COMPRESSION_RATIO = 100
MAX_PROVIDER_INPUT_BYTES = 20 * 1024 * 1024

# The ZIP is only a transport.  Each declared original must be a browser-safe,
# non-executable carrier whose extension agrees with the Front-compatible
# material contract.  This deliberately rejects Office macros, HTML, scripts,
# archives nested inside a pack, and catch-all .bin files.
_ALLOWED_ORIGINALS: dict[str, dict[str, str]] = {
    "excel": {".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "pdf": {".pdf": "application/pdf"},
    "document": {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    "image": {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"},
    # Only an actual MP4 is a media original. Panorama descriptors, SceneSpec
    # JSON and GLB files are derived artifacts and cannot enter raw import.
    "media": {".mp4": "video/mp4"},
}
_PROVIDER_MEDIA_KINDS = {
    "image": MaterialMediaKind.IMAGE,
    "pdf": MaterialMediaKind.PDF,
    "excel": MaterialMediaKind.EXCEL,
    "document": MaterialMediaKind.DOCUMENT,
}
_PROVIDER_MIME_TYPES = {
    "image": frozenset({"image/png", "image/jpeg", "image/webp"}),
    "pdf": frozenset({"application/pdf"}),
    "excel": frozenset(
        {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    ),
    "document": frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ),
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


class DataPackService:
    def __init__(
        self,
        repository: SQLiteStateRepository,
        settings: Settings,
        *,
        providers: Mapping[ModelGatewayMode, MaterialIntelligenceProviderPort] | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.locators = LocatorService(repository)
        self.providers: dict[ModelGatewayMode, MaterialIntelligenceProviderPort] = {
            ModelGatewayMode.SYNTHETIC: DeterministicSyntheticMaterialProvider(),
            **dict(providers or {}),
        }
        self.harness_config = MaterialIntelligenceHarnessConfig(
            enabled=True,
            timeout_seconds=settings.model_gateway_timeout_seconds,
        )

    def ensure_seed_records(self) -> None:
        native_sources = load_native_source_bindings(self.settings.import_root)
        with self.repository.transaction(write=True) as connection:
            rows = connection.execute(
                "SELECT id, project_id, material_id, content_hash FROM material_versions ORDER BY project_id, id"
            ).fetchall()
            for row in rows:
                native = native_sources.get((row["project_id"], row["material_id"]))
                bound = native if native and native.content_hash == row["content_hash"] else None
                connection.execute(
                    """INSERT OR IGNORE INTO material_source_records
                       (material_version_id, project_id, material_id, content_hash,
                        classification, authorization_ref, source_ref, source_file_ref,
                        byte_size, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["id"], row["project_id"], row["material_id"], row["content_hash"],
                        bound.classification if bound else "synthetic_demo",
                        bound.authorization_ref if bound else "compare-p5-synthetic-v1",
                        f"synthetic://{row['project_id']}/{row['material_id']}/{row['content_hash'][:16]}",
                        bound.source_file_ref if bound else None,
                        bound.byte_size if bound else None,
                        utc_now(),
                    ),
                )

    @staticmethod
    def project_current_evidence(
        materials: Sequence[Material],
        evidence: Sequence[EvidenceReference],
    ) -> tuple[EvidenceReference, ...]:
        """Return a current-workbench-safe view without rewriting history.

        Evidence rows and SourceAnchors are immutable audit records. When a
        controlled import advances a material version, a locator validated
        against the old original cannot be copied to the new version. The
        current projection therefore retains the evidence id but removes the
        unverified locator and sends it back through human review.
        """

        current_versions = {
            material.id: material.current_version_id for material in materials
        }
        projected: list[EvidenceReference] = []
        for item in evidence:
            locator = item.locator
            current_version_id = (
                current_versions.get(locator.material_id) if locator else None
            )
            if (
                item.location_status == "located"
                and locator is not None
                and current_version_id is not None
                and locator.material_version_id != current_version_id
            ):
                projected.append(
                    EvidenceReference(
                        id=item.id,
                        project_id=item.project_id,
                        label=item.label,
                        locator=None,
                        location_status="pending",
                        material_status="review",
                        created_at=item.created_at,
                    )
                )
                continue
            projected.append(item)
        return tuple(projected)

    async def upload_zip(
        self, project_id: str, file_name: str, content_length: int | None, stream: AsyncIterable[bytes]
    ) -> MaterialUploadReceipt:
        if not file_name.lower().endswith(".zip"):
            raise BusinessValidationError("upload_type_invalid", "当前仅接受 .zip 材料包。", field="X-File-Name")
        if content_length is not None and content_length > MAX_UPLOAD_BYTES:
            raise BusinessValidationError("upload_too_large", "材料包超过 100 MiB 上限。")
        with self.repository.transaction(write=False) as connection:
            self.repository.get_project(project_id, connection)
        upload_id = new_id("upload")
        upload_root = self.settings.import_root.resolve() / "uploads" / project_id / upload_id
        temp_root = upload_root / ".tmp"
        archive_path = temp_root / "upload.zip"
        digest = hashlib.sha256()
        size = 0
        try:
            temp_root.mkdir(parents=True, exist_ok=False)
            with archive_path.open("xb") as output:
                async for chunk in stream:
                    size += len(chunk)
                    if not isinstance(chunk, bytes):
                        raise BusinessValidationError("upload_stream_invalid", "材料包上传流必须包含二进制数据。")
                    if size > MAX_UPLOAD_BYTES:
                        raise BusinessValidationError("upload_too_large", "材料包超过 100 MiB 上限。")
                    digest.update(chunk)
                    output.write(chunk)
            self._extract_zip(archive_path, upload_root)
            manifests = [path for path in upload_root.rglob("manifest.json") if path.is_file()]
            if len(manifests) != 1:
                raise BusinessValidationError("upload_manifest_invalid", "材料包必须且只能包含一个 manifest.json。")
            manifest_ref = manifests[0].relative_to(self.settings.import_root.resolve()).as_posix()
            return MaterialUploadReceipt(project_id=project_id, upload_id=upload_id, file_name=Path(file_name).name, byte_size=size, sha256=digest.hexdigest(), manifest_ref=manifest_ref)
        except (zipfile.BadZipFile, OSError) as exc:
            shutil.rmtree(upload_root, ignore_errors=True)
            raise BusinessValidationError("upload_zip_invalid", "材料包不是可安全解压的 ZIP 文件。") from exc
        except Exception:
            shutil.rmtree(upload_root, ignore_errors=True)
            raise

    def _extract_zip(self, archive_path: Path, upload_root: Path) -> None:
        total = 0
        seen: set[str] = set()
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                clean_name = name.rstrip("/")
                parts = clean_name.split("/")
                if not clean_name or name.startswith("/") or ":" in clean_name or any(part in {"", ".", ".."} for part in parts):
                    raise BusinessValidationError("upload_zip_unsafe", "ZIP 包含不安全路径。")
                mode = info.external_attr >> 16
                file_type = mode & 0o170000
                is_link_or_special = bool(file_type) and file_type not in {0o100000, 0o040000}
                if clean_name in seen or is_link_or_special:
                    raise BusinessValidationError("upload_zip_unsafe", "ZIP 包含重复条目或链接。")
                seen.add(clean_name)
                if info.is_dir():
                    continue
                if info.file_size > MAX_UPLOAD_BYTES:
                    raise BusinessValidationError("upload_original_too_large", "单个原件超过 100 MiB 上限。")
                # Bound the expansion factor as well as the final project size.
                if info.file_size and info.file_size > max(1, info.compress_size) * MAX_COMPRESSION_RATIO:
                    raise BusinessValidationError("upload_zip_bomb", "ZIP 压缩比异常，疑似解压炸弹。")
                if total + info.file_size > MAX_PROJECT_BYTES:
                    raise BusinessValidationError("upload_project_too_large", "材料包解压后的项目总量超过 100 MiB 上限。")
                total += info.file_size
                target = (upload_root / clean_name).resolve()
                if upload_root.resolve() not in target.parents:
                    raise BusinessValidationError("upload_zip_unsafe", "ZIP 包含不安全路径。")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        # Only remove the temporary archive itself.  `upload_root` also holds
        # extracted originals, and callers/tests may place the archive beside
        # other authorized inputs.
        archive_path.unlink(missing_ok=True)
        try:
            archive_path.parent.rmdir()
        except OSError:
            pass

    def preflight_manifest(self, project_id: str, manifest_ref: str) -> tuple[MaterialImportPreflight, ControlledImportManifest]:
        manifest_path = self._authorized_path(manifest_ref)
        try:
            raw = self._read_file_limited(manifest_path)
            manifest = ControlledImportManifest.model_validate_json(raw)
        except FileNotFoundError as exc:
            raise NotFoundError("import_manifest_not_found", "授权导入 manifest 不存在。") from exc
        except (ValidationError, ValueError) as exc:
            raise BusinessValidationError("import_manifest_invalid", "授权导入 manifest 未通过严格校验。") from exc
        if manifest.project_id != project_id:
            raise BusinessValidationError("path_body_mismatch", "manifest projectId 必须与路径一致。")
        manifest_hash = hashlib.sha256(raw).hexdigest()
        items: list[MaterialImportPreview] = []
        with self.repository.transaction(write=False) as connection:
            self.repository.get_project(project_id, connection)
            snapshot = self.repository.latest_project_snapshot(project_id, connection)
            if snapshot is None:
                raise ConflictError("project_snapshot_missing", "项目没有可用版本。")
            for item in manifest.items:
                owner = connection.execute(
                    "SELECT project_id FROM materials WHERE id = ?", (item.material_id,)
                ).fetchone()
                if owner is not None and owner["project_id"] != project_id:
                    raise NotFoundError(
                        "material_not_found", "材料不存在或不属于当前项目。"
                    )
                source = self._source_path(manifest_ref, item.source_file)
                declared_business_path = item.material.get("businessPath")
                if declared_business_path is not None:
                    normalized_source = item.source_file.replace("\\", "/")
                    normalized_business = str(declared_business_path).replace("\\", "/")
                    if not (
                        normalized_source == normalized_business
                        or normalized_source.endswith("/" + normalized_business)
                    ):
                        raise BusinessValidationError(
                            "import_business_path_mismatch",
                            "sourceFile 必须保持 material.businessPath 的业务目录层级。",
                            field="sourceFile",
                        )
                self._validate_source_carrier(item.material, source)
                try:
                    content_hash, _byte_size = self._hash_file_limited(source)
                except FileNotFoundError as exc:
                    raise BusinessValidationError("import_source_missing", "manifest 引用的授权材料不存在。") from exc
                if content_hash != item.sha256:
                    raise ConflictError("import_hash_mismatch", "授权材料 SHA-256 与 manifest 不一致。")
                payload = dict(item.material)
                payload["id"] = item.material_id
                existing_version = connection.execute(
                    "SELECT id FROM material_versions WHERE project_id = ? AND material_id = ? AND content_hash = ?",
                    (project_id, item.material_id, content_hash),
                ).fetchone()
                next_version = self._next_material_version(item.material_id, connection)
                version_id = existing_version["id"] if existing_version else f"{item.material_id}-v{next_version}"
                payload["versionId"] = version_id
                try:
                    material = _MATERIAL.validate_python(payload)
                except ValidationError as exc:
                    raise BusinessValidationError("import_material_invalid", "manifest material 未通过 Front 兼容契约。") from exc
                source_ref = "source-ref:" + _hash({"manifest": manifest_hash, "authorization": item.authorization_ref, "source": item.source_file})[:24]
                items.append(MaterialImportPreview(
                    material_id=item.material_id,
                    material_version_id=version_id,
                    kind=material.kind,
                    content_hash=content_hash,
                    classification=item.classification,
                    authorization_ref=item.authorization_ref,
                    source_ref=source_ref,
                    folder_path=material.folder_path,
                    business_path=material.business_path,
                ))
        return MaterialImportPreflight(
            project_id=project_id,
            manifest_ref=manifest_ref,
            manifest_hash=manifest_hash,
            project_version=snapshot.version,
            items=items,
            is_simulated=all(item.classification == DataClassification.SYNTHETIC_DEMO for item in manifest.items),
        ), manifest

    def execute_import(
        self,
        connection: sqlite3.Connection,
        preflight: MaterialImportPreflight,
        manifest: ControlledImportManifest,
        *,
        expected_version: int,
    ) -> MaterialImportResult:
        snapshot = self.repository.latest_project_snapshot(preflight.project_id, connection)
        if snapshot is None or snapshot.version != expected_version:
            raise VersionConflictError(expected_version=expected_version, actual_version=snapshot.version if snapshot else 0)
        now = utc_now()
        preview_by_id = {item.material_id: item for item in preflight.items}
        for item in manifest.items:
            preview = preview_by_id[item.material_id]
            payload = dict(item.material)
            payload["id"] = item.material_id
            payload["versionId"] = preview.material_version_id
            contract = _MATERIAL.validate_python(payload)
            existing = connection.execute("SELECT id FROM materials WHERE id = ?", (item.material_id,)).fetchone()
            if existing is None:
                self.repository.create_material(Material(
                    id=item.material_id, project_id=preflight.project_id, kind=contract.kind,
                    file_name=contract.file_name, availability=contract.availability,
                    current_version_id=None,
                    metadata={
                        "label": contract.label,
                        "sourceLabel": contract.source_label,
                        "isSimulated": contract.is_simulated,
                        "folderPath": contract.folder_path,
                        "businessPath": contract.business_path,
                    },
                    created_at=now,
                ), connection)
            else:
                owner = connection.execute(
                    "SELECT project_id FROM materials WHERE id = ?", (item.material_id,)
                ).fetchone()
                if owner["project_id"] != preflight.project_id:
                    raise NotFoundError(
                        "material_not_found", "材料不存在或不属于当前项目。"
                    )
            version_exists = connection.execute(
                "SELECT id FROM material_versions WHERE id = ? AND project_id = ?",
                (preview.material_version_id, preflight.project_id),
            ).fetchone()
            if version_exists is None:
                version_number = int(preview.material_version_id.rsplit("-v", 1)[1])
                self.repository.create_material_version(MaterialVersion(
                    id=preview.material_version_id, project_id=preflight.project_id,
                    material_id=item.material_id, version=version_number,
                    mime_type=contract.mime_type, content_hash=preview.content_hash,
                    payload=contract.model_dump(by_alias=True, mode="json"), created_at=now,
                    created_by="controlled-import",
                ), connection)
            self.repository.set_current_material_version(preflight.project_id, item.material_id, preview.material_version_id, connection)
            if version_exists is None:
                connection.execute(
                    """INSERT INTO material_source_records
                       (material_version_id, project_id, material_id, content_hash,
                        classification, authorization_ref, source_ref, source_file_ref, byte_size, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (preview.material_version_id, preflight.project_id, item.material_id,
                     preview.content_hash, preview.classification.value,
                     preview.authorization_ref, preview.source_ref, self._source_ref(preflight.manifest_ref, item.source_file),
                     self._hash_file_limited(self._source_path(preflight.manifest_ref, item.source_file))[1], now),
                )
        import_id = new_id("material-import")
        connection.execute(
            "INSERT INTO material_imports(id, project_id, manifest_ref, manifest_hash, item_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (import_id, preflight.project_id, preflight.manifest_ref, preflight.manifest_hash, len(preflight.items), now),
        )
        return MaterialImportResult(
            **preflight.model_dump(), import_id=import_id,
            imported_count=len(preflight.items), replayed=False,
        )

    def prepare_intelligence(
        self,
        project_id: str,
        material_id: str,
        command: MaterialIntelligenceRunCommand,
    ) -> tuple[StoredMaterialIntelligence, dict[str, Any]]:
        with self.repository.transaction(write=False) as connection:
            material = self.repository.get_material(project_id, material_id, connection)
            version = self.repository.get_material_version(project_id, command.material_version_id, connection)
            if version.material_id != material.id:
                raise NotFoundError("material_version_not_found", "材料版本不存在或不属于当前材料。")
            if version.version != command.expected_version or material.current_version_id != version.id:
                actual = self.repository.get_material_version(project_id, material.current_version_id, connection).version if material.current_version_id else 0
                raise VersionConflictError(expected_version=command.expected_version, actual_version=actual)
            provider_mode = self._provider_mode(command)
            provider = self.providers.get(provider_mode)
            if provider_mode == ModelGatewayMode.REAL and provider is None:
                raise BusinessValidationError(
                    "model_gateway_provider_not_configured",
                    "显式请求的 real Model Gateway provider 尚未完成公共接线。",
                    field="providerMode",
                )
            source = self._source_record(
                connection,
                project_id=project_id,
                material_id=material_id,
                material_version_id=version.id,
                require_original=provider_mode == ModelGatewayMode.REAL,
            )
            fact_key, dimension_id, label = self._candidate_schema(project_id, material_id, connection)
            context = self._provider_context(
                version.payload,
                fact_key,
                dimension_id,
                label,
                provider_mode,
            )
            if provider_mode == ModelGatewayMode.REAL:
                context["providerInput"] = self._assemble_provider_input(
                    project_id=project_id,
                    material=material,
                    version=version,
                    source=source,
                )
            media_kind = self._media_kind(version.payload["kind"])
            request = MaterialIntelligenceRequest(
                project_id=project_id, material_id=material_id,
                material_version_id=version.id, content_hash=version.content_hash,
                media_kind=media_kind, context_version=command.context_version,
                task_goals=command.task_goals,
                data_classification=source["classification"],
                usage_authorization_ref=source["authorization_ref"],
            )
        provider = self.providers.get(provider_mode)
        if provider_mode == ModelGatewayMode.DISABLED:
            result = self._unavailable_result(request, context)
        else:
            assert provider is not None
            result = asyncio.run(execute_material_intelligence(
                request, context, provider, self.harness_config
            ))
            expected_truth = {
                ModelGatewayMode.SYNTHETIC: (
                    True,
                    MaterialIntelligenceDataStatus.SIMULATED,
                ),
                ModelGatewayMode.REAL: (
                    False,
                    MaterialIntelligenceDataStatus.PROVIDER_GENERATED_UNVERIFIED,
                ),
            }[provider_mode]
            if (result.is_simulated, result.data_status) != expected_truth:
                raise ServiceError(
                    code="model_gateway_mode_mismatch",
                    message="provider 输出未如实匹配显式 Model Gateway mode。",
                    category="internal",
                    status_code=502,
                )
        created_at = utc_now()
        run_id = f"mi-run-{result.input_hash[:24]}"
        candidate_ids = [item.id for item in result.extracted_field_candidates]
        evidence_refs = [f"ev-mi-{anchor.id}" for anchor in result.source_anchors]
        return StoredMaterialIntelligence(
            run_id=run_id, result=result, candidate_ids=candidate_ids,
            evidence_refs=evidence_refs, created_at=created_at,
        ), context

    def assemble_model_gateway_provider_input(
        self,
        request: ModelGatewayRequest,
    ) -> dict[str, str]:
        """Build the existing OpenAI providerInput shape for an explicit real run.

        The returned Base64 exists only in caller memory. This method performs no
        persistence, logging or provider call and is the injection point for the
        separate Model Gateway router/orchestrator task.
        """

        if request.mode != ModelGatewayMode.REAL:
            raise BusinessValidationError(
                "provider_input_real_only",
                "providerInput 只允许由显式 real 请求装配。",
                field="mode",
            )
        if self.settings.model_gateway_mode != ModelGatewayMode.REAL:
            raise BusinessValidationError(
                "model_gateway_real_not_enabled",
                "real Model Gateway 未由当前环境显式启用。",
                field="mode",
            )
        material_input = request.material
        with self.repository.transaction(write=False) as connection:
            try:
                material = self.repository.get_material(
                    material_input.project_id,
                    material_input.material_id,
                    connection,
                )
                version = self.repository.get_material_version(
                    material_input.project_id,
                    material_input.material_version_id,
                    connection,
                )
            except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                raise NotFoundError(
                    "material_not_found",
                    "材料或材料版本不存在，或不属于当前项目。",
                ) from exc
            if version.material_id != material.id:
                raise NotFoundError(
                    "material_version_not_found",
                    "材料版本不存在或不属于当前材料。",
                )
            if material.current_version_id != version.id:
                actual = (
                    self.repository.get_material_version(
                        material_input.project_id,
                        material.current_version_id,
                        connection,
                    ).version
                    if material.current_version_id
                    else 0
                )
                raise VersionConflictError(
                    expected_version=version.version,
                    actual_version=actual,
                )
            expected_media_kind = self._provider_media_kind(version.payload["kind"])
            if (
                material_input.content_hash != version.content_hash
                or request.input_hash != version.content_hash
                or material_input.media_kind != expected_media_kind
            ):
                raise BusinessValidationError(
                    "provider_input_binding_mismatch",
                    "providerInput 请求未绑定当前材料版本的 hash/kind。",
                    field="material",
                )
            source = self._source_record(
                connection,
                project_id=material_input.project_id,
                material_id=material_input.material_id,
                material_version_id=version.id,
                require_original=True,
            )
            if (
                material_input.source_ref != source["source_ref"]
                or material_input.data_classification.value != source["classification"]
                or material_input.usage_authorization_ref != source["authorization_ref"]
            ):
                raise BusinessValidationError(
                    "provider_input_source_mismatch",
                    "providerInput 请求未绑定服务端授权来源记录。",
                    field="material.sourceRef",
                )
            return self._assemble_provider_input(
                project_id=material_input.project_id,
                material=material,
                version=version,
                source=source,
            )

    def persist_intelligence(
        self,
        connection: sqlite3.Connection,
        stored: StoredMaterialIntelligence,
        context: Mapping[str, Any],
    ) -> StoredMaterialIntelligence:
        result = stored.result
        previous = connection.execute(
            "SELECT result_json, created_at, id FROM material_intelligence_runs WHERE project_id = ? AND material_version_id = ? AND input_hash = ?",
            (result.project_id, result.material_version_id, result.input_hash),
        ).fetchone()
        if previous is not None:
            return StoredMaterialIntelligence(
                run_id=previous["id"], result=type(result).model_validate_json(previous["result_json"]),
                candidate_ids=stored.candidate_ids, evidence_refs=stored.evidence_refs,
                created_at=previous["created_at"],
            )
        connection.execute(
            """INSERT INTO material_intelligence_runs
               (id, project_id, material_id, material_version_id, input_hash, status,
                provider, model, result_json, is_simulated, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (stored.run_id, result.project_id, result.material_id, result.material_version_id,
             result.input_hash, result.status.value, result.model_info.provider if result.model_info else None,
             result.model_info.model if result.model_info else None,
             result.model_dump_json(by_alias=True), int(result.is_simulated), stored.created_at),
        )
        anchor_to_evidence: dict[str, str] = {}
        for anchor in result.source_anchors:
            payload = anchor.model_dump(by_alias=True, mode="json")
            connection.execute(
                "INSERT INTO source_anchors(id, project_id, material_id, material_version_id, intelligence_run_id, kind, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (anchor.id, result.project_id, result.material_id, result.material_version_id,
                 stored.run_id, anchor.kind, _json(payload), stored.created_at),
            )
            evidence_id = f"ev-mi-{anchor.id}"
            locator_payload = self._anchor_locator(payload)
            evidence = EvidenceReference(
                id=evidence_id, project_id=result.project_id,
                label=f"材料智能锚点 {anchor.id}", locator=locator_from_mapping(locator_payload),
                location_status="located", material_status="review", created_at=stored.created_at,
            )
            self.locators.validate_reference(result.project_id, evidence, connection)
            self.repository.create_evidence_reference(evidence, connection)
            anchor_to_evidence[anchor.id] = evidence_id
        for candidate in result.extracted_field_candidates:
            connection.execute(
                """INSERT INTO extracted_fact_candidates
                   (id, project_id, material_id, material_version_id, intelligence_run_id,
                    field_key, dimension_id, label, value_json, unit, candidate_status,
                    source_anchor_ids_json, evidence_refs_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (candidate.id, result.project_id, result.material_id, result.material_version_id,
                 stored.run_id, candidate.field_key, context["dimensionId"], candidate.label,
                 _json(candidate.value), candidate.unit, candidate.status.value,
                 _json(candidate.source_anchor_ids),
                 _json([anchor_to_evidence[item] for item in candidate.source_anchor_ids]),
                 stored.created_at),
            )
        if result.scene_spec is not None:
            connection.execute(
                """INSERT INTO scene_specs
                   (id, project_id, material_id, material_version_id, intelligence_run_id,
                    source_anchor_ids_json, spec_json, is_simulated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"scene-{result.input_hash[:24]}", result.project_id, result.material_id,
                 result.material_version_id, stored.run_id,
                 _json([anchor.id for anchor in result.source_anchors]),
                 result.scene_spec.model_dump_json(by_alias=True), int(result.is_simulated), stored.created_at),
            )
        return stored

    def latest_intelligence(self, project_id: str, material_id: str) -> StoredMaterialIntelligence:
        with self.repository.transaction(write=False) as connection:
            try:
                self.repository.get_material(project_id, material_id, connection)
            except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                raise NotFoundError("material_not_found", "材料不存在或不属于当前项目。") from exc
            row = connection.execute(
                "SELECT * FROM material_intelligence_runs WHERE project_id = ? AND material_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (project_id, material_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("material_intelligence_not_found", "材料尚无 intelligence 结果。")
            candidates = connection.execute("SELECT id FROM extracted_fact_candidates WHERE intelligence_run_id = ? ORDER BY id", (row["id"],)).fetchall()
            anchors = connection.execute("SELECT id FROM source_anchors WHERE intelligence_run_id = ? ORDER BY id", (row["id"],)).fetchall()
            from app.contracts.material_intelligence import MaterialIntelligenceResult
            return StoredMaterialIntelligence(
                run_id=row["id"], result=MaterialIntelligenceResult.model_validate_json(row["result_json"]),
                candidate_ids=[item["id"] for item in candidates],
                evidence_refs=[f"ev-mi-{item['id']}" for item in anchors], created_at=row["created_at"],
            )

    def latest_scene(self, project_id: str, material_id: str) -> StoredSceneSpec:
        with self.repository.transaction(write=False) as connection:
            try:
                self.repository.get_material(project_id, material_id, connection)
            except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                raise NotFoundError("material_not_found", "材料不存在或不属于当前项目。") from exc
            row = connection.execute(
                "SELECT * FROM scene_specs WHERE project_id = ? AND material_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (project_id, material_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("scene_spec_not_found", "材料尚无受控 SceneSpec。")
            from app.contracts.material_intelligence import SceneSpec
            return StoredSceneSpec(
                scene_id=row["id"], project_id=row["project_id"], material_id=row["material_id"],
                material_version_id=row["material_version_id"],
                source_anchor_ids=json.loads(row["source_anchor_ids_json"]),
                spec=SceneSpec.model_validate_json(row["spec_json"]),
                is_simulated=bool(row["is_simulated"]), created_at=row["created_at"],
            )

    def _authorized_path(self, relative_ref: str) -> Path:
        root = self.settings.import_root.resolve()
        target = (root / relative_ref).resolve()
        if target != root and root not in target.parents:
            raise BusinessValidationError("import_path_invalid", "导入引用超出授权目录。")
        return target

    def _source_path(self, manifest_ref: str, source_ref: str) -> Path:
        manifest_parent = self._authorized_path(Path(manifest_ref).parent.as_posix())
        target = self._authorized_path((Path(manifest_ref).parent / source_ref).as_posix())
        if target == manifest_parent or manifest_parent not in target.parents:
            raise BusinessValidationError("import_path_invalid", "材料引用必须位于 manifest 所在目录。")
        return target

    def _source_ref(self, manifest_ref: str, source_ref: str) -> str:
        return self._source_path(manifest_ref, source_ref).relative_to(
            self.settings.import_root.resolve()
        ).as_posix()

    @staticmethod
    def _validate_source_carrier(material_payload: Mapping[str, Any], source: Path) -> None:
        """Fail preflight before hashing an unsupported or mismatched original."""
        kind = material_payload.get("kind")
        mime_type = material_payload.get("mimeType")
        allowed = _ALLOWED_ORIGINALS.get(kind)
        expected_mime = allowed.get(source.suffix.lower()) if allowed else None
        if expected_mime is None:
            raise BusinessValidationError(
                "import_source_type_invalid",
                "授权原件类型不在受控白名单内。",
                field="sourceFile",
            )
        if mime_type != expected_mime:
            raise BusinessValidationError(
                "import_source_type_mismatch",
                "原件扩展名与材料 MIME 类型不一致。",
                field="sourceFile",
            )
        if kind == "media" and material_payload.get("mediaKind") != "video":
            raise BusinessValidationError(
                "import_source_type_invalid",
                "media 原件只允许真实 MP4 视频；全景描述符属于派生产物。",
                field="material.mediaKind",
            )

    @staticmethod
    def _read_file_limited(path: Path) -> bytes:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise BusinessValidationError("import_source_too_large", "授权导入文件超过 100 MiB 上限。")
        return path.read_bytes()

    @staticmethod
    def _hash_file_limited(path: Path) -> tuple[str, int]:
        if not path.is_file():
            raise FileNotFoundError(path)
        digest, total = hashlib.sha256(), 0
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise BusinessValidationError("import_source_too_large", "授权导入文件超过 100 MiB 上限。")
                digest.update(chunk)
        return digest.hexdigest(), total

    def material_original(self, project_id: str, material_id: str) -> tuple[Path, str, str]:
        with self.repository.transaction(write=False) as connection:
            try:
                material = self.repository.get_material(project_id, material_id, connection)
            except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                raise NotFoundError("material_not_found", "材料不存在或不属于当前项目。") from exc
            if not material.current_version_id:
                raise NotFoundError("material_original_not_found", "材料没有可读取的原件。")
            version = self.repository.get_material_version(project_id, material.current_version_id, connection)
            path = self._external_original_path(project_id, material_id, version.content_hash)
            return path, version.mime_type, material.file_name

    def material_original_access(
        self, project_id: str, material_id: str, content_hash: str
    ) -> MaterialOriginalAccess:
        """Return a safe availability projection without exposing archive paths."""
        root = resolve_external_material_root(self.settings)
        if root.status != "available":
            return MaterialOriginalAccess(status=root.status, available=False)
        try:
            self._external_original_path(project_id, material_id, content_hash)
        except NotFoundError:
            return MaterialOriginalAccess(status="not_imported", available=False)
        except ConflictError:
            return MaterialOriginalAccess(status="integrity_mismatch", available=False)
        except ServiceError:
            return MaterialOriginalAccess(status="invalid_root", available=False)
        return MaterialOriginalAccess(status="available", available=True)

    def _external_original_path(
        self, project_id: str, material_id: str, content_hash: str
    ) -> Path:
        root = resolve_external_material_root(self.settings)
        if root.status == "not_configured":
            raise ServiceError(
                code="material_root_not_configured",
                message="外置材料根目录尚未配置，原件未导入当前运行时。",
                category="internal",
                status_code=503,
            )
        if root.status != "available" or root.pack_root is None:
            raise ServiceError(
                code="material_root_invalid",
                message="外置材料根目录不可用，原件未导入当前运行时。",
                category="internal",
                status_code=503,
            )
        try:
            binding = load_native_source_bindings(root.pack_root).get(
                (project_id, material_id)
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise ServiceError(
                code="material_root_invalid",
                message="外置材料根目录不可用，原件未导入当前运行时。",
                category="internal",
                status_code=503,
            ) from exc
        if binding is None:
            raise NotFoundError(
                "material_original_not_imported",
                "该材料尚未导入外置材料根目录。",
            )
        if binding.content_hash != content_hash:
            raise ConflictError(
                "material_original_integrity_mismatch",
                "外置材料与当前材料版本的 SHA-256 不一致。",
            )
        target = (root.pack_root / binding.source_file_ref).resolve()
        if root.pack_root not in target.parents or not target.is_file():
            raise NotFoundError(
                "material_original_not_imported",
                "该材料尚未导入外置材料根目录。",
            )
        digest, _byte_size = self._hash_file_limited(target)
        if digest != content_hash:
            raise ConflictError(
                "material_original_integrity_mismatch",
                "外置材料与当前材料版本的 SHA-256 不一致。",
            )
        return target

    @staticmethod
    def _next_material_version(material_id: str, connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT COALESCE(MAX(version), 0) + 1 AS value FROM material_versions WHERE material_id = ?", (material_id,)).fetchone()
        return int(row["value"])

    @staticmethod
    def _media_kind(kind: str) -> MaterialMediaKind:
        mapping = {
            "excel": MaterialMediaKind.EXCEL,
            "pdf": MaterialMediaKind.PDF,
            "document": MaterialMediaKind.DOCUMENT,
            "image": MaterialMediaKind.IMAGE,
            "media": MaterialMediaKind.MEDIA,
        }
        if kind not in mapping:
            raise BusinessValidationError("material_intelligence_kind_unsupported", "Scene 载体只读，不作为模型输入。")
        return mapping[kind]

    @staticmethod
    def _provider_media_kind(kind: str) -> MaterialMediaKind:
        media_kind = _PROVIDER_MEDIA_KINDS.get(kind)
        if media_kind is None:
            raise BusinessValidationError(
                "provider_input_kind_unsupported",
                "当前原件类型不支持 real providerInput。",
                field="material.mediaKind",
            )
        return media_kind

    @staticmethod
    def _source_record(
        connection: sqlite3.Connection,
        *,
        project_id: str,
        material_id: str,
        material_version_id: str,
        require_original: bool = False,
    ) -> sqlite3.Row:
        source = connection.execute(
            """SELECT * FROM material_source_records
               WHERE material_version_id = ? AND project_id = ? AND material_id = ?""",
            (material_version_id, project_id, material_id),
        ).fetchone()
        if source is None:
            raise ConflictError(
                "material_source_missing",
                "当前材料版本缺少项目隔离的授权来源记录。",
            )
        if require_original and (
            not source["authorization_ref"]
            or source["authorization_ref"] != source["authorization_ref"].strip()
            or not source["source_ref"]
            or source["source_ref"] != source["source_ref"].strip()
            or not source["source_file_ref"]
        ):
            raise BusinessValidationError(
                "material_source_unauthorized",
                "当前材料版本没有可供 real provider 使用的完整授权来源。",
            )
        return source

    def _assemble_provider_input(
        self,
        *,
        project_id: str,
        material: Material,
        version: MaterialVersion,
        source: Mapping[str, Any],
    ) -> dict[str, str]:
        kind = str(version.payload.get("kind", ""))
        self._provider_media_kind(kind)
        allowed_mime_types = _PROVIDER_MIME_TYPES[kind]
        if version.mime_type not in allowed_mime_types:
            raise BusinessValidationError(
                "provider_input_mime_unsupported",
                "当前原件 MIME 类型不支持 real providerInput。",
                field="material.mimeType",
            )
        if (
            source["project_id"] != project_id
            or source["material_id"] != material.id
            or source["material_version_id"] != version.id
            or source["content_hash"] != version.content_hash
        ):
            raise BusinessValidationError(
                "material_source_binding_mismatch",
                "授权来源未绑定当前 project/material/version/hash。",
            )
        path = self._provider_source_path(
            project_id=project_id,
            material_id=material.id,
            version=version,
            source=source,
        )
        self._validate_source_carrier(version.payload, path)
        try:
            byte_size = path.stat().st_size
        except OSError as exc:
            raise NotFoundError(
                "material_original_not_found",
                "当前材料版本的授权原件不可用。",
            ) from exc
        if byte_size > MAX_PROVIDER_INPUT_BYTES:
            raise BusinessValidationError(
                "provider_input_too_large",
                "当前原件超过 real providerInput 的 20 MiB 内存装配上限。",
            )
        try:
            with path.open("rb") as original:
                content = original.read(MAX_PROVIDER_INPUT_BYTES + 1)
        except OSError as exc:
            raise NotFoundError(
                "material_original_not_found",
                "当前材料版本的授权原件不可用。",
            ) from exc
        if len(content) > MAX_PROVIDER_INPUT_BYTES:
            raise BusinessValidationError(
                "provider_input_too_large",
                "当前原件超过 real providerInput 的 20 MiB 内存装配上限。",
            )
        digest = hashlib.sha256(content).hexdigest()
        recorded_size = source["byte_size"]
        if (
            digest != version.content_hash
            or digest != source["content_hash"]
            or (recorded_size is not None and int(recorded_size) != len(content))
        ):
            raise BusinessValidationError(
                "provider_input_hash_mismatch",
                "授权原件未通过当前 material version 的 hash/size 校验。",
            )
        filename = self._safe_provider_filename(material.file_name)
        return {
            "filename": filename,
            "mimeType": version.mime_type,
            "fileDataBase64": base64.b64encode(content).decode("ascii"),
        }

    def _provider_source_path(
        self,
        *,
        project_id: str,
        material_id: str,
        version: MaterialVersion,
        source: Mapping[str, Any],
    ) -> Path:
        raw_ref = str(source["source_file_ref"])
        normalized = raw_ref.replace("\\", "/")
        relative = PurePosixPath(normalized)
        if (
            relative.is_absolute()
            or ":" in normalized
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise BusinessValidationError(
                "provider_input_path_invalid",
                "授权原件必须使用 import root 内的安全相对路径。",
            )
        parts = relative.parts
        if parts and parts[0] == "uploads":
            if len(parts) < 3 or parts[1] != project_id:
                raise BusinessValidationError(
                    "provider_input_project_path_mismatch",
                    "上传原件路径未绑定当前项目隔离目录。",
                )
        else:
            native = load_native_source_bindings(self.settings.import_root).get(
                (project_id, material_id)
            )
            if native is None:
                raise BusinessValidationError(
                    "provider_input_project_path_mismatch",
                    "native 原件路径未绑定当前项目 manifest。",
                )
            native_binding = (
                native.source_file_ref == normalized
                and native.content_hash == version.content_hash
                and native.classification == source["classification"]
                and native.authorization_ref == source["authorization_ref"]
            )
            if not native_binding:
                raise BusinessValidationError(
                    "material_source_binding_mismatch",
                    "native manifest 与当前材料来源记录不一致。",
                )
        path = self._authorized_path(normalized)
        if not path.is_file():
            raise NotFoundError(
                "material_original_not_found",
                "当前材料版本的授权原件不可用。",
            )
        return path

    @staticmethod
    def _safe_provider_filename(value: str) -> str:
        if (
            not value
            or value != value.strip()
            or "/" in value
            or "\\" in value
            or Path(value).name != value
        ):
            raise BusinessValidationError(
                "provider_input_filename_invalid",
                "providerInput filename 必须是不含路径的安全文件名。",
            )
        return value

    def _candidate_schema(
        self,
        project_id: str,
        material_id: str,
        connection: sqlite3.Connection,
    ) -> tuple[str, str, str]:
        dimension = next((item for item in _DIMENSION_FACTS if f"-{item}-" in material_id), "compliance")
        fact_key = _DIMENSION_FACTS[dimension]
        fact = self.repository.latest_fact_version(project_id, fact_key, connection)
        if fact is None:
            bare_key = fact_key.split(".", 1)[1]
            fact = self.repository.latest_fact_version(project_id, bare_key, connection)
            if fact is not None:
                fact_key = bare_key
        if fact is None:
            row = connection.execute("SELECT * FROM fact_versions WHERE project_id = ? ORDER BY version DESC LIMIT 1", (project_id,)).fetchone()
            if row is None:
                raise ConflictError("fact_context_missing", "项目没有可供候选绑定的 FactVersion。")
            fact_key = row["fact_key"]
            dimension = row["dimension_id"]
            return fact_key, dimension, row["label"]
        return fact.fact_key, fact.dimension_id, fact.label

    @staticmethod
    def _provider_context(
        payload: Mapping[str, Any],
        fact_key: str,
        dimension_id: str,
        label: str,
        provider_mode: ModelGatewayMode,
    ) -> dict[str, Any]:
        # Only extraction schema and non-authoritative material/project context cross
        # the provider boundary. Existing FactVersion value/unit are deliberately absent.
        result = {
            "fieldKey": fact_key,
            "dimensionId": dimension_id,
            "label": label,
            "valueType": "unknown",
            "materialPayloadHash": _hash(payload),
            "providerMode": provider_mode.value,
        }
        if payload.get("kind") == "excel" and payload.get("sheets"):
            sheet = payload["sheets"][0]
            result["sheet"] = sheet["name"]
            result["range"] = f"A4:{chr(64 + min(len(sheet['columns']), 26))}4"
        return result

    def _provider_mode(self, command: MaterialIntelligenceRunCommand) -> ModelGatewayMode:
        configured = self.settings.model_gateway_mode
        # Startup seed is not an explicit user action. In real/disabled deployments it
        # records an unavailable advisory run and never crosses a provider boundary.
        if command.context_version == "p5-seed-v1" and configured != ModelGatewayMode.SYNTHETIC:
            return ModelGatewayMode.DISABLED
        requested = command.provider_mode
        if requested == ModelGatewayMode.REAL:
            if configured != ModelGatewayMode.REAL:
                raise BusinessValidationError(
                    "model_gateway_real_not_enabled",
                    "real Model Gateway 未由当前环境显式启用。",
                    field="providerMode",
                )
            return ModelGatewayMode.REAL
        if configured == ModelGatewayMode.DISABLED:
            return ModelGatewayMode.DISABLED
        if requested == ModelGatewayMode.DISABLED:
            return ModelGatewayMode.DISABLED
        # A configured real provider is never the implicit default. Omitting
        # providerMode retains the local synthetic path until an explicit action asks for real.
        return ModelGatewayMode.SYNTHETIC

    @staticmethod
    def _unavailable_result(
        request: MaterialIntelligenceRequest,
        context: Mapping[str, Any],
    ) -> MaterialIntelligenceResult:
        return MaterialIntelligenceResult(
            project_id=request.project_id,
            material_id=request.material_id,
            material_version_id=request.material_version_id,
            content_hash=request.content_hash,
            media_kind=request.media_kind,
            context_version=request.context_version,
            data_classification=request.data_classification,
            status="unavailable",
            confidence=0,
            observations=[],
            extracted_field_candidates=[],
            unresolved_items=[],
            source_anchors=[],
            scene_spec=None,
            model_info=None,
            prompt_version="model-gateway-disabled-v1",
            input_hash=calculate_material_intelligence_input_hash(request, context),
            advisory_only=True,
            is_simulated=False,
            data_status=MaterialIntelligenceDataStatus.UNAVAILABLE,
            source="model_gateway_startup_guard",
            disclaimer=MATERIAL_INTELLIGENCE_DISCLAIMER,
        )

    @staticmethod
    def _anchor_locator(anchor: Mapping[str, Any]) -> dict[str, Any]:
        base = {"kind": anchor["kind"], "materialId": anchor["materialId"], "materialVersionId": anchor["materialVersionId"]}
        if anchor["kind"] == "excel":
            return {**base, "sheet": anchor["sheet"], "range": anchor["range"]}
        if anchor["kind"] in {"pdf", "image"}:
            result = {**base, "bbox": anchor["bbox"]}
            if anchor["kind"] == "pdf":
                result["page"] = anchor["page"]
            return result
        if anchor["kind"] == "document":
            return {
                **base,
                "paragraphId": anchor["paragraphId"],
                "runId": anchor["runId"],
                "renderedPage": anchor["renderedPage"],
                "renderedPageBbox": anchor["renderedPageBbox"],
            }
        if anchor["kind"] == "media":
            return {**base, "startSeconds": anchor["startSeconds"], "endSeconds": anchor["endSeconds"]}
        raise BusinessValidationError("source_anchor_kind_unsupported", "SourceAnchor 无法映射为证据 locator。")


__all__ = ["DataPackService"]

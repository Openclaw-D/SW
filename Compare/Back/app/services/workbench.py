from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter

from app.domain.constants import DIMENSION_FULL_NAMES, RULE_VERSION
from app.domain.scoring import HARD_GATE_FACT_KEYS, SCORING_FACT_KEYS, evaluate_project
from app.contracts.errors import (
    BusinessValidationError,
    ConflictError,
    HardGateBlockedError,
    IdempotencyConflictError,
    NotFoundError,
    ServiceError,
    VersionConflictError,
)
from app.contracts.data_pack import (
    CandidateConfirmationCommand,
    CandidateConfirmationResult,
    ExecuteImportManifestRequest,
    ImportManifestRequest,
    MaterialImportPreflight,
    MaterialImportResult,
    MaterialIntelligenceRunCommand,
    StoredMaterialIntelligence,
    StoredSceneSpec,
)
from app.contracts.ports import WorkbenchServicePort
from app.contracts.project_selection import ProjectCatalogItem
from app.contracts.material_schema import (
    MaterialFieldSchema,
    P5_ORIGINAL_MATERIAL_COUNT,
    build_material_field_schema,
)
from app.contracts.workbench import (
    ApprovalState as ApprovalStateContract,
    ApprovalTransitionInput,
    AvailableDimensionSeriesResponse,
    BusinessAnswerCommand,
    BusinessCorrection as BusinessCorrectionContract,
    BusinessCorrectionCommand,
    BusinessCorrectionResult,
    CollaborationSubmissionResult,
    CommonReviewEvent,
    DimensionId,
    DimensionSeriesRequest,
    DimensionSeriesResponse,
    EvidenceReference as EvidenceReferenceContract,
    EvidenceSelectionResolution,
    FactVersion as FactVersionContract,
    HardConstraintResult,
    Material as MaterialContract,
    ResolvedEvidenceItem,
    ReviewEvidenceSelectionGroup,
    ReviewEvidenceTarget as ReviewEvidenceTargetContract,
    RiskAnswerCommand,
    RiskQuestionCommand,
    UnavailableDimensionSeriesResponse,
    WorkbenchProject,
)
from app.core.config import Settings
from app.models import (
    ApprovalState,
    ApprovalTransition,
    AuditRecord,
    BusinessCorrection,
    EvidenceReference,
    FactVersion,
    IdempotencyRecord,
    Material as StoredMaterial,
    MaterialVersion,
    PolicyResult,
    ProjectSnapshot,
    ReviewEvent,
    ReviewEvidenceTarget,
    RuleVersion,
    locator_from_mapping,
    new_id,
    utc_now,
)
from app.repositories import (
    RepositoryConflict,
    RepositoryNotFound,
    RepositoryProjectMismatch,
    SQLiteStateRepository,
)

from .errors import EvidenceSelectionError, InvalidLocatorError
from .generator_adapter import (
    WorkbenchGeneratorAdapter,
    discover_generator_adapter,
)
from .locators import LocatorService
from .data_pack import DataPackService
from .seeding import SeedService


_MATERIAL_ADAPTER = TypeAdapter(MaterialContract)
_DIMENSION_SERIES_ADAPTER = TypeAdapter(DimensionSeriesResponse)
_T = TypeVar("_T", bound=BaseModel)


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump(by_alias=True, mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


class WorkbenchService(WorkbenchServicePort):
    def __init__(
        self,
        repository: SQLiteStateRepository,
        generator: WorkbenchGeneratorAdapter,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.generator = generator
        self.locators = LocatorService(repository)
        self.data_pack = DataPackService(
            repository,
            settings or Settings(database_path=Path(repository.database_path)),
        )

    def close(self) -> None:
        self.repository.close()

    def _translate_repository_error(self, exc: Exception) -> Exception:
        if isinstance(exc, RepositoryProjectMismatch):
            return NotFoundError(
                f"{exc.entity}_not_found",
                "请求对象不存在或不属于当前项目。",
            )
        if isinstance(exc, RepositoryNotFound):
            return NotFoundError(
                f"{exc.entity}_not_found",
                "请求对象不存在或不属于当前项目。",
            )
        if isinstance(exc, RepositoryConflict):
            return ConflictError("state_conflict", str(exc))
        return exc

    def _project(self, project_id: str, connection: sqlite3.Connection):
        try:
            return self.repository.get_project(project_id, connection)
        except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
            raise self._translate_repository_error(exc) from exc

    @staticmethod
    def _model_payload(model: BaseModel) -> dict[str, Any]:
        return model.model_dump(by_alias=True, mode="json")

    @staticmethod
    def _restore_service_error(payload: Mapping[str, Any]) -> ServiceError:
        code = str(payload["code"])
        message = str(payload["message"])
        details = dict(payload.get("details") or {})
        field = str(payload["field"]) if payload.get("field") is not None else None
        category = str(payload["category"])
        if code == "version_conflict":
            return VersionConflictError(
                expected_version=int(details["expectedVersion"]),
                actual_version=int(details["actualVersion"]),
            )
        if code == "hard_gate_blocked":
            return HardGateBlockedError(
                [str(value) for value in details.get("blockingRuleIds", [])]
            )
        if category == "validation":
            return BusinessValidationError(
                code,
                message,
                field=field,
                details=details,
            )
        if category == "not_found":
            return NotFoundError(code, message, details=details)
        if category == "conflict":
            return ConflictError(code, message, details=details)
        return ServiceError(
            code=code,
            message=message,
            category="internal",
            status_code=int(payload["statusCode"]),
            field=field,
            details=details,
        )

    def _idempotent(
        self,
        connection: sqlite3.Connection,
        *,
        key: str,
        operation: str,
        request_payload: Any,
        response_model: type[_T],
        write: Callable[[], _T],
    ) -> _T | ServiceError:
        request_hash = _hash({"operation": operation, "payload": request_payload})
        previous = self.repository.get_idempotency_record(key, connection)
        if previous is not None:
            if previous.operation != operation or previous.request_hash != request_hash:
                raise IdempotencyConflictError()
            stored_error = previous.response.get("_serviceError")
            if isinstance(stored_error, dict):
                return self._restore_service_error(stored_error)
            return response_model.model_validate(previous.response)
        connection.execute("SAVEPOINT idempotency_write")
        try:
            result: _T | ServiceError = write()
        except ServiceError as exc:
            connection.execute("ROLLBACK TO SAVEPOINT idempotency_write")
            connection.execute("RELEASE SAVEPOINT idempotency_write")
            result = exc
            response = {
                "_serviceError": {
                    "code": exc.code,
                    "message": exc.message,
                    "category": exc.category,
                    "statusCode": exc.status_code,
                    "field": exc.field,
                    "details": exc.details,
                }
            }
            status_code = exc.status_code
        else:
            connection.execute("RELEASE SAVEPOINT idempotency_write")
            response = result.model_dump(by_alias=True, mode="json")
            status_code = 200
        self.repository.create_idempotency_record(
            IdempotencyRecord(
                key=key,
                operation=operation,
                request_hash=request_hash,
                response=response,
                status_code=status_code,
                created_at=utc_now(),
            ),
            connection,
        )
        return result

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        action: str,
        aggregate_type: str,
        aggregate_id: str,
        actor: str,
        payload: Mapping[str, Any],
        created_at: str | None = None,
    ) -> AuditRecord:
        timestamp = created_at or utc_now()
        sequence = self.repository.next_audit_sequence(project_id, connection)
        previous_hash = self.repository.latest_audit_hash(project_id, connection)
        hash_payload = {
            "projectId": project_id,
            "sequence": sequence,
            "action": action,
            "aggregateType": aggregate_type,
            "aggregateId": aggregate_id,
            "actor": actor,
            "payload": dict(payload),
            "previousHash": previous_hash,
            "createdAt": timestamp,
        }
        record = AuditRecord(
            id=new_id("audit"),
            project_id=project_id,
            sequence=sequence,
            action=action,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor=actor,
            payload=dict(payload),
            previous_hash=previous_hash,
            event_hash=_hash(hash_payload),
            created_at=timestamp,
        )
        self.repository.create_audit_record(record, connection)
        return record

    def list_projects(self) -> list[ProjectCatalogItem]:
        with self.repository.transaction(write=False) as connection:
            projects = self.repository.list_projects(connection)
        result: list[ProjectCatalogItem] = []
        for project in projects:
            catalog = project.payload.get("catalog")
            if not isinstance(catalog, dict):
                raise RuntimeError(f"project {project.id} has no catalog snapshot")
            result.append(ProjectCatalogItem.model_validate(catalog))
        return result

    def _material_contract(
        self, project_id: str, material_id: str, connection: sqlite3.Connection
    ) -> MaterialContract:
        try:
            material = self.repository.get_material(project_id, material_id, connection)
            if material.current_version_id is None:
                raise NotFoundError(
                    "material_version_not_found", "材料尚无可读取版本。"
                )
            version = self.repository.get_material_version(
                project_id, material.current_version_id, connection
            )
        except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
            raise self._translate_repository_error(exc) from exc
        contract = _MATERIAL_ADAPTER.validate_python(version.payload)
        return contract.model_copy(
            update={
                "original_access": self.data_pack.material_original_access(
                    project_id, material_id, version.content_hash
                )
            }
        )

    def list_materials(self, project_id: str) -> list[MaterialContract]:
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
            materials = self.repository.list_materials(project_id, connection)
            return [
                self._material_contract(project_id, material.id, connection)
                for material in materials
            ]

    def get_material(self, project_id: str, material_id: str) -> MaterialContract:
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
            return self._material_contract(project_id, material_id, connection)

    def get_material_field_schema(self, project_id: str) -> MaterialFieldSchema:
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
        return build_material_field_schema(project_id)

    async def upload_material_pack(self, project_id: str, file_name: str, content_length: int | None, stream):
        return await self.data_pack.upload_zip(project_id, file_name, content_length, stream)

    def get_material_original(self, project_id: str, material_id: str):
        return self.data_pack.material_original(project_id, material_id)

    def preflight_material_import(
        self, project_id: str, command: ImportManifestRequest
    ) -> MaterialImportPreflight:
        if command.project_id != project_id:
            raise BusinessValidationError("path_body_mismatch", "projectId 必须与路径一致。")
        preflight, _manifest = self.data_pack.preflight_manifest(
            project_id, command.manifest_ref
        )
        return preflight

    def execute_material_import(
        self,
        project_id: str,
        command: ExecuteImportManifestRequest,
        *,
        idempotency_key: str,
    ) -> MaterialImportResult:
        if command.project_id != project_id:
            raise BusinessValidationError("path_body_mismatch", "projectId 必须与路径一致。")
        preflight, manifest = self.data_pack.preflight_manifest(
            project_id, command.manifest_ref
        )
        with self.repository.transaction(write=True) as connection:
            def write() -> MaterialImportResult:
                result = self.data_pack.execute_import(
                    connection, preflight, manifest,
                    expected_version=command.expected_version,
                )
                self._append_audit(
                    connection, project_id=project_id,
                    action="controlled_material_imported",
                    aggregate_type="material_import", aggregate_id=result.import_id,
                    actor="business",
                    payload={
                        "manifestRef": command.manifest_ref,
                        "manifestHash": result.manifest_hash,
                        "materialVersionIds": [item.material_version_id for item in result.items],
                        "classification": [item.classification.value for item in result.items],
                    },
                )
                return result

            outcome = self._idempotent(
                connection, key=idempotency_key,
                operation=f"material_import:{project_id}:{command.manifest_ref}",
                request_payload=command, response_model=MaterialImportResult,
                write=write,
            )
        if isinstance(outcome, ServiceError):
            raise outcome
        return outcome

    def run_material_intelligence(
        self,
        project_id: str,
        material_id: str,
        command: MaterialIntelligenceRunCommand,
        *,
        idempotency_key: str,
    ) -> StoredMaterialIntelligence:
        if command.project_id != project_id or command.material_id != material_id:
            raise BusinessValidationError("path_body_mismatch", "projectId/materialId 必须与路径一致。")
        prepared, context = self.data_pack.prepare_intelligence(
            project_id, material_id, command
        )
        with self.repository.transaction(write=True) as connection:
            def write() -> StoredMaterialIntelligence:
                stored = self.data_pack.persist_intelligence(connection, prepared, context)
                self._append_audit(
                    connection, project_id=project_id,
                    action="material_intelligence_recorded",
                    aggregate_type="material_intelligence", aggregate_id=stored.run_id,
                    actor="system",
                    payload={
                        "materialId": material_id,
                        "materialVersionId": command.material_version_id,
                        "inputHash": stored.result.input_hash,
                        "candidateIds": stored.candidate_ids,
                        "sceneGenerated": stored.result.scene_spec is not None,
                        "isSimulated": stored.result.is_simulated,
                    },
                )
                return stored

            outcome = self._idempotent(
                connection, key=idempotency_key,
                operation=f"material_intelligence:{project_id}:{material_id}",
                request_payload=command, response_model=StoredMaterialIntelligence,
                write=write,
            )
        if isinstance(outcome, ServiceError):
            raise outcome
        return outcome

    def get_material_intelligence(
        self, project_id: str, material_id: str
    ) -> StoredMaterialIntelligence:
        return self.data_pack.latest_intelligence(project_id, material_id)

    def get_material_scene_spec(
        self, project_id: str, material_id: str
    ) -> StoredSceneSpec:
        return self.data_pack.latest_scene(project_id, material_id)

    def ensure_p5_intelligence_seed(self) -> int:
        with self.repository.transaction(write=False) as connection:
            rows = connection.execute(
                """SELECT m.project_id, m.id AS material_id, mv.id AS version_id, mv.version
                   FROM materials m
                   JOIN material_versions mv ON mv.id = m.current_version_id
                   WHERE m.id LIKE '%-production-site'
                   ORDER BY m.project_id"""
            ).fetchall()
            pending = [
                row for row in rows
                if connection.execute(
                    "SELECT 1 FROM material_intelligence_runs WHERE project_id = ? AND material_id = ? LIMIT 1",
                    (row["project_id"], row["material_id"]),
                ).fetchone() is None
            ]
        for row in pending:
            command = MaterialIntelligenceRunCommand(
                project_id=row["project_id"], material_id=row["material_id"],
                material_version_id=row["version_id"], context_version="p5-seed-v1",
                task_goals=[
                    "observe", "extract_field_candidates", "scene_spec"
                ],
                expected_version=row["version"],
            )
            self.run_material_intelligence(
                row["project_id"], row["material_id"], command,
                idempotency_key=f"p5-mi-{_hash([row['project_id'], row['material_id']])[:32]}",
            )
        return len(pending)

    def upgrade_seeded_p5_material_packs(self) -> int:
        """Append P5 materials to an existing P4 runtime DB without deleting state."""

        with self.repository.transaction(write=False) as connection:
            incomplete = connection.execute(
                """SELECT COUNT(*) FROM projects p
                   WHERE (SELECT COUNT(*) FROM materials m WHERE m.project_id = p.id) < ?""",
                (P5_ORIGINAL_MATERIAL_COUNT,),
            ).fetchone()[0]
        if incomplete == 0:
            return 0
        bundles = tuple(self.generator.seed_bundles())
        upgraded = 0
        with self.repository.transaction(write=True) as connection:
            for bundle in bundles:
                payload = bundle.workbench
                generated = WorkbenchProject.model_validate(payload)
                generated_payload = generated.model_dump(by_alias=True, mode="json")
                if len(generated.materials) < P5_ORIGINAL_MATERIAL_COUNT or not any(
                    item.id.endswith("production-site") for item in generated.materials
                ):
                    continue
                try:
                    self.repository.get_project(generated.project.id, connection)
                except RepositoryNotFound:
                    continue
                existing_materials = {
                    item.id for item in self.repository.list_materials(generated.project.id, connection)
                }
                now = utc_now()
                inserted_materials = 0
                for item in generated_payload["materials"]:
                    material_id = str(item["id"])
                    if material_id in existing_materials:
                        continue
                    version_id = str(item["versionId"])
                    self.repository.create_material(
                        StoredMaterial(
                            id=material_id, project_id=generated.project.id,
                            kind=str(item["kind"]), file_name=str(item["fileName"]),
                            availability=str(item["availability"]), current_version_id=None,
                            metadata={
                                "label": item["label"], "sourceLabel": item["sourceLabel"],
                                "isSimulated": item["isSimulated"],
                                "folderPath": item.get("folderPath"),
                                "businessPath": item.get("businessPath"),
                            },
                            created_at=now,
                        ),
                        connection,
                    )
                    self.repository.create_material_version(
                        MaterialVersion(
                            id=version_id, project_id=generated.project.id,
                            material_id=material_id, version=1,
                            mime_type=str(item["mimeType"]), content_hash=_hash(item),
                            payload=dict(item), created_at=now,
                            created_by="p5-datapack-upgrade",
                        ),
                        connection,
                    )
                    self.repository.set_current_material_version(
                        generated.project.id, material_id, version_id, connection
                    )
                    inserted_materials += 1
                existing_evidence = {
                    item.id
                    for item in self.repository.list_evidence_references(
                        generated.project.id, connection
                    )
                }
                for item in generated_payload["evidence"]:
                    if item["id"] in existing_evidence:
                        continue
                    evidence = EvidenceReference(
                        id=str(item["id"]), project_id=generated.project.id,
                        label=str(item["label"]),
                        locator=(locator_from_mapping(item["locator"]) if item.get("locator") else None),
                        location_status=str(item["locationStatus"]),
                        material_status=str(item["materialStatus"]), created_at=now,
                    )
                    self.locators.validate_reference(generated.project.id, evidence, connection)
                    self.repository.create_evidence_reference(evidence, connection)
                snapshot = self.repository.latest_project_snapshot(generated.project.id, connection)
                snapshot_materials = (snapshot.payload.get("materials", []) if snapshot else [])
                needs_snapshot = not any(
                    isinstance(item, dict) and str(item.get("id", "")).endswith("production-site")
                    for item in snapshot_materials
                )
                if needs_snapshot:
                    version = self.repository.next_snapshot_version(generated.project.id, connection)
                    self.repository.create_project_snapshot(
                        ProjectSnapshot(
                            id=new_id("snapshot"), project_id=generated.project.id,
                            version=version, payload=generated_payload,
                            created_at=now, created_by="p5-datapack-upgrade",
                        ),
                        connection,
                    )
                if inserted_materials or needs_snapshot:
                    upgraded += 1
                    self._append_audit(
                        connection, project_id=generated.project.id,
                        action="p5_material_pack_upgraded",
                        aggregate_type="project", aggregate_id=generated.project.id,
                        actor="system",
                        payload={
                            "insertedMaterialCount": inserted_materials,
                            "snapshotUpgraded": needs_snapshot,
                            "targetMaterialCount": len(generated.materials),
                        },
                        created_at=now,
                    )
        return upgraded

    @staticmethod
    def _evidence_contract(evidence: EvidenceReference) -> EvidenceReferenceContract:
        return EvidenceReferenceContract.model_validate(evidence.to_front_dict())

    @staticmethod
    def _fact_contract(fact: FactVersion) -> FactVersionContract:
        return FactVersionContract.model_validate(fact.to_front_dict())

    @staticmethod
    def _correction_contract(
        correction: BusinessCorrection,
    ) -> BusinessCorrectionContract:
        return BusinessCorrectionContract.model_validate(correction.to_front_dict())

    @staticmethod
    def _target_model(target: ReviewEvidenceTargetContract) -> ReviewEvidenceTarget:
        return ReviewEvidenceTarget(
            evidence_ref=target.evidence_ref,
            evidence_refs=tuple(target.evidence_refs or [target.evidence_ref]),
            dimension_id=target.dimension_id,
            review_target_id=target.review_target_id,
            fact_version_id=target.fact_version_id,
            unavailable_reason=target.unavailable_reason,
        )

    @staticmethod
    def _event_contract(event: ReviewEvent) -> CommonReviewEvent:
        return CommonReviewEvent.model_validate(event.to_front_dict())

    @staticmethod
    def _policy_contract(result: PolicyResult) -> HardConstraintResult:
        return HardConstraintResult.model_validate(result.to_front_dict())

    @staticmethod
    def _latest_policy_results(
        results: Sequence[PolicyResult],
    ) -> dict[str, PolicyResult]:
        latest: dict[str, PolicyResult] = {}
        for result in results:
            latest[result.rule_id] = result
        return latest

    def _open_issue_count(self, events: Sequence[ReviewEvent]) -> int:
        latest: dict[str, ReviewEvent] = {}
        for event in events:
            latest[event.thread_id] = event
        return sum(
            event.issue_status in {"open", "pending_gate"} for event in latest.values()
        )

    def get_workbench(self, project_id: str) -> WorkbenchProject:
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
            snapshot = self.repository.latest_project_snapshot(project_id, connection)
            if snapshot is None:
                raise NotFoundError(
                    "project_snapshot_not_found", "项目尚无可读取工作台快照。"
                )
            payload = json.loads(_canonical(snapshot.payload))
            materials = self.repository.list_materials(project_id, connection)
            evidence = self.data_pack.project_current_evidence(
                materials,
                self.repository.list_evidence_references(project_id, connection),
            )
            facts = self.repository.list_fact_versions(project_id, connection)
            corrections = self.repository.list_business_corrections(project_id, connection)
            events = self.repository.list_review_events(project_id, connection)
            policies = self.repository.list_policy_results(project_id, connection)
            payload["materials"] = [
                self._material_contract(project_id, material.id, connection).model_dump(
                    by_alias=True, mode="json"
                )
                for material in materials
            ]
            payload["evidence"] = [item.to_front_dict() for item in evidence]
            payload["facts"] = [item.to_front_dict() for item in facts]
            payload["corrections"] = [item.to_front_dict() for item in corrections]
            payload["reviewEvents"] = [item.to_front_dict() for item in events]
            payload["project"]["materialCount"] = len(materials)
            payload["project"]["collaborationIssueCount"] = self._open_issue_count(events)
            latest_policies = self._latest_policy_results(policies)
            policy_payloads = {
                rule_id: item.to_front_dict()
                for rule_id, item in latest_policies.items()
            }
            payload["riskSummary"]["hardConstraintResults"] = list(
                policy_payloads.values()
            )
            payload["riskSummary"]["evidenceRefs"] = list(
                _ordered_unique(
                    [
                        evidence_ref
                        for item in latest_policies.values()
                        for target in item.evidence_targets
                        for evidence_ref in target.evidence_refs
                    ]
                )
            )
            payload["riskSummary"]["decisionGrade"] = (
                "E"
                if any(item.result == "block" for item in latest_policies.values())
                else payload["riskSummary"]["scoreGrade"]
            )
            for determination in payload.get("determinations", []):
                determination["hardConstraintResults"] = [
                    policy_payloads.get(item.get("ruleId"), item)
                    for item in determination.get("hardConstraintResults", [])
                ]
                determination["decisionGrade"] = (
                    "E"
                    if any(
                        item.get("result") == "block"
                        for item in determination["hardConstraintResults"]
                    )
                    else determination["scoreGrade"]
                )
            return WorkbenchProject.model_validate(payload)

    def _validate_target(
        self,
        project_id: str,
        target: ReviewEvidenceTargetContract,
        connection: sqlite3.Connection,
        *,
        require_located: bool,
    ) -> None:
        refs = target.evidence_refs or [target.evidence_ref]
        if target.evidence_ref not in refs:
            raise BusinessValidationError(
                "evidence_target_invalid",
                "evidenceTarget.evidenceRef 必须包含在 evidenceRefs 中。",
                field="evidenceTargets",
            )
        fact: FactVersion | None = None
        if target.fact_version_id is not None:
            try:
                fact = self.repository.get_fact_version(
                    project_id, target.fact_version_id, connection
                )
            except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                raise self._translate_repository_error(exc) from exc
            if fact.dimension_id != target.dimension_id:
                raise BusinessValidationError(
                    "evidence_fact_dimension_mismatch",
                    "证据目标与 FactVersion 维度不一致。",
                    field="evidenceTargets",
                )
            if any(ref not in fact.evidence_refs for ref in refs):
                raise BusinessValidationError(
                    "evidence_fact_pair_mismatch",
                    "evidenceTargets 声明的证据并未支持该 FactVersion。",
                    field="evidenceTargets",
                )
        location_refs = [target.evidence_ref] if require_located else refs
        for evidence_ref in location_refs:
            try:
                resolution = self.locators.resolve(project_id, evidence_ref, connection)
            except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                raise self._translate_repository_error(exc) from exc
            if require_located and resolution.status != "located":
                raise EvidenceSelectionError(
                    status=resolution.status,
                    failed_target=target.model_dump(by_alias=True, mode="json"),
                    message=f"选择组定位失败：{resolution.message}",
                )
            if (
                not require_located
                and resolution.status != "located"
                and not (target.unavailable_reason or "").strip()
            ):
                raise BusinessValidationError(
                    "unavailable_reason_required",
                    "未定位证据进入正式审查链时必须说明 unavailableReason。",
                    field="evidenceTargets",
                    details={"evidenceRef": evidence_ref, "status": resolution.status},
                )

    def resolve_evidence(
        self,
        project_id: str,
        selection_group: ReviewEvidenceSelectionGroup,
    ) -> EvidenceSelectionResolution:
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
            items: list[ResolvedEvidenceItem] = []
            for target in selection_group.targets:
                try:
                    self._validate_target(
                        project_id, target, connection, require_located=True
                    )
                except EvidenceSelectionError:
                    raise
                except InvalidLocatorError as exc:
                    raise EvidenceSelectionError(
                        status="invalid_locator",
                        failed_target=target.model_dump(by_alias=True, mode="json"),
                        message=f"选择组定位失败：{exc.message}",
                    ) from exc
                except NotFoundError as exc:
                    status = (
                        "missing_material"
                        if exc.code.startswith("material")
                        else "missing_evidence"
                    )
                    raise EvidenceSelectionError(
                        status=status,
                        failed_target=target.model_dump(by_alias=True, mode="json"),
                        message=f"选择组定位失败：{exc.message}",
                    ) from exc
                evidence = self.repository.get_evidence_reference(
                    project_id, target.evidence_ref, connection
                )
                items.append(
                    ResolvedEvidenceItem(
                        target=target,
                        evidence=self._evidence_contract(evidence),
                    )
                )
            return EvidenceSelectionResolution(
                selection_group=selection_group,
                items=items,
            )

    def query_dimension_series(
        self,
        project_id: str,
        dimension_id: DimensionId,
        request: DimensionSeriesRequest,
    ) -> DimensionSeriesResponse:
        if request.project_id != project_id or request.dimension_id != dimension_id:
            raise BusinessValidationError(
                "path_body_mismatch",
                "projectId/dimensionId 必须与路径一致。",
                field="request",
            )
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
        result = self.generator.query_dimension_series(request)
        if result is None:
            return UnavailableDimensionSeriesResponse(
                status="unavailable",
                request=request,
                points=[],
                message="当前生成器未提供该维度的时间序列，服务未构造替代指标。",
                source_label="P4-Back-3 generator unavailable",
                is_simulated=True,
            )
        return _DIMENSION_SERIES_ADAPTER.validate_python(result)

    def _next_event_version(
        self, project_id: str, connection: sqlite3.Connection
    ) -> int:
        return self.repository.next_review_sequence(project_id, connection)

    def _validate_reply(
        self,
        project_id: str,
        thread_id: str,
        reply_to_event_id: str | None,
        connection: sqlite3.Connection,
    ) -> None:
        if not thread_id.strip():
            raise BusinessValidationError(
                "review_thread_required",
                "threadId 不能为空。",
                field="threadId",
            )
        thread_events = [
            event
            for event in self.repository.list_review_events(project_id, connection)
            if event.thread_id == thread_id
        ]
        if reply_to_event_id is None:
            if thread_events:
                raise BusinessValidationError(
                    "review_thread_exists",
                    "已存在的 threadId 必须通过 replyToEventId 续接。",
                    field="replyToEventId",
                )
            return
        try:
            parent = self.repository.get_review_event(
                project_id, reply_to_event_id, connection
            )
        except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
            raise self._translate_repository_error(exc) from exc
        if parent.thread_id != thread_id:
            raise BusinessValidationError(
                "review_thread_mismatch",
                "replyToEventId 必须属于同一 threadId。",
                field="replyToEventId",
            )
        if not thread_events or thread_events[-1].id != parent.id:
            raise BusinessValidationError(
                "review_reply_stale",
                "replyToEventId 必须指向该线程的最新不可变事件。",
                field="replyToEventId",
            )

    def _build_review_event(
        self,
        *,
        project_id: str,
        sequence: int,
        command: Any,
        event_type: str,
        actor: str,
        actor_label: str,
        issue_status: str,
        title: str,
        summary: str,
        connection: sqlite3.Connection,
    ) -> ReviewEvent:
        if not command.evidence_targets:
            raise BusinessValidationError(
                "review_evidence_required",
                "正式审查事件必须包含至少一个权威 evidenceTarget。",
                field="evidenceTargets",
            )
        target_identities = [
            (
                target.evidence_ref,
                target.review_target_id,
                target.fact_version_id,
            )
            for target in command.evidence_targets
        ]
        if len(set(target_identities)) != len(target_identities):
            raise BusinessValidationError(
                "review_evidence_target_duplicate",
                "同一审查事件不能重复提交完全相同的 evidenceTarget。",
                field="evidenceTargets",
            )
        if not summary.strip():
            raise BusinessValidationError(
                "review_content_required",
                "审查问题或回答不能为空。",
                field="summary",
            )
        for target in command.evidence_targets:
            self._validate_target(
                project_id, target, connection, require_located=False
            )
        self._validate_reply(
            project_id, command.thread_id, command.reply_to_event_id, connection
        )
        created_at = utc_now()
        event = ReviewEvent(
            id=new_id("review-event"),
            project_id=project_id,
            sequence=sequence,
            thread_id=command.thread_id,
            reply_to_event_id=command.reply_to_event_id,
            issue_status=issue_status,
            event_type=event_type,
            actor=actor,
            actor_label=actor_label,
            dimension_id=command.dimension_id,
            evidence_targets=tuple(
                self._target_model(target) for target in command.evidence_targets
            ),
            review_target_id=command.review_target_id,
            title=title,
            summary=summary.strip(),
            fact_version_ids=tuple(command.fact_version_ids),
            evidence_refs=tuple(command.evidence_refs),
            rule_refs=(),
            created_at=created_at,
            immutable=True,
            is_simulated=True,
        )
        self.repository.create_review_event(event, connection)
        self._append_audit(
            connection,
            project_id=project_id,
            action=event_type,
            aggregate_type="review_event",
            aggregate_id=event.id,
            actor=actor,
            payload=event.to_front_dict(),
            created_at=created_at,
        )
        return event

    def _fact_evidence_status(
        self,
        project_id: str,
        fact: FactVersion,
        connection: sqlite3.Connection,
    ) -> str:
        if not fact.evidence_refs:
            return "missing"
        statuses: set[str] = set()
        for evidence_ref in fact.evidence_refs:
            try:
                evidence = self.repository.get_evidence_reference(
                    project_id, evidence_ref, connection
                )
                resolution = self.locators.resolve(project_id, evidence_ref, connection)
            except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                raise self._translate_repository_error(exc) from exc
            if resolution.status == "pending":
                statuses.add("missing")
            elif resolution.status in {"unverifiable", "version_mismatch"}:
                statuses.add("unverifiable")
            elif evidence.material_status == "conflict":
                statuses.add("conflicting")
            elif evidence.material_status == "review":
                statuses.add("needs_review")
            else:
                statuses.add("verified")
        for status in ("missing", "unverifiable", "conflicting", "needs_review"):
            if status in statuses:
                return status
        return "verified"

    def _current_policy_inputs(
        self,
        project_id: str,
        connection: sqlite3.Connection,
    ) -> tuple[
        dict[str, FactVersion],
        dict[str, Any],
        dict[str, str],
        list[dict[str, float | int]],
    ]:
        latest_facts: dict[str, FactVersion] = {}
        for fact in self.repository.list_fact_versions(project_id, connection):
            canonical_key = fact.fact_key.rsplit(".", 1)[-1]
            if canonical_key in SCORING_FACT_KEYS:
                latest_facts[canonical_key] = fact
        missing = [key for key in SCORING_FACT_KEYS if key not in latest_facts]
        if missing:
            raise BusinessValidationError(
                "policy_evaluation_input_missing",
                "项目缺少制度规则重算所需的最新事实。",
                field="facts",
                details={"missingFactKeys": missing},
            )
        facts = {key: latest_facts[key].value for key in SCORING_FACT_KEYS}
        status_by_fact = {
            key: self._fact_evidence_status(project_id, latest_facts[key], connection)
            for key in SCORING_FACT_KEYS
        }
        evidence_statuses = {
            f"{latest_facts[key].dimension_id}.{key}": status
            for key, status in status_by_fact.items()
        }
        for evidence_key, fact_key in HARD_GATE_FACT_KEYS.items():
            evidence_statuses[evidence_key] = status_by_fact[fact_key]

        snapshot = self.repository.latest_project_snapshot(project_id, connection)
        schedule_payload: Any = None
        if snapshot is not None:
            equipment = snapshot.payload.get("financedEquipment")
            if isinstance(equipment, Mapping):
                schedule = equipment.get("repaymentSchedule")
                if isinstance(schedule, Mapping):
                    schedule_payload = schedule.get("points")
        if not isinstance(schedule_payload, list) or not schedule_payload:
            raise BusinessValidationError(
                "policy_repayment_schedule_missing",
                "项目缺少制度规则重算所需的持久化还款计划。",
                field="financedEquipment.repaymentSchedule.points",
            )
        repayment_points: list[dict[str, float | int]] = []
        try:
            for point in schedule_payload:
                if not isinstance(point, Mapping):
                    raise TypeError("repayment point must be a mapping")
                repayment_points.append(
                    {
                        "period": int(point["period"]),
                        "principal": float(point["principal"]),
                        "interest": float(point["interest"]),
                        "rent": float(point["rent"]),
                    }
                )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise BusinessValidationError(
                "policy_repayment_schedule_invalid",
                "持久化还款计划无法用于制度规则重算。",
                field="financedEquipment.repaymentSchedule.points",
            ) from exc
        return latest_facts, facts, evidence_statuses, repayment_points

    def _policy_rule_version(
        self,
        constraint: Any,
        template: PolicyResult | None,
        connection: sqlite3.Connection,
    ) -> RuleVersion:
        version = template.rule_version if template is not None else RULE_VERSION
        existing = self.repository.find_rule_version(
            constraint.rule_id, version, connection
        )
        if existing is not None:
            return existing
        scope = f"{DIMENSION_FULL_NAMES[constraint.dimension_id]}单项目核验"
        evidence_requirement = (
            "必须使用同一材料版本的精确 locator；缺件只能转人工复核。"
        )
        definition = {
            "kind": "hard_constraint",
            "ruleId": constraint.rule_id,
            "version": version,
            "title": constraint.title,
            "scope": scope,
            "evidenceRequirement": evidence_requirement,
            "responsibleParty": "joint",
            "source": "domain_scoring",
        }
        rule = RuleVersion(
            id=f"rule-version::{constraint.rule_id}::{version}",
            rule_id=constraint.rule_id,
            version=version,
            title=constraint.title,
            is_hard_gate=True,
            definition=definition,
            definition_hash=_hash(definition),
            created_at=utc_now(),
            created_by="system",
        )
        self.repository.create_rule_version(rule, connection)
        return rule

    def _recalculate_policy_results(
        self,
        *,
        project_id: str,
        correction: BusinessCorrection,
        trigger_fact: FactVersion,
        evaluated_at: str,
        connection: sqlite3.Connection,
    ) -> tuple[tuple[PolicyResult, ...], ReviewEvent]:
        latest_facts, facts, evidence_statuses, repayment_points = (
            self._current_policy_inputs(project_id, connection)
        )
        try:
            assessment = evaluate_project(facts, evidence_statuses, repayment_points)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise BusinessValidationError(
                "policy_evaluation_input_invalid",
                "最新事实值无法通过冻结制度规则校验。",
                field="facts",
                details={"triggerFactKey": trigger_fact.fact_key},
            ) from exc

        previous = self._latest_policy_results(
            self.repository.list_policy_results(project_id, connection)
        )
        fact_inputs = {
            key: {
                "factVersionId": latest_facts[key].id,
                "version": latest_facts[key].version,
                "value": latest_facts[key].value,
                "evidenceRefs": list(latest_facts[key].evidence_refs),
                "evidenceStatus": self._fact_evidence_status(
                    project_id, latest_facts[key], connection
                ),
            }
            for key in SCORING_FACT_KEYS
        }
        policy_results: list[PolicyResult] = []
        trigger_status = self._fact_evidence_status(
            project_id, trigger_fact, connection
        )
        trigger_refs = _ordered_unique(trigger_fact.evidence_refs)
        trigger_unavailable_reason = (
            None
            if trigger_status == "verified"
            else "触发修正的材料缺失、冲突或无法核验。"
        )
        all_targets: list[ReviewEvidenceTarget] = [
            ReviewEvidenceTarget(
                evidence_ref=evidence_ref,
                evidence_refs=trigger_refs,
                dimension_id=trigger_fact.dimension_id,
                review_target_id=trigger_fact.fact_key,
                fact_version_id=trigger_fact.id,
                unavailable_reason=trigger_unavailable_reason,
            )
            for evidence_ref in trigger_refs
        ]
        for target in all_targets:
            self._validate_target(
                project_id,
                ReviewEvidenceTargetContract.model_validate(target.to_dict()),
                connection,
                require_located=False,
            )
        for constraint in assessment.constraints:
            fact_key = HARD_GATE_FACT_KEYS[constraint.evidence_key]
            policy_fact = latest_facts[fact_key]
            status = evidence_statuses[constraint.evidence_key]
            evidence_refs = _ordered_unique(policy_fact.evidence_refs)
            unavailable_reason = (
                None
                if status == "verified"
                else "材料缺失、冲突或无法核验，仅进入人工复核，不形成否决。"
            )
            targets = tuple(
                ReviewEvidenceTarget(
                    evidence_ref=evidence_ref,
                    evidence_refs=evidence_refs,
                    dimension_id=constraint.dimension_id,
                    review_target_id=f"rule-{constraint.rule_id}",
                    fact_version_id=policy_fact.id,
                    unavailable_reason=unavailable_reason,
                )
                for evidence_ref in evidence_refs
            )
            for target in targets:
                self._validate_target(
                    project_id,
                    ReviewEvidenceTargetContract.model_validate(target.to_dict()),
                    connection,
                    require_located=False,
                )
            template = previous.get(constraint.rule_id)
            rule = self._policy_rule_version(constraint, template, connection)
            scope = (
                template.scope
                if template is not None
                else f"{DIMENSION_FULL_NAMES[constraint.dimension_id]}单项目核验"
            )
            evidence_requirement = (
                template.evidence_requirement
                if template is not None
                else "必须使用同一材料版本的精确 locator；缺件只能转人工复核。"
            )
            next_action = (
                "阻断并由人工确认"
                if constraint.result == "block"
                else "补件后人工复核"
                if constraint.result == "manual_review"
                else "保持规则通过状态"
            )
            result = PolicyResult(
                id=new_id("policy-result"),
                project_id=project_id,
                rule_version_id=rule.id,
                rule_id=constraint.rule_id,
                rule_version=rule.version,
                title=constraint.title,
                result=constraint.result,
                evidence_targets=targets,
                primary_target=targets[0] if targets else None,
                scope=scope,
                evidence_requirement=evidence_requirement,
                gate_triggered=constraint.gate_triggered,
                responsible_party=(
                    template.responsible_party if template is not None else "joint"
                ),
                next_action=next_action,
                explanation=constraint.explanation,
                evaluation_input={
                    "source": "business_correction_recalculation",
                    "trigger": {
                        "correctionId": correction.id,
                        "factKey": trigger_fact.fact_key,
                        "factVersionId": trigger_fact.id,
                    },
                    "ruleInput": {
                        "factKey": fact_key,
                        "factVersionId": policy_fact.id,
                        "value": policy_fact.value,
                        "evidenceRefs": list(evidence_refs),
                        "evidenceStatus": status,
                    },
                    "facts": fact_inputs,
                    "repaymentSchedule": repayment_points,
                },
                evaluated_at=evaluated_at,
                is_simulated=True,
            )
            self.repository.create_policy_result(result, connection)
            policy_results.append(result)
            all_targets.extend(targets)

        unique_targets = tuple(
            {
                (
                    target.evidence_ref,
                    target.review_target_id,
                    target.fact_version_id,
                ): target
                for target in all_targets
            }.values()
        )
        evidence_refs = _ordered_unique(
            [ref for target in unique_targets for ref in target.evidence_refs]
        )
        fact_version_ids = _ordered_unique(
            [
                target.fact_version_id
                for target in unique_targets
                if target.fact_version_id is not None
            ]
        )
        rule_refs = tuple(
            f"{result.rule_id}@{result.rule_version}" for result in policy_results
        )
        event = ReviewEvent(
            id=new_id("review-event"),
            project_id=project_id,
            sequence=self.repository.next_review_sequence(project_id, connection),
            thread_id=f"policy::{correction.id}",
            reply_to_event_id=None,
            issue_status=(
                "pending_gate"
                if any(result.result != "pass" for result in policy_results)
                else "resolved"
            ),
            event_type="policy_result_recorded",
            actor="system",
            actor_label="制度规则层",
            dimension_id=trigger_fact.dimension_id,
            evidence_targets=unique_targets,
            review_target_id=None,
            title="制度规则重算",
            summary="；".join(
                f"{result.rule_id}={result.result}" for result in policy_results
            ),
            fact_version_ids=fact_version_ids,
            evidence_refs=evidence_refs,
            rule_refs=rule_refs,
            created_at=evaluated_at,
            immutable=True,
            is_simulated=True,
        )
        self.repository.create_review_event(event, connection)
        self._append_audit(
            connection,
            project_id=project_id,
            action="policy_result_recorded",
            aggregate_type="policy_evaluation",
            aggregate_id=event.id,
            actor="system",
            payload={
                "correctionId": correction.id,
                "triggerFactVersionId": trigger_fact.id,
                "policyResultIds": [result.id for result in policy_results],
                "ruleRefs": list(rule_refs),
                "evaluatedAt": evaluated_at,
            },
            created_at=evaluated_at,
        )
        return tuple(policy_results), event

    def submit_business_correction(
        self,
        project_id: str,
        fact_key: str,
        command: BusinessCorrectionCommand,
        *,
        idempotency_key: str,
    ) -> BusinessCorrectionResult:
        if command.project_id != project_id or command.fact_key != fact_key:
            raise BusinessValidationError(
                "path_body_mismatch",
                "projectId/factKey 必须与路径一致。",
                field="command",
            )
        operation = f"business_correction:{project_id}:{fact_key}"
        with self.repository.transaction(write=True) as connection:
            self._project(project_id, connection)

            def write() -> BusinessCorrectionResult:
                try:
                    source = self.repository.get_fact_version(
                        project_id, command.from_fact_version_id, connection
                    )
                except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                    raise self._translate_repository_error(exc) from exc
                current = self.repository.latest_fact_version(
                    project_id, fact_key, connection
                )
                if source.fact_key != fact_key or current is None:
                    raise BusinessValidationError(
                        "fact_key_mismatch",
                        "fromFactVersionId 与 factKey 不一致。",
                        field="fromFactVersionId",
                    )
                if (
                    source.version != command.expected_version
                    or current.id != source.id
                    or current.version != command.expected_version
                ):
                    raise VersionConflictError(
                        expected_version=command.expected_version,
                        actual_version=current.version,
                    )
                if not command.evidence_refs:
                    raise BusinessValidationError(
                        "correction_evidence_required",
                        "业务修正必须引用至少一项同项目证据。",
                        field="evidenceRefs",
                    )
                if not command.reason.strip():
                    raise BusinessValidationError(
                        "correction_reason_required",
                        "业务修正原因不能为空。",
                        field="reason",
                    )
                for evidence_ref in command.evidence_refs:
                    try:
                        self.repository.get_evidence_reference(
                            project_id, evidence_ref, connection
                        )
                    except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                        raise self._translate_repository_error(exc) from exc
                created_at = utc_now()
                fact = FactVersion(
                    id=new_id("fact"),
                    project_id=project_id,
                    fact_key=fact_key,
                    dimension_id=source.dimension_id,
                    version=source.version + 1,
                    label=source.label,
                    value=command.proposed_value,
                    unit=source.unit,
                    source="mock_business_correction",
                    evidence_refs=tuple(command.evidence_refs),
                    supersedes_version_id=source.id,
                    created_at=created_at,
                    created_by="business",
                    is_simulated=True,
                )
                self.repository.create_fact_version(fact, connection)
                correction = BusinessCorrection(
                    id=new_id("correction"),
                    project_id=project_id,
                    fact_key=fact_key,
                    from_fact_version_id=source.id,
                    to_fact_version_id=fact.id,
                    expected_version=command.expected_version,
                    proposed_value=command.proposed_value,
                    reason=command.reason.strip(),
                    evidence_refs=tuple(command.evidence_refs),
                    status="submitted",
                    created_by="business",
                    created_at=created_at,
                    is_simulated=True,
                )
                self.repository.create_business_correction(correction, connection)
                group_refs = tuple(command.evidence_refs)
                targets = tuple(
                    ReviewEvidenceTarget(
                        evidence_ref=ref,
                        evidence_refs=group_refs,
                        dimension_id=source.dimension_id,
                        review_target_id=fact_key,
                        fact_version_id=fact.id,
                    )
                    for ref in group_refs
                )
                thread_id = f"fact::{fact_key}"
                previous_thread_event = next(
                    (
                        existing
                        for existing in reversed(
                            self.repository.list_review_events(project_id, connection)
                        )
                        if existing.thread_id == thread_id
                    ),
                    None,
                )
                event = ReviewEvent(
                    id=new_id("review-event"),
                    project_id=project_id,
                    sequence=self.repository.next_review_sequence(project_id, connection),
                    thread_id=thread_id,
                    reply_to_event_id=(
                        previous_thread_event.id if previous_thread_event else None
                    ),
                    issue_status="answered",
                    event_type="business_correction_submitted",
                    actor="business",
                    actor_label="业务人员",
                    dimension_id=source.dimension_id,
                    evidence_targets=targets,
                    review_target_id=fact_key,
                    title="业务修正",
                    summary=command.reason.strip(),
                    fact_version_ids=(fact.id,),
                    evidence_refs=_ordered_unique(group_refs),
                    rule_refs=(),
                    created_at=created_at,
                    immutable=True,
                    is_simulated=True,
                )
                self.repository.create_review_event(event, connection)
                self._append_audit(
                    connection,
                    project_id=project_id,
                    action="business_correction_submitted",
                    aggregate_type="fact_version",
                    aggregate_id=fact.id,
                    actor="business",
                    payload={
                        "correctionId": correction.id,
                        "fromFactVersionId": source.id,
                        "toFactVersionId": fact.id,
                        "expectedVersion": command.expected_version,
                    },
                    created_at=created_at,
                )
                self._recalculate_policy_results(
                    project_id=project_id,
                    correction=correction,
                    trigger_fact=fact,
                    evaluated_at=created_at,
                    connection=connection,
                )
                return BusinessCorrectionResult(
                    correction=self._correction_contract(correction),
                    fact_version=self._fact_contract(fact),
                    event=self._event_contract(event),
                )

            outcome = self._idempotent(
                connection,
                key=idempotency_key,
                operation=operation,
                request_payload=command,
                response_model=BusinessCorrectionResult,
                write=write,
            )
        if isinstance(outcome, ServiceError):
            raise outcome
        return outcome

    def confirm_material_candidate(
        self,
        project_id: str,
        candidate_id: str,
        command: CandidateConfirmationCommand,
        *,
        idempotency_key: str,
    ) -> CandidateConfirmationResult:
        if command.project_id != project_id or command.candidate_id != candidate_id:
            raise BusinessValidationError("path_body_mismatch", "projectId/candidateId 必须与路径一致。")
        operation = f"candidate_confirmation:{project_id}:{candidate_id}"
        with self.repository.transaction(write=True) as connection:
            self._project(project_id, connection)

            def write() -> CandidateConfirmationResult:
                candidate = connection.execute(
                    "SELECT * FROM extracted_fact_candidates WHERE id = ? AND project_id = ?",
                    (candidate_id, project_id),
                ).fetchone()
                if candidate is None:
                    raise NotFoundError("candidate_not_found", "候选不存在或不属于当前项目。")
                confirmed = connection.execute(
                    "SELECT id FROM candidate_confirmations WHERE project_id = ? AND candidate_id = ?",
                    (project_id, candidate_id),
                ).fetchone()
                if confirmed is not None:
                    raise ConflictError("candidate_already_confirmed", "候选已经完成人工确认。")
                try:
                    source = self.repository.get_fact_version(
                        project_id, command.from_fact_version_id, connection
                    )
                except (RepositoryNotFound, RepositoryProjectMismatch) as exc:
                    raise self._translate_repository_error(exc) from exc
                current = self.repository.latest_fact_version(
                    project_id, candidate["field_key"], connection
                )
                if current is None or source.id != current.id or source.version != command.expected_version:
                    raise VersionConflictError(
                        expected_version=command.expected_version,
                        actual_version=current.version if current else 0,
                    )
                evidence_refs = tuple(json.loads(candidate["evidence_refs_json"]))
                if not evidence_refs:
                    raise BusinessValidationError("candidate_evidence_required", "候选必须绑定可解析 SourceAnchor 证据。")
                for evidence_ref in evidence_refs:
                    resolution = self.locators.resolve(project_id, evidence_ref, connection)
                    if resolution.status != "located":
                        raise BusinessValidationError("candidate_evidence_unresolved", "候选证据未通过 locator 校验。")
                created_at = utc_now()
                value = json.loads(candidate["value_json"]) if command.proposed_value is None else command.proposed_value
                fact = FactVersion(
                    id=new_id("fact"), project_id=project_id,
                    fact_key=source.fact_key, dimension_id=source.dimension_id,
                    version=source.version + 1, label=source.label, value=value,
                    unit=source.unit, source="mock_business_correction",
                    evidence_refs=evidence_refs, supersedes_version_id=source.id,
                    created_at=created_at, created_by="business", is_simulated=True,
                )
                self.repository.create_fact_version(fact, connection)
                correction = BusinessCorrection(
                    id=new_id("correction"), project_id=project_id,
                    fact_key=source.fact_key, from_fact_version_id=source.id,
                    to_fact_version_id=fact.id, expected_version=command.expected_version,
                    proposed_value=value, reason=command.reason.strip(),
                    evidence_refs=evidence_refs, status="submitted",
                    created_by="business", created_at=created_at, is_simulated=True,
                )
                self.repository.create_business_correction(correction, connection)
                targets = tuple(
                    ReviewEvidenceTarget(
                        evidence_ref=ref, evidence_refs=evidence_refs,
                        dimension_id=source.dimension_id,
                        review_target_id=source.fact_key,
                        fact_version_id=fact.id,
                    )
                    for ref in evidence_refs
                )
                event = ReviewEvent(
                    id=new_id("review-event"), project_id=project_id,
                    sequence=self.repository.next_review_sequence(project_id, connection),
                    thread_id=f"candidate::{candidate_id}", reply_to_event_id=None,
                    issue_status="answered", event_type="business_correction_submitted",
                    actor="business", actor_label="业务人员",
                    dimension_id=source.dimension_id, evidence_targets=targets,
                    review_target_id=source.fact_key, title="材料候选人工确认",
                    summary=command.reason.strip(), fact_version_ids=(fact.id,),
                    evidence_refs=evidence_refs, rule_refs=(), created_at=created_at,
                    immutable=True, is_simulated=True,
                )
                self.repository.create_review_event(event, connection)
                confirmation_id = new_id("candidate-confirmation")
                connection.execute(
                    """INSERT INTO candidate_confirmations
                       (id, project_id, candidate_id, from_fact_version_id,
                        to_fact_version_id, expected_version, reason, created_at, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'business')""",
                    (confirmation_id, project_id, candidate_id, source.id, fact.id,
                     command.expected_version, command.reason.strip(), created_at),
                )
                self._append_audit(
                    connection, project_id=project_id,
                    action="material_candidate_confirmed",
                    aggregate_type="fact_candidate", aggregate_id=candidate_id,
                    actor="business",
                    payload={
                        "confirmationId": confirmation_id,
                        "fromFactVersionId": source.id,
                        "toFactVersionId": fact.id,
                        "materialVersionId": candidate["material_version_id"],
                        "sourceAnchorIds": json.loads(candidate["source_anchor_ids_json"]),
                    },
                    created_at=created_at,
                )
                self._recalculate_policy_results(
                    project_id=project_id, correction=correction,
                    trigger_fact=fact, evaluated_at=created_at,
                    connection=connection,
                )
                policies = [
                    self._policy_contract(item)
                    for item in self._latest_policy_results(
                        self.repository.list_policy_results(project_id, connection)
                    ).values()
                ]
                return CandidateConfirmationResult(
                    confirmation_id=confirmation_id, candidate_id=candidate_id,
                    fact_version=self._fact_contract(fact),
                    event=self._event_contract(event), policy_results=policies,
                    approval=self._approval_contract(project_id, connection),
                )

            outcome = self._idempotent(
                connection, key=idempotency_key, operation=operation,
                request_payload=command,
                response_model=CandidateConfirmationResult, write=write,
            )
        if isinstance(outcome, ServiceError):
            raise outcome
        return outcome

    def _submit_review(
        self,
        *,
        project_id: str,
        command: Any,
        idempotency_key: str,
        event_type: str,
        actor: str,
        actor_label: str,
        issue_status: str,
        title: str,
        summary: str,
        response_model: type[_T],
    ) -> _T:
        if command.project_id != project_id:
            raise BusinessValidationError(
                "path_body_mismatch", "projectId 必须与路径一致。", field="projectId"
            )
        operation = f"{event_type}:{project_id}"
        with self.repository.transaction(write=True) as connection:
            self._project(project_id, connection)

            def write() -> _T:
                actual_version = self._next_event_version(project_id, connection)
                if command.expected_version != actual_version:
                    raise VersionConflictError(
                        expected_version=command.expected_version,
                        actual_version=actual_version,
                    )
                event = self._build_review_event(
                    project_id=project_id,
                    sequence=actual_version,
                    command=command,
                    event_type=event_type,
                    actor=actor,
                    actor_label=actor_label,
                    issue_status=issue_status,
                    title=title,
                    summary=summary,
                    connection=connection,
                )
                event_contract = self._event_contract(event)
                if response_model is CommonReviewEvent:
                    return event_contract  # type: ignore[return-value]
                events = self.repository.list_review_events(project_id, connection)
                return CollaborationSubmissionResult(
                    event=event_contract,
                    open_issue_count=self._open_issue_count(events),
                )  # type: ignore[return-value]

            outcome = self._idempotent(
                connection,
                key=idempotency_key,
                operation=operation,
                request_payload=command,
                response_model=response_model,
                write=write,
            )
        if isinstance(outcome, ServiceError):
            raise outcome
        return outcome

    def submit_risk_question(
        self,
        project_id: str,
        command: RiskQuestionCommand,
        *,
        idempotency_key: str,
    ) -> CommonReviewEvent:
        return self._submit_review(
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
            event_type="risk_question_submitted",
            actor="risk",
            actor_label="风控人员",
            issue_status="open",
            title="风控问题",
            summary=command.question,
            response_model=CommonReviewEvent,
        )

    def submit_business_answer(
        self,
        project_id: str,
        command: BusinessAnswerCommand,
        *,
        idempotency_key: str,
    ) -> CollaborationSubmissionResult:
        return self._submit_review(
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
            event_type="business_answer_submitted",
            actor="business",
            actor_label="业务人员",
            issue_status="answered",
            title="业务回答",
            summary=command.answer,
            response_model=CollaborationSubmissionResult,
        )

    def submit_risk_answer(
        self,
        project_id: str,
        command: RiskAnswerCommand,
        *,
        idempotency_key: str,
    ) -> CollaborationSubmissionResult:
        return self._submit_review(
            project_id=project_id,
            command=command,
            idempotency_key=idempotency_key,
            event_type="risk_answer_submitted",
            actor="risk",
            actor_label="风控人员",
            issue_status="pending_gate",
            title="风控意见",
            summary=command.answer,
            response_model=CollaborationSubmissionResult,
        )

    def list_review_events(self, project_id: str) -> list[CommonReviewEvent]:
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
            return [
                self._event_contract(event)
                for event in self.repository.list_review_events(project_id, connection)
            ]

    def list_policy_results(self, project_id: str) -> list[HardConstraintResult]:
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
            return [
                self._policy_contract(result)
                for result in self._latest_policy_results(
                    self.repository.list_policy_results(project_id, connection)
                ).values()
            ]

    def _approval_contract(
        self, project_id: str, connection: sqlite3.Connection
    ) -> ApprovalStateContract:
        stored = self.repository.get_approval_state(project_id, connection)
        if stored is None:
            stored = ApprovalState(
                project_id=project_id,
                state="draft",
                version=1,
                decision_grade=None,
                updated_at=utc_now(),
                updated_by="system",
            )
        latest_by_rule = self._latest_policy_results(
            self.repository.list_policy_results(project_id, connection)
        )
        blocks = [item.rule_id for item in latest_by_rule.values() if item.result == "block"]
        manual = [
            item.rule_id for item in latest_by_rule.values() if item.result == "manual_review"
        ]
        hard_status = "block" if blocks else "manual_review" if manual else "pass"
        blocking = _ordered_unique([*blocks, *manual])
        veto_ids = _ordered_unique(blocks)
        return ApprovalStateContract(
            project_id=project_id,
            version=stored.version,
            status=stored.state,
            hard_gate_status=hard_status,
            blocking_rule_ids=list(blocking),
            risk_veto=bool(veto_ids),
            risk_veto_rule_ids=list(veto_ids),
            updated_at=stored.updated_at,
            is_simulated=True,
        )

    def get_approval_state(self, project_id: str) -> ApprovalStateContract:
        with self.repository.transaction(write=False) as connection:
            self._project(project_id, connection)
            return self._approval_contract(project_id, connection)

    def transition_approval(
        self,
        project_id: str,
        command: ApprovalTransitionInput,
        *,
        idempotency_key: str,
    ) -> ApprovalStateContract:
        operation = f"approval_transition:{project_id}"
        with self.repository.transaction(write=True) as connection:
            self._project(project_id, connection)

            def write() -> ApprovalStateContract:
                current_contract = self._approval_contract(project_id, connection)
                if command.expected_version != current_contract.version:
                    raise VersionConflictError(
                        expected_version=command.expected_version,
                        actual_version=current_contract.version,
                    )
                if command.transition == "complete":
                    blocking = _ordered_unique(
                        [
                            *current_contract.blocking_rule_ids,
                            *current_contract.risk_veto_rule_ids,
                        ]
                    )
                    if current_contract.hard_gate_status != "pass" or blocking:
                        raise HardGateBlockedError(list(blocking))
                allowed_from = {
                    "save_draft": {"draft", "returned"},
                    "return": {"submitted"},
                    "submit": {"draft", "returned"},
                    "complete": {"submitted"},
                }
                if current_contract.status not in allowed_from[command.transition]:
                    raise BusinessValidationError(
                        "approval_transition_invalid",
                        "当前审批状态不允许执行该 transition。",
                        field="transition",
                        details={
                            "status": current_contract.status,
                            "transition": command.transition,
                        },
                    )
                if command.transition == "complete":
                    if command.requested_by == "business":
                        raise BusinessValidationError(
                            "approval_role_forbidden",
                            "业务角色不能完成最终审批。",
                            field="requestedBy",
                        )
                if command.transition == "return" and command.requested_by == "business":
                    raise BusinessValidationError(
                        "approval_role_forbidden",
                        "业务角色不能执行退回。",
                        field="requestedBy",
                    )
                status = {
                    "save_draft": "draft",
                    "return": "returned",
                    "submit": "submitted",
                    "complete": "completed",
                }[command.transition]
                now = utc_now()
                stored = ApprovalState(
                    project_id=project_id,
                    state=status,
                    version=current_contract.version + 1,
                    decision_grade=None,
                    updated_at=now,
                    updated_by=command.requested_by,
                )
                self.repository.put_approval_state(stored, connection)
                policy_ids = tuple(
                    result.id
                    for result in self._latest_policy_results(
                        self.repository.list_policy_results(project_id, connection)
                    ).values()
                )
                transition = ApprovalTransition(
                    id=new_id("approval-transition"),
                    project_id=project_id,
                    sequence=self.repository.next_approval_sequence(
                        project_id, connection
                    ),
                    from_state=current_contract.status,
                    to_state=status,
                    actor_role=command.requested_by,
                    reason=command.reason.strip(),
                    policy_result_ids=policy_ids,
                    created_at=now,
                )
                self.repository.create_approval_transition(transition, connection)
                self._append_audit(
                    connection,
                    project_id=project_id,
                    action="approval_transition",
                    aggregate_type="approval",
                    aggregate_id=project_id,
                    actor=command.requested_by,
                    payload={
                        "transitionId": transition.id,
                        "from": current_contract.status,
                        "to": status,
                        "expectedVersion": command.expected_version,
                        "policyResultIds": list(policy_ids),
                    },
                    created_at=now,
                )
                return self._approval_contract(project_id, connection)

            outcome = self._idempotent(
                connection,
                key=idempotency_key,
                operation=operation,
                request_payload=command,
                response_model=ApprovalStateContract,
                write=write,
            )
        if isinstance(outcome, ServiceError):
            raise outcome
        return outcome


def create_workbench_service(
    settings: Settings,
    *,
    generator: WorkbenchGeneratorAdapter | None = None,
) -> WorkbenchService:
    repository = SQLiteStateRepository(settings.database_path)
    adapter = generator or discover_generator_adapter(settings)
    try:
        SeedService(repository, adapter, settings.import_root).seed_once()
    except BaseException:
        repository.close()
        raise
    service = WorkbenchService(repository, adapter, settings)
    service.upgrade_seeded_p5_material_packs()
    service.data_pack.ensure_seed_records()
    service.ensure_p5_intelligence_seed()
    return service


__all__ = ["WorkbenchService", "create_workbench_service"]

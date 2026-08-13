from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.contracts.project_selection import ProjectCatalogItem
from app.contracts.material_schema import MaterialFieldSchema
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
from app.contracts.workbench import (
    ApprovalState,
    ApprovalTransitionInput,
    BusinessAnswerCommand,
    BusinessCorrectionCommand,
    BusinessCorrectionResult,
    CollaborationSubmissionResult,
    CommonReviewEvent,
    DimensionId,
    DimensionSeriesRequest,
    DimensionSeriesResponse,
    EvidenceSelectionResolution,
    HardConstraintResult,
    Material,
    ReviewEvidenceSelectionGroup,
    RiskAnswerCommand,
    RiskQuestionCommand,
    WorkbenchProject,
)


@runtime_checkable
class WorkbenchServicePort(Protocol):
    """Authoritative integration surface implemented by P4-Back-2.

    All returned mappings must validate against the declared model. The HTTP
    layer performs no business calculation and never manufactures IDs,
    sequences, timestamps or versions.
    """

    def list_projects(self) -> list[ProjectCatalogItem]: ...

    def get_workbench(self, project_id: str) -> WorkbenchProject: ...

    def list_materials(self, project_id: str) -> list[Material]: ...

    def get_material(self, project_id: str, material_id: str) -> Material: ...

    def get_material_field_schema(self, project_id: str) -> MaterialFieldSchema: ...

    async def upload_material_pack(self, project_id: str, file_name: str, content_length: int | None, stream: object): ...

    def get_material_original(self, project_id: str, material_id: str): ...

    def preflight_material_import(self, project_id: str, command: ImportManifestRequest) -> MaterialImportPreflight: ...

    def execute_material_import(self, project_id: str, command: ExecuteImportManifestRequest, *, idempotency_key: str) -> MaterialImportResult: ...

    def run_material_intelligence(self, project_id: str, material_id: str, command: MaterialIntelligenceRunCommand, *, idempotency_key: str) -> StoredMaterialIntelligence: ...

    def get_material_intelligence(self, project_id: str, material_id: str) -> StoredMaterialIntelligence: ...

    def get_material_scene_spec(self, project_id: str, material_id: str) -> StoredSceneSpec: ...

    def confirm_material_candidate(self, project_id: str, candidate_id: str, command: CandidateConfirmationCommand, *, idempotency_key: str) -> CandidateConfirmationResult: ...

    def resolve_evidence(
        self,
        project_id: str,
        selection_group: ReviewEvidenceSelectionGroup,
    ) -> EvidenceSelectionResolution: ...

    def query_dimension_series(
        self,
        project_id: str,
        dimension_id: DimensionId,
        request: DimensionSeriesRequest,
    ) -> DimensionSeriesResponse: ...

    def submit_business_correction(
        self,
        project_id: str,
        fact_key: str,
        command: BusinessCorrectionCommand,
        *,
        idempotency_key: str,
    ) -> BusinessCorrectionResult: ...

    def submit_risk_question(
        self,
        project_id: str,
        command: RiskQuestionCommand,
        *,
        idempotency_key: str,
    ) -> CommonReviewEvent: ...

    def submit_business_answer(
        self,
        project_id: str,
        command: BusinessAnswerCommand,
        *,
        idempotency_key: str,
    ) -> CollaborationSubmissionResult: ...

    def submit_risk_answer(
        self,
        project_id: str,
        command: RiskAnswerCommand,
        *,
        idempotency_key: str,
    ) -> CollaborationSubmissionResult: ...

    def list_review_events(self, project_id: str) -> list[CommonReviewEvent]: ...

    def list_policy_results(self, project_id: str) -> list[HardConstraintResult]: ...

    def get_approval_state(self, project_id: str) -> ApprovalState: ...

    def transition_approval(
        self,
        project_id: str,
        command: ApprovalTransitionInput,
        *,
        idempotency_key: str,
    ) -> ApprovalState: ...

    def close(self) -> None: ...

import type {
  ApprovalState,
  CommonReviewEvent,
  FactValue,
  FactVersion,
  HardConstraintResult,
  NormalizedBBox,
} from "./workbench";

export type DataClassification = "authorized_customer" | "public_reference" | "synthetic_demo";
export type MaterialIntelligenceTaskGoal = "observe" | "extract_field_candidates" | "identify_unresolved" | "scene_spec";
export type MaterialMediaKind = "image" | "pdf" | "excel" | "document" | "media";

interface BaseSourceAnchor {
  id: string;
  materialId: string;
  materialVersionId: string;
  contentHash: string;
}

export type SourceAnchor =
  | (BaseSourceAnchor & { kind: "image"; page: 1; bbox: NormalizedBBox; polygon?: Array<{ x: number; y: number }> | null; ocrTokenIds: string[]; charStart?: number | null; charEnd?: number | null })
  | (BaseSourceAnchor & { kind: "pdf"; page: number; bbox: NormalizedBBox; polygon?: Array<{ x: number; y: number }> | null; ocrTokenIds: string[]; charStart?: number | null; charEnd?: number | null })
  | (BaseSourceAnchor & { kind: "excel"; sheet: string; range: string })
  | (BaseSourceAnchor & { kind: "document"; paragraphId: string; runId: string; renderedPage: number; renderedPageBbox: NormalizedBBox })
  | (BaseSourceAnchor & { kind: "media"; startSeconds: number; endSeconds: number; startFrame: number; endFrame: number; bbox: NormalizedBBox });

export interface MaterialObservation {
  id: string;
  kind: "content_summary" | "visual_detail" | "ocr_text" | "structure";
  text: string;
  sourceAnchorIds: string[];
}

export interface ExtractedFieldCandidate {
  id: string;
  fieldKey: string;
  label: string;
  value: FactValue;
  unit: string | null;
  status: "candidate" | "needs_review" | "conflicting";
  sourceAnchorIds: string[];
}

export interface UnresolvedMaterialItem {
  id: string;
  kind: "missing_material" | "unreadable_content" | "ambiguous_content" | "cross_source_conflict" | "manual_review";
  question: string;
  reason: string;
  requiresHumanReview: true;
  sourceAnchorIds: string[];
}

export interface SceneVector3 { x: number; y: number; z: number }
export interface SceneObject {
  id: string;
  kind: "box" | "plane" | "marker" | "label";
  regionId: string;
  position: SceneVector3;
  size: SceneVector3;
  rotation: SceneVector3;
}
export interface SceneHotspot {
  id: string;
  objectId: string;
  regionId: string;
  sourceAnchorId: string;
}
export interface SceneSpec {
  cameraPreset: "perspective" | "front" | "side" | "top";
  objects: SceneObject[];
  hotspots: SceneHotspot[];
}

export interface MaterialIntelligenceResult {
  projectId: string;
  materialId: string;
  materialVersionId: string;
  contentHash: string;
  mediaKind: MaterialMediaKind;
  contextVersion: string;
  dataClassification: DataClassification;
  status: "completed" | "needs_review" | "unavailable";
  confidence: number;
  observations: MaterialObservation[];
  extractedFieldCandidates: ExtractedFieldCandidate[];
  unresolvedItems: UnresolvedMaterialItem[];
  sourceAnchors: SourceAnchor[];
  sceneSpec: SceneSpec | null;
  modelInfo: { provider: string; model: string; modelVersion: string | null } | null;
  promptVersion: string;
  schemaVersion: "1.0";
  inputHash: string;
  advisoryOnly: true;
  isSimulated: boolean;
  dataStatus: "simulated" | "provider_generated_unverified" | "unavailable";
  source: string;
  disclaimer: string;
}

export interface StoredMaterialIntelligence {
  runId: string;
  result: MaterialIntelligenceResult;
  candidateIds: string[];
  evidenceRefs: string[];
  createdAt: string;
}

export interface StoredSceneSpec {
  sceneId: string;
  projectId: string;
  materialId: string;
  materialVersionId: string;
  sourceAnchorIds: string[];
  spec: SceneSpec;
  isSimulated: boolean;
  createdAt: string;
}

export interface MaterialImportPreview {
  materialId: string;
  materialVersionId: string;
  kind: "excel" | "pdf" | "image" | "media" | "scene";
  contentHash: string;
  classification: DataClassification;
  authorizationRef: string;
  sourceRef: string;
}

/** 上传 ZIP 后由服务端生成的受控清单引用；文件内容不会进入 JSON 请求体。 */
export interface MaterialUploadReceipt {
  projectId: string;
  uploadId: string;
  fileName: string;
  byteSize: number;
  sha256: string;
  manifestRef: string;
  isSimulated: boolean;
}

export interface MaterialImportPreflight {
  projectId: string;
  manifestRef: string;
  manifestHash: string;
  projectVersion: number;
  items: MaterialImportPreview[];
  isSimulated: boolean;
}
export interface MaterialImportResult extends MaterialImportPreflight {
  importId: string;
  importedCount: number;
  replayed: boolean;
}

export interface MaterialIntelligenceRunInput {
  projectId: string;
  materialId: string;
  materialVersionId: string;
  contextVersion: string;
  taskGoals: MaterialIntelligenceTaskGoal[];
  expectedVersion: number;
  idempotencyKey: string;
  providerMode?: "disabled" | "synthetic" | "real";
}

export interface CandidateConfirmationInput {
  projectId: string;
  candidateId: string;
  fromFactVersionId: string;
  expectedVersion: number;
  reason: string;
  proposedValue?: FactValue | null;
  idempotencyKey: string;
}

export interface CandidateConfirmationResult {
  confirmationId: string;
  candidateId: string;
  factVersion: FactVersion;
  event: CommonReviewEvent;
  policyResults: HardConstraintResult[];
  approval: ApprovalState;
}

/** Back persists every SourceAnchor as a stable evidence reference by contract. */
export function evidenceRefForSourceAnchor(sourceAnchorId: string) {
  return `ev-mi-${sourceAnchorId}`;
}

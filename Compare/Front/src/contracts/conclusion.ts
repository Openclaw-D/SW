import type {
  DecisionGrade,
  DimensionId,
  EvidenceLocationStatus,
  LocalMaterialStatus,
  RiskLevel,
  ScoreGrade,
} from "./workbench";

export type ConclusionAgentRole = "business" | "risk" | "leadership";

export interface ConclusionOverall {
  riskLevel: RiskLevel;
  scoreGrade: ScoreGrade;
  decisionGrade: DecisionGrade;
  confidence: number;
  summary: string;
}

export interface ConclusionDimension {
  dimensionId: DimensionId;
  name: string;
  score: number;
  scoreGrade: ScoreGrade;
  decisionGrade: DecisionGrade;
  confidence: number;
  summary: string;
  conclusion: string;
}

export interface ConclusionEvidenceItem {
  evidenceRef: string;
  label: string;
  locationStatus: EvidenceLocationStatus;
  materialStatus: LocalMaterialStatus;
  locatorSummary: string;
}

export interface ConclusionOpenItem {
  id: string;
  source: "formal_review" | "risk_summary" | "policy";
  title: string;
  detail: string;
  status: "open" | "pending_gate" | "manual_review" | "block";
  dimensionId: DimensionId | null;
  responsibleParty: "business" | "risk" | "joint";
  nextAction: string;
  evidenceRefs: string[];
}

export interface ConclusionGateSummary {
  approvalStatus: "draft" | "returned" | "submitted" | "completed";
  approvalVersion: number;
  hardGateStatus: "pass" | "block" | "manual_review";
  blockingRuleIds: string[];
  riskVeto: boolean;
  riskVetoRuleIds: string[];
  policyCounts: { passed: number; blocked: number; manualReview: number };
  completionAllowed: boolean;
}

export interface ConclusionAgentCitation {
  evidenceRef: string;
  dimensionId: DimensionId;
  reviewTargetId: string | null;
  factVersionId: string | null;
}

export interface ConclusionAgentAdvice {
  id: string;
  projectId: string;
  threadId: string;
  sequence: number;
  role: ConclusionAgentRole;
  authorType: "agent";
  kind: "agent_reply";
  content: string;
  citations: ConclusionAgentCitation[];
  generatedContent: {
    replyText: string;
    observations: string[];
    questions: string[];
    citations: ConclusionAgentCitation[];
    scopeStatus: "in_scope" | "needs_clarification" | "out_of_scope";
    disposition: "answer" | "request_information" | "escalate" | "decline_out_of_scope";
  };
  execution: {
    mode: "disabled" | "synthetic" | "real";
    providerId: string | null;
    modelId: string | null;
    promptVersion: string | null;
    inputHash: string;
    contextVersion: string;
    outputHash: string | null;
    advisoryOnly: true;
    isSimulated: boolean;
    dataStatus: "simulated" | "provider_generated_unverified" | "unavailable";
    source: string;
    disclaimer: string;
  };
  replyToMessageId: string | null;
  runId: string;
  createdAt: string;
  immutable: true;
  advisoryOnly: true;
  isSimulated: boolean;
}

export interface ConclusionCollaboration {
  hasThread: boolean;
  threadId: string | null;
  threadTitle: string | null;
  threadStatus: "active" | "closed" | "rejected" | null;
  focusRole: ConclusionAgentRole | null;
  threadVersion: number | null;
  messageCount: number;
  agentMessageCount: number;
  focusEventCount: number;
  focusTransitionCount: number;
  latestAdvice: ConclusionAgentAdvice | null;
}

export interface ProjectConclusionReport {
  schemaVersion: "1.0";
  projectId: string;
  projectName: string;
  generatedAt: string;
  overall: ConclusionOverall;
  dimensions: ConclusionDimension[];
  evidenceTotal: number;
  evidenceStatusCounts: Record<EvidenceLocationStatus, number>;
  keyEvidence: ConclusionEvidenceItem[];
  openItems: ConclusionOpenItem[];
  gates: ConclusionGateSummary;
  collaboration: ConclusionCollaboration;
  humanConfirmation: {
    required: true;
    status: "human_action_required" | "ready_for_human" | "completed";
    checks: string[];
    boundary: string;
  };
  aiValue: {
    sourceSectionsConsolidated: string[];
    evidenceItemsOrganized: number;
    openItemsSurfaced: number;
    followUpQuestionsSurfaced: number;
    traceableReferenceCount: number;
    advisoryMessagesAvailable: number;
    focusTransitionsRecorded: number;
    summary: string;
  };
  advisoryOnly: true;
  isSimulated: boolean;
  dataStatus: "simulated" | "provider_generated_unverified";
  source: "server_conclusion_projection";
  disclaimer: string;
}

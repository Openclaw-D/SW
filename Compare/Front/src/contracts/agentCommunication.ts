import type { ReviewEvidenceTarget } from "./workbench";

export type AgentRole = "business" | "risk" | "leadership";
export type ChatAgentRole = Exclude<AgentRole, "leadership">;
export type AgentResponseDepth = "brief" | "balanced" | "detailed";
export type AgentResponseFocus = "balanced" | "risk" | "evidence" | "next_steps";
export interface AgentResponsePreferences {
  responseDepth: AgentResponseDepth;
  responseFocus: AgentResponseFocus;
  customGuidance: string;
}
export type AgentThreadStatus = "active" | "closed" | "rejected";

export interface AgentCitation {
  evidenceRef: string;
  dimensionId: ReviewEvidenceTarget["dimensionId"];
  reviewTargetId: string | null;
  factVersionId: string | null;
}

export interface GeneratedAgentContent {
  replyText: string;
  observations: string[];
  questions: string[];
  citations: AgentCitation[];
  scopeStatus: "in_scope" | "needs_clarification" | "out_of_scope";
  disposition: "answer" | "request_information" | "escalate" | "decline_out_of_scope";
}

export interface AgentExecutionMetadata {
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
}

export interface AgentMessage {
  id: string;
  projectId: string;
  threadId: string;
  sequence: number;
  role: AgentRole;
  authorType: "human" | "agent";
  kind: "user_input" | "agent_reply";
  content: string;
  citations: AgentCitation[];
  generatedContent: GeneratedAgentContent | null;
  execution: AgentExecutionMetadata | null;
  replyToMessageId: string | null;
  runId: string | null;
  createdAt: string;
  immutable: true;
  advisoryOnly: true;
  isSimulated: boolean;
}

export interface AgentThread {
  id: string;
  projectId: string;
  title: string;
  version: number;
  status: AgentThreadStatus;
  focusRole: AgentRole;
  createdByRole: AgentRole;
  closedReason: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AgentFocusEvent {
  id: string;
  projectId: string;
  threadId: string;
  sequence: number;
  kind: "thread_created" | "thread_migrated" | "focus_transferred" | "focus_returned" | "thread_closed" | "thread_rejected" | "thread_reopened";
  fromFocusRole: AgentRole | null;
  toFocusRole: AgentRole;
  actorRole: AgentRole;
  reason: string;
  expectedVersion: number;
  resultingVersion: number;
  createdAt: string;
  immutable: true;
}

export interface AgentTurnResult {
  turnId: string;
  runId: string;
  status: "completed" | "needs_review" | "out_of_scope" | "unavailable";
  focusRole: AgentRole;
  currentFocusRole: AgentRole;
  messages: AgentMessage[];
  nextExpectedVersion: number;
  execution: AgentExecutionMetadata;
  advisoryOnly: true;
  schemaVersion: "2.0";
}

/**
 * Ephemeral UI state for an explicit Agent mention. This is deliberately a
 * progress summary, not hidden chain-of-thought or an authoritative decision.
 */
export interface AgentActivityState {
  sourceMessageId: string;
  role: ChatAgentRole;
  phase: "thinking" | "failed";
  startedAt: string;
  detail: string;
}

export type CollaborationContextReference =
  | { kind: "agent_message"; id: string; label: string; createdAt: string }
  | { kind: "review_event"; id: string; label: string; createdAt: string }
  | {
      kind: "material_annotation";
      id: string;
      label: string;
      createdAt: string;
      materialId: string;
      materialVersionId: string;
      locatorMethod: "element" | "ocr_region";
      matchStatus: "exact" | "confirmed" | "pending";
      sourceAnchorId: string | null;
      region: { x: number; y: number; width: number; height: number } | null;
      snapshotDataUrl: string | null;
      evidenceTargets: ReviewEvidenceTarget[];
    };

export interface CreateAgentThreadCommand {
  projectId: string;
  title: string;
  principal: "business";
  idempotencyKey: string;
}

export interface TransitionAgentFocusCommand {
  projectId: string;
  threadId: string;
  principal: AgentRole;
  toFocusRole: AgentRole;
  expectedVersion: number;
  reason: string;
  idempotencyKey: string;
}

export interface ExecuteAgentTurnCommand {
  projectId: string;
  threadId: string;
  principal: AgentRole;
  targetAgentRole: ChatAgentRole;
  sourceMessageId: string;
  instruction: string;
  replyToMessageId: string | null;
  evidenceTargets: ReviewEvidenceTarget[];
  expectedVersion: number;
  locale: "zh-CN";
  responseDepth: AgentResponseDepth;
  responseFocus: AgentResponseFocus;
  customGuidance: string;
  idempotencyKey: string;
}

export interface PostAgentMessageCommand {
  projectId: string;
  threadId: string;
  principal: AgentRole;
  content: string;
  replyToMessageId: string | null;
  evidenceTargets: ReviewEvidenceTarget[];
  locale: "zh-CN";
  idempotencyKey: string;
}

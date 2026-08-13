import type { ReviewEvidenceTarget } from "./workbench";

export type AgentRole = "business" | "risk" | "leadership";
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
  runId: string;
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

export type CollaborationContextReference =
  | { kind: "agent_message"; id: string; label: string; createdAt: string }
  | { kind: "review_event"; id: string; label: string; createdAt: string };

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
  instruction: string;
  replyToMessageId: string | null;
  evidenceTargets: ReviewEvidenceTarget[];
  expectedVersion: number;
  locale: "zh-CN";
  idempotencyKey: string;
}

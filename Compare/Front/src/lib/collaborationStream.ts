import type { AgentFocusEvent, AgentMessage, AgentRole } from "../contracts/agentCommunication";
import type { DimensionId, MappedCommonReviewEvent, ReviewEvidenceTarget } from "../contracts/workbench";

export type CollaborationStreamKind = "material_reference" | "pending_question" | "confirmed_conclusion" | "focus_event";

export interface CollaborationStreamItem {
  id: string;
  kind: CollaborationStreamKind;
  createdAt: string;
  sequence: number;
  actorRole: AgentRole | "system";
  actorLabel: string;
  title: string;
  summary: string;
  sourceLabel: string;
  dimensionId: DimensionId | null;
  evidenceTargets: ReviewEvidenceTarget[];
  pending: boolean;
  reviewEventId: string | null;
  agentMessageId: string | null;
}

const explicitConclusionTypes = new Set(["business_answer_submitted", "risk_answer_submitted"]);

function citationTargets(message: AgentMessage): ReviewEvidenceTarget[] {
  return message.citations.map((citation) => ({
    evidenceRef: citation.evidenceRef,
    evidenceRefs: [citation.evidenceRef],
    dimensionId: citation.dimensionId,
    reviewTargetId: citation.reviewTargetId,
    factVersionId: citation.factVersionId,
  }));
}

function fromReviewEvent(event: MappedCommonReviewEvent): CollaborationStreamItem | null {
  const hasMaterialReference = event.evidenceTargets.length > 0;
  const pending = event.issueStatus === "open";
  const explicitConclusion = explicitConclusionTypes.has(event.eventType);
  if (!hasMaterialReference && !pending && !explicitConclusion) return null;
  return {
    id: `review:${event.id}`,
    kind: pending ? "pending_question" : explicitConclusion ? "confirmed_conclusion" : "material_reference",
    createdAt: event.createdAt,
    sequence: event.sequence,
    actorRole: event.actor,
    actorLabel: event.actorLabel,
    title: event.title,
    summary: event.summary,
    sourceLabel: `共同审查记录 · ${event.eventType} · #${event.sequence}`,
    dimensionId: event.dimensionId,
    evidenceTargets: event.evidenceTargets,
    pending,
    reviewEventId: event.id,
    agentMessageId: null,
  };
}

function fromAgentMessage(message: AgentMessage): CollaborationStreamItem | null {
  if (message.authorType !== "agent" || !message.generatedContent) return null;
  const targets = citationTargets(message);
  const questions = message.generatedContent.questions;
  if (!targets.length && !questions.length) return null;
  const provider = message.execution?.providerId ?? "provider-unavailable";
  const model = message.execution?.modelId ?? "model-unavailable";
  return {
    id: `agent:${message.id}`,
    kind: questions.length ? "pending_question" : "material_reference",
    createdAt: message.createdAt,
    sequence: message.sequence,
    actorRole: message.role,
    actorLabel: `${message.role === "business" ? "业务" : message.role === "risk" ? "风控" : "系统"} Agent`,
    title: questions.length ? "Agent 明确待回复问题" : "带材料引用的 Agent 建议",
    summary: questions.length ? questions.join("；") : message.content,
    sourceLabel: `Agent run · ${message.runId ?? "run-unavailable"} · ${provider}/${model}`,
    dimensionId: targets[0]?.dimensionId ?? null,
    evidenceTargets: targets,
    pending: questions.length > 0,
    reviewEventId: null,
    agentMessageId: message.id,
  };
}

function fromFocusEvent(event: AgentFocusEvent): CollaborationStreamItem {
  const roleLabel = (role: AgentRole | null) => role === "business" ? "业务" : role === "risk" ? "风控" : role === "leadership" ? "系统" : "无";
  return {
    id: `focus:${event.id}`,
    kind: "focus_event",
    createdAt: event.createdAt,
    sequence: event.sequence,
    actorRole: event.actorRole,
    actorLabel: `${roleLabel(event.actorRole)}角色`,
    title: event.kind === "focus_transferred" ? "焦点接管" : event.kind === "focus_returned" ? "焦点返回业务" : "会话焦点事件",
    summary: `${roleLabel(event.fromFocusRole)} → ${roleLabel(event.toFocusRole)}；${event.reason}`,
    sourceLabel: `服务端焦点事件 · ${event.kind} · #${event.sequence}`,
    dimensionId: null,
    evidenceTargets: [],
    pending: false,
    reviewEventId: null,
    agentMessageId: null,
  };
}

export function compareCollaborationStreamItems(left: CollaborationStreamItem, right: CollaborationStreamItem) {
  return left.createdAt.localeCompare(right.createdAt) || left.sequence - right.sequence || left.id.localeCompare(right.id);
}

export function buildCollaborationStream(reviewEvents: MappedCommonReviewEvent[], agentMessages: AgentMessage[], focusEvents: AgentFocusEvent[]) {
  return [
    ...reviewEvents.flatMap((event) => {
      const item = fromReviewEvent(event);
      return item ? [item] : [];
    }),
    ...agentMessages.flatMap((message) => {
      const item = fromAgentMessage(message);
      return item ? [item] : [];
    }),
    ...focusEvents.map(fromFocusEvent),
  ].sort(compareCollaborationStreamItems);
}

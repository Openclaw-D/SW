from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.contracts.agent_communication import (
    AGENT_COMMUNICATION_DISCLAIMER,
    AgentApprovalContext,
    AgentCitation,
    AgentDimensionContext,
    AgentEvidenceContext,
    AgentFactContext,
    AgentPolicyContext,
    AgentProjectContext,
    AgentProviderContext,
    AgentRole,
    AgentTurnRequest,
    AgentVisibleMessageContext,
)
from app.contracts.errors import BusinessValidationError, NotFoundError
from app.contracts.ports import WorkbenchServicePort
from app.ports.agent_communication import AgentAssembledInput


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class AgentContextAssembler:
    """Build a bounded, project-scoped and read-only model context."""

    def __init__(self, workbench: WorkbenchServicePort) -> None:
        self.workbench = workbench

    def assemble(
        self,
        *,
        project_id: str,
        thread_id: str,
        target_role: AgentRole,
        request: AgentTurnRequest,
        visible_messages: Sequence[Mapping[str, Any]],
    ) -> tuple[AgentProviderContext, AgentAssembledInput]:
        snapshot = self.workbench.get_workbench(project_id)
        policies = self.workbench.list_policy_results(project_id)
        approval = self.workbench.get_approval_state(project_id)

        evidence_by_id = {item.id: item for item in snapshot.evidence}
        facts_by_id = {item.id: item for item in snapshot.facts}
        allowlist: list[AgentCitation] = []
        selected_evidence: list[AgentEvidenceContext] = []
        selected_facts: list[AgentFactContext] = []
        selected_evidence_ids: set[str] = set()
        selected_fact_ids: set[str] = set()
        for target in request.evidence_targets:
            evidence = evidence_by_id.get(target.evidence_ref)
            if evidence is None:
                raise NotFoundError(
                    "agent_evidence_not_found",
                    "Agent 请求引用的证据不存在或不属于当前项目。",
                    details={"evidenceRef": target.evidence_ref},
                )
            for evidence_ref in target.evidence_refs or [target.evidence_ref]:
                if evidence_ref not in evidence_by_id:
                    raise NotFoundError(
                        "agent_evidence_not_found",
                        "Agent 请求引用的证据不存在或不属于当前项目。",
                        details={"evidenceRef": evidence_ref},
                    )
            if target.fact_version_id is not None:
                fact = facts_by_id.get(target.fact_version_id)
                if fact is None or fact.dimension_id != target.dimension_id:
                    raise BusinessValidationError(
                        "agent_fact_binding_invalid",
                        "Agent 请求中的 factVersionId 与当前项目或维度不匹配。",
                        field="evidenceTargets",
                    )
                if target.evidence_ref not in fact.evidence_refs:
                    raise BusinessValidationError(
                        "agent_fact_binding_invalid",
                        "Agent 请求中的证据不支持指定 FactVersion。",
                        field="evidenceTargets",
                    )
            allowlist.append(AgentCitation.from_evidence_target(target))
            if evidence.id not in selected_evidence_ids:
                selected_evidence_ids.add(evidence.id)
                locator_summary = None
                if evidence.locator is not None:
                    locator_summary = _canonical_json(
                        evidence.locator.model_dump(by_alias=True, mode="json")
                    )
                selected_evidence.append(
                    AgentEvidenceContext(
                        evidence_ref=evidence.id,
                        label=evidence.label,
                        dimension_id=target.dimension_id,
                        location_status=evidence.location_status,
                        material_status=evidence.material_status,
                        locator_summary=locator_summary,
                    )
                )
            if target.fact_version_id is not None:
                fact = facts_by_id[target.fact_version_id]
                if fact.id not in selected_fact_ids:
                    selected_fact_ids.add(fact.id)
                    selected_facts.append(
                        AgentFactContext(
                            fact_version_id=fact.id,
                            fact_key=fact.fact_key,
                            dimension_id=fact.dimension_id,
                            label=fact.label,
                            value_text="未知" if fact.value is None else str(fact.value),
                            unit=fact.unit,
                            evidence_refs=fact.evidence_refs,
                        )
                    )

        visible = [self._visible_message(item) for item in visible_messages[-40:]]
        policy_contexts: list[AgentPolicyContext] = []
        allowed_citations = {item.stable_tuple(): item for item in allowlist}
        for item in policies:
            citations = []
            for target in item.evidence_targets:
                citation = AgentCitation.from_evidence_target(target)
                if citation.stable_tuple() in allowed_citations:
                    citations.append(citation)
            policy_contexts.append(
                AgentPolicyContext(
                    policy_result_id=item.id,
                    rule_id=item.rule_id,
                    title=item.title,
                    result=item.result,
                    explanation=item.explanation,
                    next_action=item.next_action,
                    citations=citations,
                )
            )

        manifest = {
            "projectId": project_id,
            "threadId": thread_id,
            "targetRole": target_role.value,
            "project": snapshot.project.model_dump(by_alias=True, mode="json"),
            "dimensions": [
                {
                    "dimensionId": item.id,
                    "name": item.name,
                    "summary": item.summary,
                }
                for item in snapshot.dimensions
            ],
            "policies": [item.model_dump(by_alias=True, mode="json") for item in policy_contexts],
            "selectedEvidence": [
                item.model_dump(by_alias=True, mode="json") for item in selected_evidence
            ],
            "selectedFacts": [
                item.model_dump(by_alias=True, mode="json") for item in selected_facts
            ],
            "approval": approval.model_dump(by_alias=True, mode="json"),
            "messages": [item.model_dump(by_alias=True, mode="json") for item in visible],
            "citationAllowlist": [item.model_dump(by_alias=True, mode="json") for item in allowlist],
            "instruction": request.instruction,
        }
        context_version = _sha256(manifest)
        context = AgentProviderContext(
            project_id=project_id,
            thread_id=thread_id,
            target_role=target_role,
            context_version=context_version,
            project_summary=AgentProjectContext(
                project_id=project_id,
                name=snapshot.project.name,
                summary=(
                    f"当前项目共有 {snapshot.project.material_count} 份材料，"
                    f"共同审查未结事项 {snapshot.project.collaboration_issue_count} 项。"
                ),
                is_simulated=snapshot.project.is_simulated,
            ),
            dimension_summaries=[
                AgentDimensionContext(
                    dimension_id=item.id,
                    name=item.name,
                    summary=item.summary,
                )
                for item in snapshot.dimensions
            ],
            policy_results=policy_contexts,
            selected_evidence=selected_evidence,
            selected_facts=selected_facts,
            approval_state=AgentApprovalContext(
                version=approval.version,
                status=approval.status,
                hard_gate_status=approval.hard_gate_status,
                blocking_rule_ids=approval.blocking_rule_ids,
                risk_veto=approval.risk_veto,
                summary=(
                    "审批状态仅供只读参考；任何 Agent 和系统通信控制均不能覆盖 hard gate。"
                ),
            ),
            recent_visible_messages=visible,
            citation_allowlist=allowlist,
            current_instruction=request.instruction,
            is_context_simulated=snapshot.project.is_simulated,
            disclaimer=AGENT_COMMUNICATION_DISCLAIMER,
        )
        provider_payload = {
            "schemaVersion": "2.0",
            "request": request.model_dump(by_alias=True, mode="json"),
            "context": context.model_dump(by_alias=True, mode="json"),
        }
        input_hash = _sha256(provider_payload)
        return context, AgentAssembledInput(
            payload=provider_payload,
            input_hash=input_hash,
            estimated_input_tokens=max(1, len(_canonical_json(provider_payload)) // 4),
        )

    @staticmethod
    def _visible_message(item: Mapping[str, Any]) -> AgentVisibleMessageContext:
        def value(name: str, alias: str | None = None) -> Any:
            if name in item:
                return item[name]
            return item.get(alias or name)

        return AgentVisibleMessageContext(
            message_id=value("message_id", "id"),
            sequence=value("sequence"),
            role=value("role"),
            author_type=value("author_type", "authorType"),
            content=value("content"),
        )


__all__ = ["AgentContextAssembler"]

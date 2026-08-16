from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import Counter
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.contracts.agent_communication import (
    AGENT_COMMUNICATION_DISCLAIMER,
    AgentCitation,
    AgentDataStatus,
    AgentChatMessageRequest,
    AgentExecutionMetadata,
    AgentFocusEvent,
    AgentFocusTransitionRequest,
    AgentMessage,
    AgentMode,
    AgentRole,
    AgentRunRecord,
    AgentRunStatus,
    AgentScopeStatus,
    AgentThread,
    AgentThreadControlRequest,
    AgentThreadCreateRequest,
    AgentTurnRequest,
    AgentTurnResult,
    AgentTurnStatus,
    GeneratedAgentContent,
    validate_agent_provider_context,
    validate_generated_agent_content,
)
from app.contracts.errors import ConflictError, ForbiddenError, ServiceError
from app.contracts.conclusion import (
    ConclusionAiValue,
    ConclusionCollaboration,
    ConclusionDimension,
    ConclusionEvidenceItem,
    ConclusionGateSummary,
    ConclusionHumanConfirmation,
    ConclusionOpenItem,
    ConclusionOverall,
    ConclusionPolicyCounts,
    ProjectConclusionReport,
)
from app.contracts.ports import WorkbenchServicePort
from app.models import utc_now
from app.ports.agent_communication import AgentProviderPort
from app.services.agent_communication.context import AgentContextAssembler
from app.services.agent_communication.repository import AgentCommunicationRepository


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _locator_summary(evidence: Any) -> str:
    locator = evidence.locator
    if locator is None:
        return {
            "pending": "待定位",
            "unverifiable": "无法核验",
            "version_mismatch": "材料版本不匹配",
        }.get(evidence.location_status, "未定位")
    if locator.kind == "excel":
        return f"{locator.sheet}!{locator.range}"
    if locator.kind == "pdf":
        return f"第 {locator.page} 页"
    if locator.kind == "image":
        return "图像区域"
    if locator.kind == "document":
        return f"渲染第 {locator.rendered_page} 页"
    if locator.kind == "media":
        return f"{locator.start_seconds:g}–{locator.end_seconds:g} 秒"
    if locator.kind == "scene":
        return f"场景点 {len(locator.point_ids)} 个"
    return "已定位"


class AgentCommunicationService:
    """Project-chat orchestrator with explicit Agent routing and no authority writes."""

    def __init__(
        self,
        *,
        workbench: WorkbenchServicePort,
        repository: AgentCommunicationRepository,
        mode: AgentMode = AgentMode.SYNTHETIC,
        providers: Mapping[AgentRole, AgentProviderPort] | None = None,
        timeout_seconds: float = 30,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.workbench = workbench
        self.repository = repository
        self.mode = mode
        self.providers = dict(providers or {})
        self.timeout_seconds = timeout_seconds
        self.context_assembler = AgentContextAssembler(workbench)

    def close(self) -> None:
        self.repository.close()

    def _ensure_project(self, project_id: str) -> None:
        self.repository.require_project(project_id)

    def get_conclusion_report(self, project_id: str) -> ProjectConclusionReport:
        """Build a read-only human-decision brief from existing authoritative sources."""

        workbench = self.workbench.get_workbench(project_id)
        policies = self.workbench.list_policy_results(project_id)
        approval = self.workbench.get_approval_state(project_id)
        review_events = self.workbench.list_review_events(project_id)
        agent_snapshot = self.repository.get_latest_conclusion_snapshot(project_id)
        latest_advice = (
            None
            if agent_snapshot["latestAgentMessage"] is None
            else AgentMessage.model_validate(agent_snapshot["latestAgentMessage"])
        )

        determinations = {item.dimension_id: item for item in workbench.determinations}
        dimensions = []
        for dimension in workbench.dimensions:
            determination = determinations[dimension.id]
            dimensions.append(
                ConclusionDimension(
                    dimension_id=dimension.id,
                    name=dimension.name,
                    score=dimension.score,
                    score_grade=dimension.score_grade,
                    decision_grade=determination.decision_grade,
                    confidence=dimension.confidence,
                    summary=dimension.summary,
                    conclusion=determination.conclusion,
                )
            )

        latest_formal_events: dict[str, Any] = {}
        for event in review_events:
            current = latest_formal_events.get(event.thread_id)
            if current is None or event.sequence > current.sequence:
                latest_formal_events[event.thread_id] = event

        open_items: list[ConclusionOpenItem] = []
        for event in latest_formal_events.values():
            if event.issue_status not in {"open", "pending_gate"}:
                continue
            if event.event_type == "risk_question_submitted":
                responsible_party, next_action = "business", "业务补充证据或作出可追溯答复。"
            elif event.event_type in {"business_answer_submitted", "business_correction_submitted"}:
                responsible_party, next_action = "risk", "风控复核答复与证据后更新正式认定。"
            else:
                responsible_party, next_action = "joint", "业务与风控按正式共同审查链处理。"
            open_items.append(
                ConclusionOpenItem(
                    id=event.id,
                    source="formal_review",
                    title=event.title,
                    detail=event.summary,
                    status=event.issue_status,
                    dimension_id=event.dimension_id,
                    responsible_party=responsible_party,
                    next_action=next_action,
                    evidence_refs=event.evidence_refs,
                )
            )

        for item in workbench.risk_summary.pending_human_determinations:
            open_items.append(
                ConclusionOpenItem(
                    id=item.id,
                    source="risk_summary",
                    title=item.title,
                    detail=item.detail,
                    status="manual_review",
                    dimension_id=(
                        item.evidence_targets[0].dimension_id
                        if item.evidence_targets
                        else None
                    ),
                    responsible_party=item.responsible_party,
                    next_action=item.next_action,
                    evidence_refs=_unique(
                        [
                            evidence_ref
                            for target in item.evidence_targets
                            for evidence_ref in (target.evidence_refs or [target.evidence_ref])
                        ]
                    ),
                )
            )

        for policy in policies:
            if policy.result == "pass":
                continue
            open_items.append(
                ConclusionOpenItem(
                    id=policy.id,
                    source="policy",
                    title=policy.title,
                    detail=policy.explanation,
                    status=policy.result,
                    dimension_id=(
                        policy.primary_target.dimension_id
                        if policy.primary_target is not None
                        else None
                    ),
                    responsible_party=policy.responsible_party,
                    next_action=policy.next_action,
                    evidence_refs=_unique(
                        [
                            evidence_ref
                            for target in policy.evidence_targets
                            for evidence_ref in (target.evidence_refs or [target.evidence_ref])
                        ]
                    ),
                )
            )

        evidence_counts = Counter(item.location_status for item in workbench.evidence)
        important_refs = list(workbench.risk_summary.evidence_refs)
        important_refs.extend(
            evidence_ref for item in open_items for evidence_ref in item.evidence_refs
        )
        if latest_advice is not None:
            important_refs.extend(item.evidence_ref for item in latest_advice.citations)
        important_refs = _unique(important_refs)
        if not important_refs:
            important_refs = [item.id for item in workbench.evidence]
        evidence_by_id = {item.id: item for item in workbench.evidence}
        key_evidence = [
            ConclusionEvidenceItem(
                evidence_ref=evidence.id,
                label=evidence.label,
                location_status=evidence.location_status,
                material_status=evidence.material_status,
                locator_summary=_locator_summary(evidence),
            )
            for evidence_ref in important_refs[:20]
            if (evidence := evidence_by_id.get(evidence_ref)) is not None
        ]

        policy_counts = Counter(item.result for item in policies)
        completion_allowed = (
            approval.hard_gate_status == "pass"
            and not approval.blocking_rule_ids
            and not approval.risk_veto
            and not approval.risk_veto_rule_ids
        )
        if approval.status == "completed":
            human_status = "completed"
        elif completion_allowed and not open_items:
            human_status = "ready_for_human"
        else:
            human_status = "human_action_required"
        not_located_count = len(workbench.evidence) - evidence_counts["located"]
        human_checks = [
            f"制度 Gate：{approval.hard_gate_status}；阻断规则 {len(approval.blocking_rule_ids)} 条。",
            f"正式未决项：{len(open_items)} 条；未完成定位证据：{not_located_count} 条。",
            "负责人须在正式审批链确认结论；Agent 建议不能写入事实、制度或审批状态。",
        ]

        thread = agent_snapshot["thread"]
        collaboration = ConclusionCollaboration(
            has_thread=thread is not None,
            thread_id=None if thread is None else thread["id"],
            thread_title=None if thread is None else thread["title"],
            thread_status=None if thread is None else thread["status"],
            focus_role=None if thread is None else thread["focusRole"],
            thread_version=None if thread is None else thread["version"],
            message_count=agent_snapshot["messageCount"],
            agent_message_count=agent_snapshot["agentMessageCount"],
            focus_event_count=agent_snapshot["focusEventCount"],
            focus_transition_count=agent_snapshot["focusTransitionCount"],
            latest_advice=latest_advice,
        )
        traceable_refs = _unique(
            [item.evidence_ref for item in key_evidence]
            + [evidence_ref for item in open_items for evidence_ref in item.evidence_refs]
            + ([] if latest_advice is None else [item.evidence_ref for item in latest_advice.citations])
        )
        question_count = (
            0
            if latest_advice is None or latest_advice.generated_content is None
            else len(latest_advice.generated_content.questions)
        )
        sources = [
            "项目状态与六维认定",
            "关键证据定位",
            "正式共同审查未决项",
            "制度 Gate 与审批状态",
        ]
        if thread is not None:
            sources.append("单焦点 Agent 建议与 provenance")

        is_simulated = workbench.project.is_simulated or bool(
            latest_advice is not None and latest_advice.is_simulated
        )
        return ProjectConclusionReport(
            project_id=project_id,
            project_name=workbench.project.name,
            generated_at=utc_now(),
            overall=ConclusionOverall(
                risk_level=workbench.risk_summary.level,
                score_grade=workbench.risk_summary.score_grade,
                decision_grade=workbench.risk_summary.decision_grade,
                confidence=workbench.risk_summary.confidence,
                summary=workbench.risk_summary.summary,
            ),
            dimensions=dimensions,
            evidence_total=len(workbench.evidence),
            evidence_status_counts={
                status: evidence_counts[status]
                for status in ("located", "pending", "unverifiable", "version_mismatch")
            },
            key_evidence=key_evidence,
            open_items=open_items,
            gates=ConclusionGateSummary(
                approval_status=approval.status,
                approval_version=approval.version,
                hard_gate_status=approval.hard_gate_status,
                blocking_rule_ids=approval.blocking_rule_ids,
                risk_veto=approval.risk_veto,
                risk_veto_rule_ids=approval.risk_veto_rule_ids,
                policy_counts=ConclusionPolicyCounts(
                    passed=policy_counts["pass"],
                    blocked=policy_counts["block"],
                    manual_review=policy_counts["manual_review"],
                ),
                completion_allowed=completion_allowed,
            ),
            collaboration=collaboration,
            human_confirmation=ConclusionHumanConfirmation(
                status=human_status,
                checks=human_checks,
                boundary="系统仅整理与提示；最终结论、审批和制度 Gate 均由既有服务端规则与授权人员确认。",
            ),
            ai_value=ConclusionAiValue(
                source_sections_consolidated=sources,
                evidence_items_organized=len(key_evidence),
                open_items_surfaced=len(open_items),
                follow_up_questions_surfaced=question_count,
                traceable_reference_count=len(traceable_refs),
                advisory_messages_available=agent_snapshot["agentMessageCount"],
                focus_transitions_recorded=agent_snapshot["focusTransitionCount"],
                summary=(
                    "把分散在项目、证据、正式协同、制度 Gate 与单焦点会话中的当前状态"
                    "汇总到一个可追溯视图，减少人工整理、逐项追问和页面切换；以上数量来自"
                    "当前服务端记录，不代表自动决策、模型准确率或已实现的时间/利润收益。"
                ),
            ),
            advisory_only=True,
            is_simulated=is_simulated,
            data_status=("simulated" if is_simulated else "provider_generated_unverified"),
        )

    def create_thread(
        self,
        project_id: str,
        principal: AgentRole,
        request: AgentThreadCreateRequest,
        *,
        idempotency_key: str,
    ) -> AgentThread:
        self._ensure_project(project_id)
        request_hash = _canonical_hash(
            {
                "operation": "create_thread",
                "projectId": project_id,
                "principal": principal.value,
                "request": request.model_dump(mode="json", by_alias=True),
            }
        )
        return AgentThread.model_validate(
            self.repository.create_thread(
                project_id,
                title=request.title,
                created_by_role=principal.value,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        )

    def get_thread(self, project_id: str, thread_id: str) -> AgentThread:
        self._ensure_project(project_id)
        return AgentThread.model_validate(self.repository.get_thread(project_id, thread_id))

    def list_messages(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[AgentMessage]:
        del principal
        self._ensure_project(project_id)
        return [
            AgentMessage.model_validate(item)
            for item in self.repository.list_messages(
                project_id,
                thread_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        ]

    def post_message(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        request: AgentChatMessageRequest,
        *,
        idempotency_key: str,
    ) -> AgentMessage:
        self._ensure_project(project_id)
        request_hash = _canonical_hash(
            {
                "operation": "chat_message",
                "projectId": project_id,
                "threadId": thread_id,
                "principal": principal.value,
                "request": request.model_dump(mode="json", by_alias=True),
            }
        )
        return AgentMessage.model_validate(
            self.repository.append_human_message(
                project_id,
                thread_id,
                role=principal.value,
                content=request.content,
                reply_to_message_id=request.reply_to_message_id,
                citations=[
                    AgentCitation.from_evidence_target(target)
                    for target in request.evidence_targets
                ],
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        )

    def transition_focus(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        request: AgentFocusTransitionRequest,
        *,
        idempotency_key: str,
    ) -> AgentThread:
        self._ensure_project(project_id)
        request_hash = _canonical_hash(
            {
                "operation": "transition_focus",
                "projectId": project_id,
                "threadId": thread_id,
                "principal": principal.value,
                "request": request.model_dump(mode="json", by_alias=True),
            }
        )
        return AgentThread.model_validate(
            self.repository.transition_focus(
                project_id,
                thread_id,
                actor_role=principal.value,
                to_focus_role=request.to_focus_role.value,
                expected_version=request.expected_version,
                reason=request.reason,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        )

    def list_focus_events(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[AgentFocusEvent]:
        del principal
        self._ensure_project(project_id)
        return [
            AgentFocusEvent.model_validate(item)
            for item in self.repository.list_focus_events(
                project_id,
                thread_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        ]

    def control_thread(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        request: AgentThreadControlRequest,
        *,
        idempotency_key: str,
    ) -> AgentThread:
        self._ensure_project(project_id)
        request_hash = _canonical_hash(
            {
                "operation": "control_thread",
                "projectId": project_id,
                "threadId": thread_id,
                "principal": principal.value,
                "request": request.model_dump(mode="json", by_alias=True),
            }
        )
        return AgentThread.model_validate(
            self.repository.control_thread(
                project_id,
                thread_id,
                actor_role=principal.value,
                action=request.action,
                expected_version=request.expected_version,
                reason=request.reason,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        )

    async def execute_turn(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        request: AgentTurnRequest,
        *,
        idempotency_key: str,
    ) -> AgentTurnResult:
        self._ensure_project(project_id)
        request_fingerprint = _canonical_hash(
            {
                "operation": "turn",
                "projectId": project_id,
                "threadId": thread_id,
                "principal": principal.value,
                "request": request.model_dump(mode="json", by_alias=True),
            }
        )
        existing = self.repository.lookup_turn(
            project_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if existing is not None:
            if existing["status"] == "running":
                existing = await self._wait_for_terminal(project_id, existing["runId"])
            return self._result_from_stored(existing)
        thread = AgentThread.model_validate(
            self.repository.get_thread(project_id, thread_id)
        )
        if thread.status.value != "active":
            raise ConflictError("agent_thread_not_active", "非 active 会话不能执行 turn。")
        explicit_routing = request.target_agent_role is not None
        target_role = request.target_agent_role or thread.focus_role
        if not explicit_routing and thread.focus_role != principal:
            raise ForbiddenError(
                "agent_focus_mismatch", "当前认证会话角色必须等于服务端 focusRole。"
            )
        if request.expected_version != thread.version:
            from app.contracts.errors import VersionConflictError

            raise VersionConflictError(
                expected_version=request.expected_version, actual_version=thread.version
            )
        source_message = None
        if request.source_message_id is not None:
            source_message = self.repository.require_message(
                project_id, thread_id, request.source_message_id
            )
            if (
                source_message["authorType"] != "human"
                or source_message["role"] != principal.value
                or source_message["content"] != request.instruction
            ):
                raise ForbiddenError(
                    "agent_source_message_mismatch",
                    "sourceMessageId 必须指向当前认证角色刚发送的同文人类消息。",
                )
        if request.reply_to_message_id is not None:
            self.repository.require_message(
                project_id, thread_id, request.reply_to_message_id
            )

        visible = self.repository.list_recent_messages(project_id, thread_id, limit=40)
        context, assembled = self.context_assembler.assemble(
            project_id=project_id,
            thread_id=thread_id,
            target_role=target_role,
            request=request,
            visible_messages=visible,
        )
        validate_agent_provider_context(target_role, request, context)
        provider = self.providers.get(target_role)
        provider_id = None if provider is None else provider.provider_id
        model_id = None if provider is None else provider.model_id
        prompt_version = None if provider is None else provider.prompt_version
        reserved = self.repository.reserve_turn(
            project_id,
            thread_id,
            turn_id=_new_id("agent-turn"),
            role=target_role.value,
            mode=self.mode.value,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            input_hash=assembled.input_hash,
            context_version=context.context_version,
            expected_thread_version=request.expected_version,
            provider_id=provider_id,
            model_id=model_id,
            prompt_version=prompt_version,
            lease_seconds=max(self.timeout_seconds + 5, 10),
        )
        if reserved["action"] == "wait":
            run = await self._wait_for_terminal(project_id, reserved["run"]["runId"])
            return self._result_from_stored(run)
        if reserved["action"] == "replay":
            return self._result_from_stored(reserved["run"])

        run = reserved["run"]
        run_id = run["runId"]
        lease_token = reserved["leaseToken"]
        if self.mode == AgentMode.DISABLED or provider is None:
            error = ServiceError(
                code="agent_provider_disabled",
                message="Agent provider 已禁用或未配置。",
                category="internal",
                status_code=503,
                details={"retryable": False},
            )
            self.repository.fail_turn(
                project_id,
                run_id,
                lease_token=lease_token,
                status="unavailable",
                error=self._error_payload(error),
            )
            raise error
        if target_role not in provider.supported_roles:
            error = ServiceError(
                code="agent_provider_role_unsupported",
                message="当前 provider 不支持服务端焦点角色。",
                category="internal",
                status_code=503,
                details={"retryable": False},
            )
            self.repository.fail_turn(
                project_id,
                run_id,
                lease_token=lease_token,
                status="unavailable",
                error=self._error_payload(error),
            )
            raise error

        started_at = utc_now()
        try:
            candidate = await asyncio.wait_for(
                provider.generate(
                    target_role,
                    request,
                    context,
                    assembled,
                    max_output_tokens=2048,
                ),
                timeout=self.timeout_seconds,
            )
            generated = (
                candidate
                if isinstance(candidate, GeneratedAgentContent)
                else GeneratedAgentContent.model_validate(candidate)
            )
            validate_generated_agent_content(target_role, context, generated)
            generated_json = generated.model_dump(mode="json", by_alias=True)
            output_hash = _canonical_hash(generated_json)
            execution = AgentExecutionMetadata(
                mode=self.mode,
                provider_id=provider.provider_id,
                model_id=provider.model_id,
                prompt_version=provider.prompt_version,
                input_hash=assembled.input_hash,
                context_version=context.context_version,
                output_hash=output_hash,
                is_simulated=provider.is_simulated,
                data_status=self._data_status(self.mode),
                source=provider.provider_id,
                disclaimer=AGENT_COMMUNICATION_DISCLAIMER,
            )
        except asyncio.CancelledError:
            error = ServiceError(
                code="agent_run_cancelled",
                message="Agent turn 已取消。",
                category="internal",
                status_code=503,
                details={"retryable": False},
            )
            self._record_failure(
                project_id,
                run_id,
                lease_token,
                target_role,
                provider,
                assembled.input_hash,
                context.context_version,
                started_at,
                error,
            )
            raise
        except Exception as exc:
            error = self._provider_error(exc)
            self._record_failure(
                project_id,
                run_id,
                lease_token,
                target_role,
                provider,
                assembled.input_hash,
                context.context_version,
                started_at,
                error,
            )
            raise error from exc

        execution_json = execution.model_dump(mode="json", by_alias=True)
        human_message_id = request.source_message_id or _new_id("agent-message")
        agent_message_id = _new_id("agent-message")
        messages = []
        if source_message is None:
            messages.append(
                {
                    "id": human_message_id,
                    "role": principal.value,
                    "authorType": "human",
                    "kind": "user_input",
                    "content": request.instruction,
                    "citations": [],
                    "generatedContent": None,
                    "execution": None,
                    "replyToMessageId": request.reply_to_message_id,
                    "isSimulated": False,
                }
            )
        messages.append(
            {
                "id": agent_message_id,
                "role": target_role.value,
                "authorType": "agent",
                "kind": "agent_reply",
                "content": generated.reply_text,
                "citations": [
                    item.model_dump(mode="json", by_alias=True)
                    for item in generated.citations
                ],
                "generatedContent": generated_json,
                "execution": execution_json,
                "replyToMessageId": human_message_id,
                "isSimulated": provider.is_simulated,
            }
        )
        completed = self.repository.finalize_turn(
            project_id,
            run_id,
            lease_token=lease_token,
            status=self._run_status(generated),
            messages=messages,
            step={
                "stepId": _new_id("agent-step"),
                "stepIndex": 1,
                "role": target_role.value,
                "status": "completed",
                "providerId": provider.provider_id,
                "modelId": provider.model_id,
                "promptVersion": provider.prompt_version,
                "inputHash": assembled.input_hash,
                "contextVersion": context.context_version,
                "outputHash": output_hash,
                "error": None,
                "startedAt": started_at,
                "finishedAt": utc_now(),
            },
            output_hash=output_hash,
        )
        return self._turn_result(completed)

    def get_run(
        self, project_id: str, run_id: str, principal: AgentRole
    ) -> AgentRunRecord:
        del principal
        self._ensure_project(project_id)
        return AgentRunRecord.model_validate(self.repository.get_run(project_id, run_id))

    async def _wait_for_terminal(
        self, project_id: str, run_id: str
    ) -> Mapping[str, Any]:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds + 6
        while asyncio.get_running_loop().time() < deadline:
            run = self.repository.get_run(project_id, run_id)
            if run["status"] != "running":
                return run
            await asyncio.sleep(0.02)
        raise ConflictError(
            "agent_run_in_progress",
            "同一幂等 turn 仍在运行，请通过 GET run 查询而不要重复调用 provider。",
            details={"runId": run_id},
        )

    def _result_from_stored(self, raw_run: Mapping[str, Any]) -> AgentTurnResult:
        run = AgentRunRecord.model_validate(raw_run)
        if run.status in {AgentRunStatus.FAILED, AgentRunStatus.UNAVAILABLE}:
            raise self._stored_run_error(run)
        if run.status == AgentRunStatus.RUNNING:
            raise ConflictError(
                "agent_run_in_progress", "同一幂等 turn 仍在运行。", details={"runId": run.run_id}
            )
        thread = self.repository.get_thread(run.project_id, run.thread_id)
        messages = self.repository.list_messages(run.project_id, run.thread_id, limit=1000)
        agent_messages = [
            item
            for item in messages
            if item["runId"] == run.run_id and item["authorType"] == "agent"
        ]
        return AgentTurnResult(
            turn_id=run.turn_id,
            run_id=run.run_id,
            status=self._turn_status(run.status),
            focus_role=run.role,
            current_focus_role=thread["focusRole"],
            messages=[AgentMessage.model_validate(agent_messages[-1])],
            next_expected_version=thread["version"],
            execution=run.execution,
        )

    def _turn_result(self, completed: Mapping[str, Any]) -> AgentTurnResult:
        run = AgentRunRecord.model_validate(completed["run"])
        agent_messages = [
            AgentMessage.model_validate(item)
            for item in completed["messages"]
            if item["authorType"] == "agent"
        ]
        return AgentTurnResult(
            turn_id=run.turn_id,
            run_id=run.run_id,
            status=self._turn_status(run.status),
            focus_role=run.role,
            current_focus_role=completed["thread"]["focusRole"],
            messages=agent_messages,
            next_expected_version=completed["thread"]["version"],
            execution=run.execution,
        )

    def _record_failure(
        self,
        project_id: str,
        run_id: str,
        lease_token: str,
        role: AgentRole,
        provider: AgentProviderPort,
        input_hash: str,
        context_version: str,
        started_at: str,
        error: ServiceError,
    ) -> None:
        step = {
            "stepId": _new_id("agent-step"),
            "stepIndex": 1,
            "role": role.value,
            "status": "failed",
            "providerId": provider.provider_id,
            "modelId": provider.model_id,
            "promptVersion": provider.prompt_version,
            "inputHash": input_hash,
            "contextVersion": context_version,
            "outputHash": None,
            "error": self._error_payload(error),
            "startedAt": started_at,
            "finishedAt": utc_now(),
        }
        try:
            self.repository.fail_turn(
                project_id,
                run_id,
                lease_token=lease_token,
                status="failed",
                error=self._error_payload(error),
                step=step,
            )
        except ConflictError:
            # A stale/expired owner is fenced and must not overwrite the winner.
            pass

    @staticmethod
    def _run_status(content: GeneratedAgentContent) -> str:
        if content.scope_status == AgentScopeStatus.OUT_OF_SCOPE:
            return "out_of_scope"
        if content.scope_status == AgentScopeStatus.NEEDS_CLARIFICATION:
            return "needs_review"
        return "completed"

    @staticmethod
    def _turn_status(status: AgentRunStatus) -> AgentTurnStatus:
        return {
            AgentRunStatus.COMPLETED: AgentTurnStatus.COMPLETED,
            AgentRunStatus.NEEDS_REVIEW: AgentTurnStatus.NEEDS_REVIEW,
            AgentRunStatus.OUT_OF_SCOPE: AgentTurnStatus.OUT_OF_SCOPE,
            AgentRunStatus.UNAVAILABLE: AgentTurnStatus.UNAVAILABLE,
        }[status]

    @staticmethod
    def _data_status(mode: AgentMode) -> AgentDataStatus:
        return {
            AgentMode.DISABLED: AgentDataStatus.UNAVAILABLE,
            AgentMode.SYNTHETIC: AgentDataStatus.SIMULATED,
            AgentMode.REAL: AgentDataStatus.PROVIDER_GENERATED_UNVERIFIED,
        }[mode]

    @staticmethod
    def _error_payload(error: ServiceError) -> dict[str, Any]:
        return {
            "code": error.code,
            "message": error.message,
            "retryable": bool(error.details.get("retryable", False)),
            "providerStatus": error.details.get("providerStatus"),
        }

    @staticmethod
    def _provider_error(exc: Exception) -> ServiceError:
        if isinstance(exc, ServiceError):
            return exc
        if getattr(exc, "code", None) == "provider_cli_error":
            return ServiceError(
                code="agent_provider_cli_error",
                message="Agent provider CLI 执行失败。",
                category="internal",
                status_code=503,
                details={"retryable": bool(getattr(exc, "retryable", False))},
            )
        if isinstance(exc, asyncio.TimeoutError):
            return ServiceError(
                code="agent_provider_timeout",
                message="Agent provider 超时。",
                category="internal",
                status_code=503,
                details={"retryable": True},
            )
        if isinstance(exc, (ValidationError, ValueError, TypeError)):
            return ServiceError(
                code="agent_provider_output_invalid",
                message="Agent provider 输出未通过结构、引用或权威边界校验。",
                category="internal",
                status_code=503,
                details={"retryable": False},
            )
        return ServiceError(
            code="agent_provider_unavailable",
            message="Agent provider 不可用。",
            category="internal",
            status_code=503,
            details={"retryable": True},
        )

    @staticmethod
    def _stored_run_error(run: AgentRunRecord) -> ServiceError:
        assert run.error is not None
        return ServiceError(
            code=run.error.code,
            message=run.error.message,
            category="internal",
            status_code=503,
            details={
                "retryable": run.error.retryable,
                "providerStatus": run.error.provider_status,
                "runId": run.run_id,
            },
        )


__all__ = ["AgentCommunicationService"]

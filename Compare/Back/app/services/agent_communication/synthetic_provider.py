from __future__ import annotations

import re

from app.contracts.agent_communication import (
    AgentDisposition,
    AgentProviderContext,
    AgentRole,
    AgentScopeStatus,
    AgentTurnRequest,
    GeneratedAgentContent,
    validate_agent_provider_context,
    validate_generated_agent_content,
)
from app.ports.agent_communication import AgentAssembledInput


SYNTHETIC_AGENT_PROVIDER_ID = "deterministic_agent_simulator"
SYNTHETIC_AGENT_MODEL_ID = "structured-single-focus-sim-v2"
SYNTHETIC_AGENT_PROMPT_VERSION = "compare-agent-single-focus-synthetic-v2"

_PROJECT_MARKERS = frozenset(
    {
        "项目",
        "融资租赁",
        "租赁",
        "业务",
        "风控",
        "领导",
        "材料",
        "证据",
        "事实",
        "合同",
        "报价",
        "供应商",
        "设备",
        "合规",
        "交易",
        "生产",
        "产能",
        "营收",
        "负债",
        "流水",
        "还款",
        "偿债",
        "审批",
        "制度",
        "hard gate",
        "evidence",
        "policy",
        "approval",
    }
)
_CLEARLY_UNRELATED_MARKERS = frozenset(
    {
        "今天天气",
        "明天天气",
        "股票推荐",
        "彩票",
        "写首诗",
        "写小说",
        "菜谱",
        "做饭",
        "编程作业",
        "游戏攻略",
        "医疗诊断",
        "星座",
        "娱乐新闻",
        "体育比分",
        "translate this",
        "weather forecast",
        "write a poem",
        "recipe",
    }
)
_GAP_MARKERS = (
    "缺失",
    "未提供",
    "待补",
    "待定位",
    "无法核验",
    "不可核验",
    "版本不一致",
    "version_mismatch",
    "manual_review",
    "pending",
    "unverifiable",
)
_VAGUE_INSTRUCTIONS = frozenset({"看看", "继续", "怎么办", "请说明", "帮我看下", "分析一下"})


class SyntheticAgentProvider:
    """Deterministic but context-sensitive provider for the local first version."""

    provider_id = SYNTHETIC_AGENT_PROVIDER_ID
    model_id = SYNTHETIC_AGENT_MODEL_ID
    prompt_version = SYNTHETIC_AGENT_PROMPT_VERSION
    is_simulated = True
    supported_roles = frozenset(AgentRole)

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(
        self,
        role: AgentRole,
        request: AgentTurnRequest,
        context: AgentProviderContext,
        assembled_input: AgentAssembledInput,
        *,
        max_output_tokens: int,
    ) -> GeneratedAgentContent:
        if role not in self.supported_roles:
            raise ValueError("synthetic provider does not support the routed role")
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        validate_agent_provider_context(role, request, context)
        self.call_count += 1

        if _is_clearly_out_of_scope(request.instruction):
            content = GeneratedAgentContent(
                reply_text=(
                    "这个问题与当前融资租赁项目的材料、证据、审查或审批流程无直接关系。"
                    "我只能在本项目范围内协助，请改为询问当前项目事项。"
                ),
                observations=[],
                questions=[],
                citations=[],
                scope_status=AgentScopeStatus.OUT_OF_SCOPE,
                disposition=AgentDisposition.DECLINE_OUT_OF_SCOPE,
            )
            return validate_generated_agent_content(role, context, content)

        if _is_vague(request.instruction):
            content = GeneratedAgentContent(
                reply_text=(
                    f"请明确希望{_role_label(role)}围绕哪项材料、事实、制度结果或审批事项展开。"
                ),
                observations=[],
                questions=["请指出要讨论的具体项目事项或选择相应证据。"],
                citations=[],
                scope_status=AgentScopeStatus.NEEDS_CLARIFICATION,
                disposition=AgentDisposition.REQUEST_INFORMATION,
            )
            return validate_generated_agent_content(role, context, content)

        if role == AgentRole.BUSINESS:
            content = _business_content(request, context, assembled_input)
        elif role == AgentRole.RISK:
            content = _risk_content(request, context, assembled_input)
        else:
            content = _leadership_content(request, context, assembled_input)
        return validate_generated_agent_content(role, context, content)


def _business_content(
    request: AgentTurnRequest,
    context: AgentProviderContext,
    assembled_input: AgentAssembledInput,
) -> GeneratedAgentContent:
    topic = _topic(request.instruction)
    gaps = _context_has_gaps(context)
    citations = context.citation_allowlist[:3]
    observations = [
        f"当前答复仅针对项目“{context.project_summary.name}”及业务侧可见上下文。",
        (
            f"已读取 {len(context.dimension_summaries)} 个维度摘要、"
            f"{len(context.selected_evidence)} 项所选证据和 "
            f"{len(context.selected_facts)} 个绑定事实版本。"
        ),
    ]
    if context.selected_facts:
        observations.append(f"所选事实：{_selected_fact_summary(context)}。")
    if context.selected_evidence:
        observations.append(
            "证据定位状态："
            + "、".join(
                f"{item.label}={item.location_status}"
                for item in context.selected_evidence[:3]
            )
            + "。"
        )
    if gaps:
        observations.append("当前上下文存在缺失、待定位或需人工复核的信息。")
        questions = ["请补充或定位与本事项直接相关的原始材料，再由人工确认版本一致性。"]
        disposition = AgentDisposition.REQUEST_INFORMATION
        ending = "在补齐材料前，本答复只说明业务口径，不替代正式事实确认。"
    else:
        questions = []
        disposition = AgentDisposition.ANSWER
        ending = "业务口径已整理；是否切换焦点由服务端显式焦点接口处理。"
    return GeneratedAgentContent(
        reply_text=f"业务侧已围绕“{topic}”整理当前项目说明。{ending}",
        observations=[*observations, f"本次输入绑定标识为 {assembled_input.input_hash[:12]}。"],
        questions=questions,
        citations=citations,
        scope_status=AgentScopeStatus.IN_SCOPE,
        disposition=disposition,
    )


def _risk_content(
    request: AgentTurnRequest,
    context: AgentProviderContext,
    assembled_input: AgentAssembledInput,
) -> GeneratedAgentContent:
    topic = _topic(request.instruction)
    gaps = _context_has_gaps(context)
    blocked = (
        context.approval_state.hard_gate_status != "pass"
        or context.approval_state.risk_veto
        or any(item.result == "block" for item in context.policy_results)
    )
    citations = context.citation_allowlist[:3]
    observations = [
        f"风控侧按项目“{context.project_summary.name}”的证据、制度和审批当前态审阅“{topic}”。",
        f"当前审批状态为 {context.approval_state.status}，hard gate 为 {context.approval_state.hard_gate_status}。",
        f"本次输入绑定标识为 {assembled_input.input_hash[:12]}。",
    ]
    if context.selected_facts:
        observations.append(f"本轮绑定事实为：{_selected_fact_summary(context)}。")
    if context.selected_evidence:
        observations.append(
            "本轮证据状态为："
            + "、".join(
                f"{item.label}={item.location_status}/{item.material_status}"
                for item in context.selected_evidence[:3]
            )
            + "。"
        )
    if blocked:
        return GeneratedAgentContent(
            reply_text=(
                "当前存在 hard gate、风险否决或阻断制度结果。风控侧只能提示阻断事实并提交领导协调，"
                "任何 Agent 都不能覆盖该状态。"
            ),
            observations=observations,
            questions=[],
            citations=citations,
            scope_status=AgentScopeStatus.IN_SCOPE,
            disposition=AgentDisposition.ESCALATE,
        )
    if gaps:
        return GeneratedAgentContent(
            reply_text="现有材料不足以形成稳定风控意见，缺口只进入补件与人工复核，不自动等同拒绝。",
            observations=[*observations, "证据状态包含缺失、不可核验或版本待确认项。"],
            questions=["请业务侧补充对应原件、精确位置和当前版本说明。"],
            citations=citations,
            scope_status=AgentScopeStatus.IN_SCOPE,
            disposition=AgentDisposition.REQUEST_INFORMATION,
        )
    return GeneratedAgentContent(
        reply_text="风控侧已完成本轮证据充分性与制度当前态检查；该内容仍须人工形成正式意见。",
        observations=observations,
        questions=[],
        citations=citations,
        scope_status=AgentScopeStatus.IN_SCOPE,
        disposition=AgentDisposition.ANSWER,
    )


def _leadership_content(
    request: AgentTurnRequest,
    context: AgentProviderContext,
    assembled_input: AgentAssembledInput,
) -> GeneratedAgentContent:
    topic = _topic(request.instruction)
    gaps = _context_has_gaps(context)
    citations = context.citation_allowlist[:3]
    actions = (
        "业务侧先补齐原件与版本说明，风控侧在同一证据范围内复核，完成后再回到领导通道汇总。"
        if gaps
        else "业务侧确认事实口径，风控侧确认风险与制度口径，再由人工决定是否推进正式 Gate。"
    )
    questions = ["请业务与风控分别确认各自下一步负责人和完成条件。"] if gaps else []
    return GeneratedAgentContent(
        reply_text=f"领导侧已汇总“{topic}”。{actions}",
        observations=[
            f"汇总范围仅限项目“{context.project_summary.name}”和当前可见消息。",
            "领导协调权不覆盖 FactVersion、hard gate、风险否决或审批不变量。",
            f"本次输入绑定标识为 {assembled_input.input_hash[:12]}。",
        ],
        questions=questions,
        citations=citations,
        scope_status=AgentScopeStatus.IN_SCOPE,
        disposition=(
            AgentDisposition.REQUEST_INFORMATION if gaps else AgentDisposition.ANSWER
        ),
    )


def _is_clearly_out_of_scope(instruction: str) -> bool:
    normalized = instruction.casefold()
    has_project_marker = any(marker in normalized for marker in _PROJECT_MARKERS)
    return not has_project_marker and any(
        marker in normalized for marker in _CLEARLY_UNRELATED_MARKERS
    )


def _is_vague(instruction: str) -> bool:
    normalized = re.sub(r"[\s，。！？!?、]", "", instruction.casefold())
    return normalized in _VAGUE_INSTRUCTIONS or len(normalized) < 3


def _context_has_gaps(context: AgentProviderContext) -> bool:
    texts = [
        context.project_summary.summary,
        context.approval_state.summary,
        *(item.summary for item in context.dimension_summaries),
        *(f"{item.result} {item.explanation} {item.next_action}" for item in context.policy_results),
    ]
    joined = " ".join(texts).casefold()
    return any(marker in joined for marker in _GAP_MARKERS)


def _topic(instruction: str) -> str:
    compact = " ".join(instruction.split())
    return compact if len(compact) <= 80 else compact[:77] + "..."


def _role_label(role: AgentRole) -> str:
    return {
        AgentRole.BUSINESS: "业务侧",
        AgentRole.RISK: "风控侧",
        AgentRole.LEADERSHIP: "领导侧",
    }[role]


def _selected_fact_summary(context: AgentProviderContext) -> str:
    return "、".join(
        f"{item.label}={item.value_text}{item.unit or ''}"
        for item in context.selected_facts[:3]
    )


__all__ = [
    "SYNTHETIC_AGENT_MODEL_ID",
    "SYNTHETIC_AGENT_PROMPT_VERSION",
    "SYNTHETIC_AGENT_PROVIDER_ID",
    "SyntheticAgentProvider",
]

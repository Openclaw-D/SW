from __future__ import annotations

import math
from typing import Mapping, Sequence, TypeVar

from app.contracts.pre_review import (
    PreReviewAction,
    PreReviewDriver,
    PreReviewHardGate,
    PreReviewIssue,
    PreReviewProjection,
    PreReviewSource,
    PreReviewSourceIssue,
    PreReviewSourcePolicy,
    PreReviewTendencies,
)
from app.domain.constants import DIMENSION_NAMES

CALCULATION_VERSION = "pre-review-v1"

ESTIMATE_DISCLAIMER = (
    "该时长区间由确定性规则生成，未使用历史数据校准，不构成任何时限承诺。"
)
READY_NEXT_ACTION = "当前没有待补充事项；预审结果仍需人工审查确认。"

_TENDENCY_ORDER: tuple[str, ...] = ("support", "return", "review", "deny")
_T = TypeVar("_T")
_DISPOSITION_TIE_PRIORITY = {"review": 3, "return": 2, "deny": 1, "support": 0}
_ESTIMATE_BASE_RANGES: dict[str, tuple[int, int]] = {
    "support": (2, 4),
    "return": (5, 8),
    "review": (4, 7),
    "deny": (2, 4),
}


def _largest_remainder(raw: Mapping[str, float]) -> dict[str, int]:
    """Scale raw tendency weights to integers summing to 100 with every value >= 1."""

    weights = {key: max(0.0, raw[key] - 1.0) for key in _TENDENCY_ORDER}
    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        weights = {key: 1.0 for key in _TENDENCY_ORDER}
        total_weight = float(len(_TENDENCY_ORDER))
    pool = 100 - len(_TENDENCY_ORDER)
    shares = {key: pool * weights[key] / total_weight for key in _TENDENCY_ORDER}
    floors = {key: math.floor(shares[key]) for key in _TENDENCY_ORDER}
    leftover = pool - sum(floors.values())
    ranked = sorted(
        _TENDENCY_ORDER,
        key=lambda key: (-(shares[key] - floors[key]), _TENDENCY_ORDER.index(key)),
    )
    for key in ranked[:leftover]:
        floors[key] += 1
    return {key: 1 + floors[key] for key in _TENDENCY_ORDER}


def _winning_disposition(values: Mapping[str, int]) -> str:
    return max(
        _TENDENCY_ORDER,
        key=lambda key: (values[key], _DISPOSITION_TIE_PRIORITY[key]),
    )


def _sorted_by_id(items: Sequence[_T]) -> list[_T]:
    return sorted(items, key=lambda item: item.id)


def _has_located_evidence(
    issue: PreReviewSourceIssue, located_evidence_ids: frozenset[str]
) -> bool:
    return any(ref in located_evidence_ids for ref in issue.evidence_refs)


def _issue_next_action(issue: PreReviewSourceIssue) -> str:
    if issue.status == "pending_gate":
        return "request_manual_review"
    if issue.evidence_refs:
        return "resolve_verified_issue"
    return "upload_or_link_evidence"


def _hard_gate(
    blocking_policies: Sequence[PreReviewSourcePolicy],
    manual_policies: Sequence[PreReviewSourcePolicy],
) -> PreReviewHardGate:
    if blocking_policies:
        rule_summary = "；".join(
            f"{policy.rule_id} {policy.title}" for policy in blocking_policies
        )
        return PreReviewHardGate(
            status="block",
            enforced=True,
            blocking_rule_ids=[policy.rule_id for policy in blocking_policies],
            manual_review_rule_ids=[policy.rule_id for policy in manual_policies],
            explanation=(
                f"已核验制度规则触发阻断：{rule_summary}。"
                "该结果独立于六维评分，预审处置固定为拒绝。"
            ),
        )
    if manual_policies:
        return PreReviewHardGate(
            status="manual_review",
            enforced=False,
            blocking_rule_ids=[],
            manual_review_rule_ids=[policy.rule_id for policy in manual_policies],
            explanation=(
                f"有 {len(manual_policies)} 项制度规则待人工复核；"
                "材料缺失或无法核验仅提高复核权重，不构成自动拒绝。"
            ),
        )
    return PreReviewHardGate(
        status="pass",
        enforced=False,
        blocking_rule_ids=[],
        manual_review_rule_ids=[],
        explanation="未触发制度阻断；证据缺口只提高退回或复核权重，不提高拒绝权重。",
    )


def _drivers(
    *,
    source: PreReviewSource,
    blocking_policies: Sequence[PreReviewSourcePolicy],
    manual_policies: Sequence[PreReviewSourcePolicy],
    issues: Sequence[PreReviewSourceIssue],
    nonlocated_evidence_ids: Sequence[str],
    disposition: str,
) -> list[PreReviewDriver]:
    drivers: list[PreReviewDriver] = []
    for policy in blocking_policies:
        drivers.append(
            PreReviewDriver(
                id=f"driver-hard-gate-{policy.id}",
                kind="hard_gate",
                title=f"制度阻断：{policy.title}",
                explanation=policy.explanation,
                direction="deny",
                dimension_id=policy.dimension_id,
                evidence_refs=policy.evidence_refs,
                rule_ids=[policy.rule_id],
            )
        )
    for policy in manual_policies:
        drivers.append(
            PreReviewDriver(
                id=f"driver-rule-{policy.id}",
                kind="rule",
                title=f"待人工复核规则：{policy.title}",
                explanation=policy.explanation,
                direction="review",
                dimension_id=policy.dimension_id,
                evidence_refs=policy.evidence_refs,
                rule_ids=[policy.rule_id],
            )
        )
    for issue in issues:
        drivers.append(
            PreReviewDriver(
                id=f"driver-issue-{issue.id}",
                kind="issue",
                title=f"待处理问题：{issue.title}",
                explanation=issue.summary,
                direction="return" if issue.status == "open" else "review",
                dimension_id=issue.dimension_id,
                evidence_refs=issue.evidence_refs,
                fact_version_ids=issue.fact_version_ids,
                rule_ids=issue.rule_ids,
                issue_ids=[issue.id],
            )
        )
    if nonlocated_evidence_ids:
        drivers.append(
            PreReviewDriver(
                id="driver-evidence-unresolved",
                kind="evidence",
                title="证据定位缺口",
                explanation=(
                    f"{len(nonlocated_evidence_ids)} 项证据未定位或无法核验；"
                    "仅提高退回与复核权重，不提高拒绝权重。"
                ),
                direction="return",
                evidence_refs=list(nonlocated_evidence_ids),
            )
        )
    if source.confidence < 80:
        drivers.append(
            PreReviewDriver(
                id="driver-confidence-low",
                kind="confidence",
                title="置信度不足",
                explanation=(
                    f"当前置信度 {source.confidence:g}，低于 80；"
                    "需要人工复核补充核验，不改变评分本身。"
                ),
                direction="review",
            )
        )
    for dimension in source.dimensions:
        if dimension.score < 40:
            drivers.append(
                PreReviewDriver(
                    id=f"driver-critical-{dimension.dimension_id}",
                    kind="score",
                    title=f"低分维度：{DIMENSION_NAMES[dimension.dimension_id]}",
                    explanation=(
                        f"{DIMENSION_NAMES[dimension.dimension_id]}得分 "
                        f"{dimension.score:g} 低于 40，进入拒绝倾向权重。"
                    ),
                    direction="deny",
                    dimension_id=dimension.dimension_id,
                )
            )
    drivers.append(
        PreReviewDriver(
            id="driver-overall-score",
            kind="score",
            title="综合评分基线",
            explanation=(
                f"综合评分 {source.overall_score:g}、置信度 {source.confidence:g} "
                "按确定性规则构成倾向基线。"
            ),
            direction=disposition,
            evidence_refs=sorted(item.id for item in source.evidence),
        )
    )
    return drivers


def _issues_and_actions(
    issues: Sequence[PreReviewSourceIssue],
    *,
    linked_issue_ids: frozenset[str],
    manual_requested_issue_ids: frozenset[str],
    located_evidence_ids: frozenset[str],
) -> tuple[list[PreReviewIssue], list[PreReviewAction]]:
    projected_issues: list[PreReviewIssue] = []
    actions: list[PreReviewAction] = []
    for issue in issues:
        evidence_completed = (
            issue.id in linked_issue_ids
            and _has_located_evidence(issue, located_evidence_ids)
        )
        projected_issues.append(
            PreReviewIssue(
                id=issue.id,
                thread_id=issue.thread_id,
                dimension_id=issue.dimension_id,
                title=issue.title,
                summary=issue.summary,
                status=issue.status,
                evidence_refs=issue.evidence_refs,
                fact_version_ids=issue.fact_version_ids,
                rule_ids=issue.rule_ids,
                next_action=_issue_next_action(issue),
            )
        )
        if issue.evidence_refs:
            actions.append(
                PreReviewAction(
                    id=f"action-{issue.id}-evidence",
                    issue_id=issue.id,
                    dimension_id=issue.dimension_id,
                    action_type="resolve_verified_issue",
                    title="核验并确认既有证据",
                    description=(
                        "请确认既有证据已定位并由风险岗核验；"
                        "只有匹配的关联证据动作且证据已定位时才会完成。"
                    ),
                    completed=evidence_completed,
                    closure_requires="verified_evidence",
                    evidence_refs=issue.evidence_refs,
                    rule_ids=issue.rule_ids,
                )
            )
        else:
            actions.append(
                PreReviewAction(
                    id=f"action-{issue.id}-evidence",
                    issue_id=issue.id,
                    dimension_id=issue.dimension_id,
                    action_type="upload_or_link_evidence",
                    title="补充并关联证据",
                    description="请补充并关联可定位的证据；证据本身不构成审批结论。",
                    completed=False,
                    closure_requires="verified_evidence",
                    rule_ids=issue.rule_ids,
                )
            )
        actions.append(
            PreReviewAction(
                id=f"action-{issue.id}-explanation",
                issue_id=issue.id,
                dimension_id=issue.dimension_id,
                action_type="provide_explanation",
                title="补充业务说明",
                description=(
                    "请补充业务说明；说明本身不完成也不关闭该问题，"
                    "关闭仍需已核验证据或人工复核。"
                ),
                completed=False,
                closure_requires="verified_evidence",
                evidence_refs=issue.evidence_refs,
                rule_ids=issue.rule_ids,
            )
        )
        if issue.status == "pending_gate":
            actions.append(
                PreReviewAction(
                    id=f"action-{issue.id}-manual",
                    issue_id=issue.id,
                    dimension_id=issue.dimension_id,
                    action_type="request_manual_review",
                    title="申请人工复核",
                    description="该问题等待人工复核；只有匹配的人工复核申请动作才会完成。",
                    completed=issue.id in manual_requested_issue_ids,
                    closure_requires="human_review",
                    evidence_refs=issue.evidence_refs,
                    rule_ids=issue.rule_ids,
                )
            )
    return projected_issues, actions


def _estimate(
    *,
    disposition: str,
    manual_count: int,
    nonlocated_count: int,
    actions: Sequence[PreReviewAction],
) -> tuple[int, int, list[str], str]:
    base_min, base_max = _ESTIMATE_BASE_RANGES[disposition]
    manual_extra = 0 if manual_count == 0 else 1 if manual_count == 1 else 2
    unresolved_extra = 0 if nonlocated_count == 0 else 1 if nonlocated_count == 1 else 2
    min_days = min(90, base_min + manual_extra + unresolved_extra)
    max_days = min(90, base_max + manual_extra + unresolved_extra)
    drivers = [f"确定性规则区间 {CALCULATION_VERSION}"]
    if manual_count:
        drivers.append(f"{manual_count} 项制度规则待人工复核")
    if nonlocated_count:
        drivers.append(f"{nonlocated_count} 项证据未定位")
    first_incomplete = next(
        (action for action in actions if not action.completed), None
    )
    next_action = (
        first_incomplete.description
        if first_incomplete is not None
        else READY_NEXT_ACTION
    )
    return min_days, max_days, drivers, next_action


def calculate_pre_review_projection(source: PreReviewSource) -> PreReviewProjection:
    """Project a deterministic provisional pre-review disposition. No time or randomness."""

    blocking_policies = [
        policy
        for policy in _sorted_by_id(source.policies)
        if policy.result == "block" and policy.gate_triggered
    ]
    manual_policies = [
        policy
        for policy in _sorted_by_id(source.policies)
        if policy.result == "manual_review"
    ]
    issues = _sorted_by_id(source.issues)
    nonlocated_evidence_ids = sorted(
        item.id for item in source.evidence if item.location_status != "located"
    )
    located_evidence_ids = frozenset(
        item.id for item in source.evidence if item.location_status == "located"
    )
    unresolved_ratio = len(nonlocated_evidence_ids) / max(1, len(source.evidence))
    open_count = sum(1 for issue in issues if issue.status == "open")
    manual_count = len(manual_policies)
    critical_count = sum(1 for dimension in source.dimensions if dimension.score < 40)

    if blocking_policies:
        disposition: str = "deny"
        tendencies = PreReviewTendencies(support=0, return_value=0, review=0, deny=100)
    else:
        raw = {
            "support": max(1.0, source.overall_score * source.confidence / 100.0),
            "return": max(
                1.0, 12.0 + open_count * 10.0 + unresolved_ratio * 30.0
            ),
            "review": max(
                1.0, 8.0 + manual_count * 18.0 + (100.0 - source.confidence) * 0.35
            ),
            "deny": max(
                1.0,
                3.0
                + critical_count * 12.0
                + max(0.0, 50.0 - source.overall_score) * 0.8,
            ),
        }
        values = _largest_remainder(raw)
        tendencies = PreReviewTendencies(
            support=values["support"],
            return_value=values["return"],
            review=values["review"],
            deny=values["deny"],
        )
        disposition = _winning_disposition(values)

    projected_issues, actions = _issues_and_actions(
        issues,
        linked_issue_ids=frozenset(
            action.issue_id
            for action in source.issue_actions
            if action.action_type == "link_evidence"
        ),
        manual_requested_issue_ids=frozenset(
            action.issue_id
            for action in source.issue_actions
            if action.action_type == "request_manual_review"
        ),
        located_evidence_ids=located_evidence_ids,
    )
    min_days, max_days, estimate_drivers, estimate_next_action = _estimate(
        disposition=disposition,
        manual_count=manual_count,
        nonlocated_count=len(nonlocated_evidence_ids),
        actions=actions,
    )
    return PreReviewProjection(
        project_id=source.project_id,
        calculation_version=CALCULATION_VERSION,
        disposition=disposition,
        tendencies=tendencies,
        overall_score=source.overall_score,
        score_grade=source.score_grade,
        decision_grade=source.decision_grade,
        confidence=source.confidence,
        dimensions=list(source.dimensions),
        drivers=_drivers(
            source=source,
            blocking_policies=blocking_policies,
            manual_policies=manual_policies,
            issues=issues,
            nonlocated_evidence_ids=nonlocated_evidence_ids,
            disposition=disposition,
        ),
        issues=projected_issues,
        hard_gate=_hard_gate(blocking_policies, manual_policies),
        actions=actions,
        estimate={
            "minDays": min_days,
            "maxDays": max_days,
            "estimateKind": "rule_based_range",
            "drivers": estimate_drivers,
            "disclaimer": ESTIMATE_DISCLAIMER,
            "nextAction": estimate_next_action,
        },
    )


__all__ = ["CALCULATION_VERSION", "calculate_pre_review_projection"]

from __future__ import annotations

from copy import deepcopy

import pytest

from app.contracts.pre_review import PreReviewProjection, PreReviewSource
from app.domain.constants import DIMENSION_IDS
from app.domain.pre_review import calculate_pre_review_projection


def _dimensions_payload(
    *, score: float = 88.0, confidence: float = 92.0
) -> list[dict[str, object]]:
    return [
        {
            "dimensionId": dimension_id,
            "score": score,
            "scoreGrade": "B",
            "decisionGrade": "B",
            "confidence": confidence,
        }
        for dimension_id in DIMENSION_IDS
    ]


def _pass_policy() -> dict[str, object]:
    return {
        "id": "policy-compliance",
        "ruleId": "CMP-H-001",
        "ruleVersion": "compare-business-rules-2026.08",
        "title": "禁入主体状态",
        "result": "pass",
        "gateTriggered": False,
        "dimensionId": "compliance",
        "evidenceRefs": ["evidence-compliance"],
        "nextAction": "无需补充",
        "explanation": "已核验事实未触发制度阻断。",
    }


def _blocking_policy() -> dict[str, object]:
    return {
        "id": "policy-transaction-block",
        "ruleId": "TRX-H-001",
        "ruleVersion": "compare-business-rules-2026.08",
        "title": "融资金额不得超过项目金额",
        "result": "block",
        "gateTriggered": True,
        "dimensionId": "transaction",
        "evidenceRefs": ["evidence-transaction"],
        "nextAction": "人工复核",
        "explanation": "已核验不利事实触发制度阻断；该结果独立于六维分数。",
    }


def _source_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "projectId": "project-pre-001",
        "overallScore": 88.0,
        "scoreGrade": "B",
        "decisionGrade": "B",
        "confidence": 92.0,
        "dimensions": _dimensions_payload(),
        "evidence": [
            {
                "id": f"evidence-{dimension_id}",
                "dimensionId": dimension_id,
                "locationStatus": "located",
            }
            for dimension_id in DIMENSION_IDS
        ],
        "facts": [],
        "policies": [_pass_policy()],
        "issues": [],
        "issueActions": [],
    }
    payload.update(overrides)
    return payload


def _issue_payload(**overrides: object) -> dict[str, object]:
    issue: dict[str, object] = {
        "id": "issue-revenue-1",
        "threadId": "thread-revenue",
        "dimensionId": "revenue",
        "title": "营收证据待关联",
        "summary": "营收口径需要补充关联证据。",
        "status": "open",
        "evidenceRefs": ["evidence-revenue"],
        "factVersionIds": ["fact-revenue-v1"],
        "ruleIds": ["REV-H-001"],
    }
    issue.update(overrides)
    return issue


def _tendency_total(projection: PreReviewProjection) -> int:
    return (
        projection.tendencies.support
        + projection.tendencies.return_value
        + projection.tendencies.review
        + projection.tendencies.deny
    )


def test_projection_is_deterministic_and_tendencies_sum_to_100() -> None:
    payload = _source_payload(
        issues=[_issue_payload(id="issue-z"), _issue_payload(id="issue-a")]
    )

    first = calculate_pre_review_projection(PreReviewSource.model_validate(payload))
    second = calculate_pre_review_projection(PreReviewSource.model_validate(payload))

    assert first == second
    assert first.model_dump() == second.model_dump()
    assert _tendency_total(first) == 100
    assert [issue.id for issue in first.issues] == ["issue-a", "issue-z"]
    assert len({action.id for action in first.actions}) == len(first.actions)
    assert first.calculation_version == "pre-review-v1"
    assert first.provisional is True
    assert first.calibrated_probability is False
    assert first.formal_decision is False
    serialized = first.model_dump(by_alias=True)
    assert set(serialized["tendencies"]) == {"support", "return", "review", "deny"}


def test_missing_or_unverifiable_evidence_never_increases_deny() -> None:
    baseline = calculate_pre_review_projection(
        PreReviewSource.model_validate(_source_payload())
    )
    evidence = deepcopy(_source_payload()["evidence"])
    evidence[1]["locationStatus"] = "pending"
    evidence[2]["locationStatus"] = "unverifiable"

    variant = calculate_pre_review_projection(
        PreReviewSource.model_validate(_source_payload(evidence=evidence))
    )

    assert variant.tendencies.deny == baseline.tendencies.deny
    assert variant.tendencies.return_value > baseline.tendencies.return_value
    assert variant.disposition != "deny"
    assert variant.hard_gate.status == "pass"
    assert _tendency_total(variant) == 100


def test_verified_policy_block_forces_deny_with_frozen_tendencies() -> None:
    projection = calculate_pre_review_projection(
        PreReviewSource.model_validate(
            _source_payload(policies=[_pass_policy(), _blocking_policy()])
        )
    )

    assert projection.disposition == "deny"
    assert (
        projection.tendencies.support,
        projection.tendencies.return_value,
        projection.tendencies.review,
        projection.tendencies.deny,
    ) == (0, 0, 0, 100)
    assert projection.hard_gate.status == "block"
    assert projection.hard_gate.enforced is True
    assert projection.hard_gate.blocking_rule_ids == ["TRX-H-001"]
    assert _tendency_total(projection) == 100


def test_six_frozen_dimensions_must_appear_in_order() -> None:
    reordered = _source_payload()
    reordered["dimensions"] = [
        reordered["dimensions"][1],
        reordered["dimensions"][0],
        *reordered["dimensions"][2:],
    ]
    with pytest.raises(ValueError, match="six frozen dimensions"):
        PreReviewSource.model_validate(reordered)

    valid = calculate_pre_review_projection(
        PreReviewSource.model_validate(_source_payload())
    )
    serialized = valid.model_dump(by_alias=True)
    serialized["dimensions"] = list(reversed(serialized["dimensions"]))
    with pytest.raises(ValueError, match="six frozen dimensions"):
        PreReviewProjection.model_validate(serialized)


def test_explanation_action_never_completes_or_closes() -> None:
    explain_only = calculate_pre_review_projection(
        PreReviewSource.model_validate(
            _source_payload(
                issues=[_issue_payload()],
                issueActions=[
                    {
                        "id": "action-source-explain",
                        "issueId": "issue-revenue-1",
                        "actionType": "explain",
                        "note": "已补充业务说明",
                    }
                ],
            )
        )
    )
    by_type = {action.action_type: action for action in explain_only.actions}
    assert by_type["provide_explanation"].completed is False
    assert by_type["provide_explanation"].closure_requires == "verified_evidence"
    assert by_type["resolve_verified_issue"].completed is False

    linked = calculate_pre_review_projection(
        PreReviewSource.model_validate(
            _source_payload(
                issues=[_issue_payload()],
                issueActions=[
                    {
                        "id": "action-source-link",
                        "issueId": "issue-revenue-1",
                        "actionType": "link_evidence",
                        "evidenceRef": "evidence-revenue",
                    },
                    {
                        "id": "action-source-explain",
                        "issueId": "issue-revenue-1",
                        "actionType": "explain",
                    },
                ],
            )
        )
    )
    linked_by_type = {action.action_type: action for action in linked.actions}
    assert linked_by_type["resolve_verified_issue"].completed is True
    assert linked_by_type["provide_explanation"].completed is False


def test_link_evidence_completes_only_with_located_evidence() -> None:
    located = calculate_pre_review_projection(
        PreReviewSource.model_validate(
            _source_payload(
                issues=[_issue_payload()],
                issueActions=[
                    {
                        "id": "action-source-link",
                        "issueId": "issue-revenue-1",
                        "actionType": "link_evidence",
                        "evidenceRef": "evidence-revenue",
                    }
                ],
            )
        )
    )
    assert located.issues[0].next_action == "resolve_verified_issue"
    assert next(
        action
        for action in located.actions
        if action.id == "action-issue-revenue-1-evidence"
    ).completed is True

    pending_evidence = deepcopy(_source_payload()["evidence"])
    pending_evidence[4]["locationStatus"] = "version_mismatch"
    pending = calculate_pre_review_projection(
        PreReviewSource.model_validate(
            _source_payload(
                evidence=pending_evidence,
                issues=[_issue_payload(evidenceRefs=["evidence-debt"])],
                issueActions=[
                    {
                        "id": "action-source-link",
                        "issueId": "issue-revenue-1",
                        "actionType": "link_evidence",
                        "evidenceRef": "evidence-debt",
                    }
                ],
            )
        )
    )
    assert next(
        action
        for action in pending.actions
        if action.id == "action-issue-revenue-1-evidence"
    ).completed is False


def test_manual_review_action_completes_only_matching_manual_action() -> None:
    manual = calculate_pre_review_projection(
        PreReviewSource.model_validate(
            _source_payload(
                policies=[
                    _pass_policy(),
                    {
                        "id": "policy-debt-manual",
                        "ruleId": "DEBT-H-001",
                        "ruleVersion": "compare-business-rules-2026.08",
                        "title": "动产登记重复融资核验",
                        "result": "manual_review",
                        "gateTriggered": False,
                        "dimensionId": "debt",
                        "evidenceRefs": ["evidence-debt"],
                        "nextAction": "人工复核",
                        "explanation": "关键材料缺失，仅触发人工复核；不得据此自动拒绝。",
                    },
                ],
                issues=[_issue_payload(status="pending_gate", evidenceRefs=[])],
                issueActions=[
                    {
                        "id": "action-source-manual",
                        "issueId": "issue-revenue-1",
                        "actionType": "request_manual_review",
                    }
                ],
            )
        )
    )
    manual_action = next(
        action
        for action in manual.actions
        if action.action_type == "request_manual_review"
    )
    assert manual.issues[0].next_action == "request_manual_review"
    assert manual_action.completed is True
    assert manual_action.closure_requires == "human_review"
    assert manual.hard_gate.status == "manual_review"
    assert manual.hard_gate.manual_review_rule_ids == ["DEBT-H-001"]

    without_manual = calculate_pre_review_projection(
        PreReviewSource.model_validate(
            _source_payload(
                issues=[_issue_payload(status="pending_gate", evidenceRefs=[])],
                issueActions=[
                    {
                        "id": "action-source-link",
                        "issueId": "issue-revenue-1",
                        "actionType": "link_evidence",
                    }
                ],
            )
        )
    )
    without_manual_action = next(
        action
        for action in without_manual.actions
        if action.action_type == "request_manual_review"
    )
    assert without_manual_action.completed is False


def test_estimate_is_honest_rule_based_range_without_calibration() -> None:
    projection = calculate_pre_review_projection(
        PreReviewSource.model_validate(_source_payload())
    )
    estimate = projection.estimate

    assert estimate.estimate_kind == "rule_based_range"
    assert 0 <= estimate.min_days <= estimate.max_days <= 90
    assert "未使用历史数据校准" in estimate.disclaimer
    assert "不构成任何时限承诺" in estimate.disclaimer
    assert estimate.drivers
    assert estimate.next_action == "当前没有待补充事项；预审结果仍需人工审查确认。"

    with_todo = calculate_pre_review_projection(
        PreReviewSource.model_validate(
            _source_payload(issues=[_issue_payload(evidenceRefs=[])])
        )
    )
    first_incomplete = next(
        action for action in with_todo.actions if action.completed is False
    )
    assert with_todo.estimate.next_action == first_incomplete.description

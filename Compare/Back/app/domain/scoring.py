from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .constants import DIMENSION_IDS, DIMENSION_NAMES, RULE_VERSION
from .grading import clamp, equal_weighted_score, round1, score_to_grade
from .repayment import repayment_structure_score


_RATING_POINTS = {"A级": 96.0, "B级": 82.0, "C级": 65.0, "D级": 42.0, "E级": 18.0}
_QUALITY = {
    "verified": 1.0,
    "needs_review": 0.5,
    "missing": 0.0,
    "conflicting": 0.0,
    "unverifiable": 0.0,
}

SCORING_FACT_KEYS: tuple[str, ...] = (
    "registration_valid",
    "identity_consistency",
    "litigation_count",
    "prohibited_status",
    "supplier_rating",
    "brand_rating",
    "financing_ratio",
    "term_months",
    "repayment",
    "equipment_utilization",
    "output_consistency",
    "electricity_output_match",
    "process_completeness",
    "staff_stability",
    "order_income_coverage",
    "invoice_income_ratio",
    "collection_invoice_ratio",
    "net_margin",
    "rent_coverage",
    "debt_revenue_ratio",
    "short_debt_share",
    "debt_service_coverage",
    "duplicate_registration",
    "guarantee_obligation_ratio",
    "cashflow_revenue_match",
    "operating_counterparty_share",
    "cashflow_anomaly_rate",
    "net_inflow_ratio",
    "collection_cash_match",
)

HARD_GATE_FACT_KEYS: dict[str, str] = {
    "compliance.prohibited_status": "prohibited_status",
    "transaction.financing_ratio": "financing_ratio",
    "debt.duplicate_registration": "duplicate_registration",
}


@dataclass(frozen=True)
class DimensionAssessment:
    id: str
    score: float
    score_grade: str
    confidence: float
    summary: str


@dataclass(frozen=True)
class ConstraintAssessment:
    rule_id: str
    dimension_id: str
    title: str
    result: str
    gate_triggered: bool
    explanation: str
    evidence_key: str


@dataclass(frozen=True)
class ProjectAssessment:
    dimensions: tuple[DimensionAssessment, ...]
    overall_score: float
    score_grade: str
    decision_grade: str
    confidence: float
    risk_level: str
    constraints: tuple[ConstraintAssessment, ...]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _confidence(statuses: Sequence[str]) -> float:
    if not statuses:
        return 0.0
    return round1(_mean([_QUALITY.get(status, 0.0) for status in statuses]) * 100)


def _ratio_score(value: float, *, ideal: float = 1.0, penalty: float = 150.0) -> float:
    return clamp(100 - abs(value - ideal) * penalty)


def _finance_ratio_score(value: float) -> float:
    if value <= 0.75:
        return 96
    if value <= 0.85:
        return 86
    if value <= 0.95:
        return 64
    if value <= 1.0:
        return 34
    return 8


def _debt_ratio_score(value: float) -> float:
    if value <= 0.35:
        return 96
    if value <= 0.60:
        return 82
    if value <= 0.85:
        return 62
    if value <= 1.10:
        return 38
    return 16


def _hard_result(
    *, rule_id: str, dimension_id: str, title: str, adverse: bool, status: str, evidence_key: str
) -> ConstraintAssessment:
    if status != "verified":
        return ConstraintAssessment(
            rule_id, dimension_id, title, "manual_review", False,
            "关键材料缺失、冲突或无法核验，仅触发人工复核；不得据此自动拒绝。", evidence_key,
        )
    if adverse:
        return ConstraintAssessment(
            rule_id, dimension_id, title, "block", True,
            "已核验不利事实触发制度阻断；该结果独立于六维分数。", evidence_key,
        )
    return ConstraintAssessment(
        rule_id, dimension_id, title, "pass", False,
        "已核验事实未触发制度阻断。", evidence_key,
    )


def evaluate_project(
    facts: Mapping[str, float | int | bool | str],
    evidence_statuses: Mapping[str, str],
    repayment_points: Sequence[dict[str, float | int]],
) -> ProjectAssessment:
    """Derive six scores and governance results from facts, never outcome labels."""

    compliance = round1(
        0.45 * (100 if facts["registration_valid"] else 12)
        + 0.35 * float(facts["identity_consistency"])
        + 0.20 * clamp(100 - float(facts["litigation_count"]) * 18)
    )
    transaction = round1(_mean([
        _RATING_POINTS[str(facts["supplier_rating"])],
        _RATING_POINTS[str(facts["brand_rating"])],
        _finance_ratio_score(float(facts["financing_ratio"])),
        92 if int(facts["term_months"]) <= 36 else 76 if int(facts["term_months"]) <= 48 else 55,
        repayment_structure_score(repayment_points),
    ]))
    production = round1(_mean([
        clamp(float(facts["equipment_utilization"]) * 100),
        clamp(float(facts["output_consistency"]) * 100),
        clamp(float(facts["electricity_output_match"]) * 100),
        clamp(float(facts["process_completeness"]) * 100),
        clamp(float(facts["staff_stability"]) * 100),
    ]))
    revenue = round1(_mean([
        clamp(float(facts["order_income_coverage"]) / 1.05 * 100),
        _ratio_score(float(facts["invoice_income_ratio"])),
        clamp(float(facts["collection_invoice_ratio"]) * 100),
        clamp(float(facts["net_margin"]) / 0.15 * 100),
        clamp(float(facts["rent_coverage"]) / 2.0 * 100),
    ]))
    debt = round1(_mean([
        _debt_ratio_score(float(facts["debt_revenue_ratio"])),
        clamp(110 - float(facts["short_debt_share"]) * 100),
        clamp(float(facts["debt_service_coverage"]) / 1.8 * 100),
        25 if facts["duplicate_registration"] else 92,
        clamp(100 - float(facts["guarantee_obligation_ratio"]) * 180),
    ]))
    cashflow = round1(_mean([
        clamp(float(facts["cashflow_revenue_match"]) * 100),
        clamp(float(facts["operating_counterparty_share"]) * 100),
        clamp(100 - float(facts["cashflow_anomaly_rate"]) * 900),
        clamp((float(facts["net_inflow_ratio"]) + 0.05) / 0.20 * 100),
        clamp(float(facts["collection_cash_match"]) * 100),
    ]))
    scores = dict(zip(DIMENSION_IDS, (compliance, transaction, production, revenue, debt, cashflow)))

    scoped_statuses = {
        dimension_id: [
            status for key, status in evidence_statuses.items() if key.startswith(f"{dimension_id}.")
        ]
        for dimension_id in DIMENSION_IDS
    }
    dimensions = tuple(
        DimensionAssessment(
            id=dimension_id,
            score=scores[dimension_id],
            score_grade=score_to_grade(scores[dimension_id]),
            confidence=_confidence(scoped_statuses[dimension_id]),
            summary=f"{DIMENSION_NAMES[dimension_id]}由已核验业务事实按版本化规则计算；材料状态只影响置信度。",
        )
        for dimension_id in DIMENSION_IDS
    )
    constraints = (
        _hard_result(
            rule_id="CMP-H-001", dimension_id="compliance", title="禁入主体状态",
            adverse=bool(facts["prohibited_status"]),
            status=evidence_statuses.get("compliance.prohibited_status", "missing"),
            evidence_key="compliance.prohibited_status",
        ),
        _hard_result(
            rule_id="TRX-H-001", dimension_id="transaction", title="融资金额不得超过项目金额",
            adverse=float(facts["financing_ratio"]) > 1.0,
            status=evidence_statuses.get("transaction.financing_ratio", "missing"),
            evidence_key="transaction.financing_ratio",
        ),
        _hard_result(
            rule_id="DEBT-H-001", dimension_id="debt", title="动产登记重复融资核验",
            adverse=bool(facts["duplicate_registration"]),
            status=evidence_statuses.get("debt.duplicate_registration", "missing"),
            evidence_key="debt.duplicate_registration",
        ),
    )
    overall_score = equal_weighted_score(item.score for item in dimensions)
    score_grade = score_to_grade(overall_score)
    blocked = any(item.result == "block" for item in constraints)
    manual = any(item.result == "manual_review" for item in constraints)
    confidence = round1(_mean([item.confidence for item in dimensions]))
    decision_grade = "E" if blocked else score_grade
    if blocked:
        risk_level = "forbid"
    elif min(item.score for item in dimensions) < 40 or overall_score < 50:
        risk_level = "risk"
    elif manual or confidence < 60:
        risk_level = "confirm"
    elif overall_score < 80 or min(item.score for item in dimensions) < 60:
        risk_level = "attention"
    else:
        risk_level = "support"
    return ProjectAssessment(
        dimensions=dimensions,
        overall_score=overall_score,
        score_grade=score_grade,
        decision_grade=decision_grade,
        confidence=confidence,
        risk_level=risk_level,
        constraints=constraints,
    )


__all__ = [
    "ConstraintAssessment",
    "DimensionAssessment",
    "HARD_GATE_FACT_KEYS",
    "ProjectAssessment",
    "RULE_VERSION",
    "SCORING_FACT_KEYS",
    "evaluate_project",
]

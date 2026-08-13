"""Focused invariants for the P4 business-rule domain modules."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.contracts.workbench import ReviewEvidenceSelectionGroup
from app.domain.constants import DIMENSION_IDS
from app.domain.evidence import (
    build_evidence_targets,
    build_selection_group,
    validate_locators,
)
from app.domain.grading import equal_weighted_score, round1, score_to_grade
from app.domain.repayment import (
    build_repayment_points,
    classify_repayment_structure,
    repayment_structure_label,
    repayment_structure_score,
)
from app.domain.scoring import evaluate_project


@pytest.mark.parametrize(
    ("score", "expected_grade"),
    (
        (0, "E"),
        (19.94, "E"),
        (19.95, "D"),
        (39.94, "D"),
        (39.95, "C"),
        (59.94, "C"),
        (59.95, "B"),
        (79.94, "B"),
        (79.95, "A"),
        (100, "A"),
    ),
)
def test_grade_boundaries_apply_round_half_up_before_classification(
    score: float,
    expected_grade: str,
) -> None:
    assert score_to_grade(score) == expected_grade


def test_round_half_up_is_decimal_not_bankers_rounding() -> None:
    assert round1(79.85) == 79.9
    assert round1(79.95) == 80.0


def test_six_dimensions_are_equal_weight_and_exactly_six_are_required() -> None:
    single_dimension_contributions = [
        equal_weighted_score(100 if index == active else 0 for index in range(6))
        for active in range(6)
    ]

    assert DIMENSION_IDS == (
        "compliance",
        "transaction",
        "production",
        "revenue",
        "debt",
        "cashflow",
    )
    assert single_dimension_contributions == [16.7] * 6
    assert equal_weighted_score((100, 80, 60, 40, 20, 0)) == 50.0
    with pytest.raises(ValueError, match="exactly six"):
        equal_weighted_score((100, 80, 60, 40, 20))


def test_repayment_risk_order_is_derived_from_actual_principal_schedules() -> None:
    schedules = {
        structure: build_repayment_points(
            financed_amount=1_200_000,
            term_months=12,
            annual_rate=0.06,
            structure=structure,
        )
        for structure in ("front_loaded", "balanced", "back_loaded")
    }

    assert {
        structure: classify_repayment_structure(points)
        for structure, points in schedules.items()
    } == {
        "front_loaded": "front_loaded",
        "balanced": "balanced",
        "back_loaded": "back_loaded",
    }
    assert schedules["front_loaded"][0]["principal"] > schedules["front_loaded"][-1]["principal"]
    assert schedules["balanced"][0]["principal"] == schedules["balanced"][-1]["principal"]
    assert schedules["back_loaded"][0]["principal"] < schedules["back_loaded"][-1]["principal"]

    scores = {
        structure: repayment_structure_score(points)
        for structure, points in schedules.items()
    }
    assert scores["front_loaded"] > scores["balanced"] > scores["back_loaded"]
    assert {
        structure: repayment_structure_label(points)
        for structure, points in schedules.items()
    } == {
        "front_loaded": "前高后低",
        "balanced": "均衡",
        "back_loaded": "前低后高",
    }
    for points in schedules.values():
        assert sum(float(point["principal"]) for point in points) == pytest.approx(
            1_200_000,
            abs=0.01,
        )


def _high_quality_facts() -> dict[str, float | int | bool | str]:
    return {
        "registration_valid": True,
        "identity_consistency": 100,
        "litigation_count": 0,
        "supplier_rating": "A级",
        "brand_rating": "A级",
        "financing_ratio": 0.70,
        "term_months": 24,
        "equipment_utilization": 1.0,
        "output_consistency": 1.0,
        "electricity_output_match": 1.0,
        "process_completeness": 1.0,
        "staff_stability": 1.0,
        "order_income_coverage": 1.05,
        "invoice_income_ratio": 1.0,
        "collection_invoice_ratio": 1.0,
        "net_margin": 0.15,
        "rent_coverage": 2.0,
        "debt_revenue_ratio": 0.30,
        "short_debt_share": 0.10,
        "debt_service_coverage": 1.8,
        "duplicate_registration": False,
        "guarantee_obligation_ratio": 0.0,
        "cashflow_revenue_match": 1.0,
        "operating_counterparty_share": 1.0,
        "cashflow_anomaly_rate": 0.0,
        "net_inflow_ratio": 0.15,
        "collection_cash_match": 1.0,
        "prohibited_status": False,
    }


def _verified_evidence_statuses() -> dict[str, str]:
    statuses = {f"{dimension_id}.source": "verified" for dimension_id in DIMENSION_IDS}
    statuses.update(
        {
            "compliance.prohibited_status": "verified",
            "transaction.financing_ratio": "verified",
            "debt.duplicate_registration": "verified",
        }
    )
    return statuses


def _balanced_schedule() -> list[dict[str, float | int]]:
    return build_repayment_points(
        financed_amount=1_200_000,
        term_months=24,
        annual_rate=0.06,
        structure="balanced",
    )


def test_verified_adverse_fact_triggers_hard_gate_without_rewriting_score_grade() -> None:
    facts = _high_quality_facts()
    facts["prohibited_status"] = True

    assessment = evaluate_project(
        facts,
        _verified_evidence_statuses(),
        _balanced_schedule(),
    )
    constraint = next(
        item for item in assessment.constraints if item.rule_id == "CMP-H-001"
    )

    assert assessment.score_grade == "A"
    assert assessment.decision_grade == "E"
    assert assessment.risk_level == "forbid"
    assert constraint.result == "block"
    assert constraint.gate_triggered is True


@pytest.mark.parametrize("evidence_status", ("missing", "needs_review", "unverifiable"))
def test_unverified_adverse_fact_requires_manual_review_not_automatic_rejection(
    evidence_status: str,
) -> None:
    facts = _high_quality_facts()
    facts["prohibited_status"] = True
    statuses = _verified_evidence_statuses()
    statuses["compliance.prohibited_status"] = evidence_status

    assessment = evaluate_project(facts, statuses, _balanced_schedule())
    constraint = next(
        item for item in assessment.constraints if item.rule_id == "CMP-H-001"
    )

    assert assessment.score_grade == "A"
    assert assessment.decision_grade == "A"
    assert assessment.risk_level == "confirm"
    assert constraint.result == "manual_review"
    assert constraint.gate_triggered is False
    assert "不得据此自动拒绝" in constraint.explanation


def _excel_material() -> dict[str, object]:
    return {
        "id": "material-excel-1",
        "versionId": "material-excel-1-v1",
        "kind": "excel",
        "sheets": [
            {
                "name": "核验表",
                "columns": ["字段", "值"],
                "rows": [["登记状态", "有效"], ["禁入状态", "未命中"]],
            }
        ],
    }


def _excel_evidence(cell_range: str) -> dict[str, object]:
    return {
        "id": "evidence-excel-1",
        "locationStatus": "located",
        "locator": {
            "kind": "excel",
            "materialId": "material-excel-1",
            "materialVersionId": "material-excel-1-v1",
            "sheet": "核验表",
            "range": cell_range,
        },
    }


def test_excel_locator_uses_row_four_as_first_business_data_row() -> None:
    material = _excel_material()

    validate_locators([material], [_excel_evidence("A4:B4")])
    validate_locators([material], [_excel_evidence("A5:B5")])
    with pytest.raises(ValueError, match="invalid Excel range"):
        validate_locators([material], [_excel_evidence("A4")])
    with pytest.raises(ValueError, match="Excel range exceeds material bounds"):
        validate_locators([material], [_excel_evidence("A3:B4")])
    with pytest.raises(ValueError, match="Excel range exceeds material bounds"):
        validate_locators([material], [_excel_evidence("A6:B6")])


def test_multi_evidence_selection_group_is_atomic_and_contract_valid() -> None:
    targets = build_evidence_targets(
        evidence_refs=("evidence-1", "evidence-2", "evidence-1"),
        dimension_id="transaction",
        review_target_id="transaction-equipment-price",
        fact_version_id="fact-equipment-price-v1",
    )
    group = build_selection_group(targets)
    validated = ReviewEvidenceSelectionGroup.model_validate(group)

    assert [target["evidenceRef"] for target in targets] == [
        "evidence-1",
        "evidence-2",
    ]
    assert all(
        target["evidenceRefs"] == ["evidence-1", "evidence-2"]
        for target in targets
    )
    assert validated.id == (
        "transaction::transaction-equipment-price::fact-equipment-price-v1::"
        "evidence-1::evidence-2"
    )

    with pytest.raises(ValueError, match="atomic evidence group"):
        build_selection_group(targets[:1])

    non_atomic = deepcopy(targets)
    non_atomic[1]["evidenceRefs"] = ["evidence-2"]
    with pytest.raises(ValueError, match="atomic evidence group"):
        build_selection_group(non_atomic)

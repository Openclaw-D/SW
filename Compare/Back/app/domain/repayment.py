from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Sequence

from .grading import round1

RepaymentStructure = Literal["front_loaded", "balanced", "back_loaded"]


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_repayment_points(
    financed_amount: float,
    term_months: int,
    annual_rate: float,
    structure: RepaymentStructure,
) -> list[dict[str, float | int]]:
    """Build a reconciled principal/interest/rent schedule from actual cash flows."""

    if financed_amount <= 0 or term_months <= 0:
        raise ValueError("financed amount and term must be positive")
    if annual_rate < 0:
        raise ValueError("annual rate cannot be negative")
    principal = _money(Decimal(str(financed_amount)))
    monthly_rate = Decimal(str(annual_rate)) / Decimal(12)
    if structure == "balanced":
        weights = [Decimal(1)] * term_months
    else:
        low, high = Decimal("0.45"), Decimal("1.55")
        step = (high - low) / Decimal(max(1, term_months - 1))
        ascending = [low + step * index for index in range(term_months)]
        weights = list(reversed(ascending)) if structure == "front_loaded" else ascending
    weight_total = sum(weights)
    balance = principal
    assigned = Decimal(0)
    rows: list[dict[str, float | int]] = []
    for index, weight in enumerate(weights):
        principal_paid = (
            principal - assigned
            if index == term_months - 1
            else _money(principal * weight / weight_total)
        )
        principal_paid = min(balance, principal_paid)
        interest = _money(balance * monthly_rate)
        rent = _money(principal_paid + interest)
        balance = _money(balance - principal_paid)
        assigned += principal_paid
        rows.append(
            {
                "period": index + 1,
                "principal": float(principal_paid),
                "interest": float(interest),
                "rent": float(rent),
            }
        )
    if abs(sum(Decimal(str(row["principal"])) for row in rows) - principal) > Decimal("0.01"):
        raise AssertionError("repayment principal does not reconcile")
    return rows


def classify_repayment_structure(points: Sequence[dict[str, float | int]]) -> RepaymentStructure:
    if len(points) < 3:
        raise ValueError("at least three repayment points are required")
    third = max(1, len(points) // 3)
    total = sum(float(point["principal"]) for point in points)
    if total <= 0:
        raise ValueError("repayment principal total must be positive")
    first_share = sum(float(point["principal"]) for point in points[:third]) / total
    last_share = sum(float(point["principal"]) for point in points[-third:]) / total
    if first_share - last_share >= 0.08:
        return "front_loaded"
    if last_share - first_share >= 0.08:
        return "back_loaded"
    return "balanced"


def repayment_structure_score(points: Sequence[dict[str, float | int]]) -> float:
    """Higher is safer: front-loaded > balanced > back-loaded."""

    return {
        "front_loaded": 95.0,
        "balanced": 76.0,
        "back_loaded": 32.0,
    }[classify_repayment_structure(points)]


def repayment_structure_label(points: Sequence[dict[str, float | int]]) -> str:
    return {
        "front_loaded": "前高后低",
        "balanced": "均衡",
        "back_loaded": "前低后高",
    }[classify_repayment_structure(points)]


__all__ = [
    "RepaymentStructure",
    "build_repayment_points",
    "classify_repayment_structure",
    "repayment_structure_label",
    "repayment_structure_score",
]

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


def round1(value: float) -> float:
    """Round once, half-up, before applying the frozen grade boundary."""

    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return min(high, max(low, value))


def score_to_grade(score: float) -> str:
    rounded = round1(clamp(score))
    if rounded >= 80:
        return "A"
    if rounded >= 60:
        return "B"
    if rounded >= 40:
        return "C"
    if rounded >= 20:
        return "D"
    return "E"


def equal_weighted_score(scores: Iterable[float]) -> float:
    values = tuple(scores)
    if len(values) != 6:
        raise ValueError("the frozen workbench requires exactly six equal-weight dimensions")
    return round1(sum(values) / 6)


__all__ = ["clamp", "equal_weighted_score", "round1", "score_to_grade"]

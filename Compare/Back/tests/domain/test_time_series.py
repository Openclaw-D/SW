from __future__ import annotations

from copy import deepcopy

import pytest

from app.contracts.workbench import (
    AvailableDimensionSeriesResponse,
    UnavailableDimensionSeriesResponse,
)
from app.domain.time_series import aggregate_dimension_series


def _request(**overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "projectId": "project-sim-001",
        "dimensionId": "production",
        "metricIds": ["total"],
        "grain": "day",
        "startDate": "2024-01-01",
        "endDate": "2024-12-31",
        "timezone": "Asia/Shanghai",
    }
    request.update(overrides)
    return request


def _series(
    *,
    observations: list[dict[str, object]] | None = None,
    supported_grains: list[str] | None = None,
) -> dict[str, object]:
    return {
        "dimensionId": "production",
        "supportedGrains": supported_grains
        if supported_grains is not None
        else ["day", "week", "month", "year"],
        "metrics": [
            {"id": "total", "label": "合计", "unit": "件", "aggregation": "sum"},
            {"id": "rate", "label": "利用率", "unit": "%", "aggregation": "average"},
            {"id": "stock", "label": "期末人数", "unit": "人", "aggregation": "last"},
        ],
        "observations": observations
        if observations is not None
        else [
            {
                "id": "total-leap-day",
                "date": "2024-02-29",
                "metricId": "total",
                "value": 5,
                "evidenceRefs": ["evidence-leap-day"],
                "isSimulated": True,
            }
        ],
        "sourceLabel": "统一脱敏模拟时序数据",
        "isSimulated": True,
    }


@pytest.mark.parametrize(
    ("grain", "period_start", "period_end", "label"),
    [
        ("day", "2024-02-29", "2024-02-29", "02-29"),
        ("week", "2024-02-26", "2024-03-03", "02-26周"),
        ("month", "2024-02-01", "2024-02-29", "2024年2月"),
        ("year", "2024-01-01", "2024-12-31", "2024"),
    ],
)
def test_calendar_grains_have_deterministic_complete_period_boundaries(
    grain: str, period_start: str, period_end: str, label: str
) -> None:
    result = aggregate_dimension_series(
        _series(),
        _request(
            grain=grain,
            startDate="2024-02-29",
            endDate="2024-02-29",
        ),
    )

    assert result["status"] == "available"
    point = result["points"][0]
    assert (point["periodStart"], point["periodEnd"], point["label"]) == (
        period_start,
        period_end,
        label,
    )
    AvailableDimensionSeriesResponse.model_validate(result)


def test_sum_average_and_last_use_stable_date_id_order_and_all_evidence() -> None:
    observations = [
        {
            "id": "sum-b",
            "date": "2024-01-01",
            "metricId": "total",
            "value": 2,
            "evidenceRefs": ["sum-b", "shared"],
        },
        {
            "id": "sum-a",
            "date": "2024-01-01",
            "metricId": "total",
            "value": 1,
            "evidenceRefs": ["sum-a", "shared"],
        },
        {
            "id": "average-b",
            "date": "2024-01-01",
            "metricId": "rate",
            "value": 4,
            "evidenceRefs": ["average-b", "shared"],
        },
        {
            "id": "average-a",
            "date": "2024-01-01",
            "metricId": "rate",
            "value": 2,
            "evidenceRefs": ["average-a", "shared"],
        },
        {
            "id": "last-b",
            "date": "2024-01-02",
            "metricId": "stock",
            "value": 9,
            "evidenceRefs": ["last-b", "shared"],
        },
        {
            "id": "last-a",
            "date": "2024-01-02",
            "metricId": "stock",
            "value": 1,
            "evidenceRefs": ["last-a", "shared"],
        },
        {
            "id": "last-z-older",
            "date": "2024-01-01",
            "metricId": "stock",
            "value": 99,
            "evidenceRefs": ["last-older"],
        },
    ]
    request = _request(
        metricIds=["total", "rate", "stock", "stock"],
        grain="month",
        startDate="2024-01-01",
        endDate="2024-01-31",
    )

    result = aggregate_dimension_series(_series(observations=observations), request)

    assert result["status"] == "available"
    assert result["request"]["metricIds"] == ["total", "rate", "stock"]
    measures = {measure["label"]: measure for measure in result["points"][0]["measures"]}
    assert measures["合计"]["value"] == 3.0
    assert measures["利用率"]["value"] == 3.0
    assert measures["期末人数"]["value"] == 9.0
    assert measures["合计"]["evidenceRefs"] == ["sum-a", "shared", "sum-b"]
    assert measures["利用率"]["evidenceRefs"] == [
        "average-a",
        "shared",
        "average-b",
    ]
    assert measures["期末人数"]["evidenceRefs"] == [
        "last-older",
        "last-a",
        "shared",
        "last-b",
    ]


def test_week_starts_on_monday_across_a_year_boundary() -> None:
    observations = [
        {
            "id": "new-years-eve",
            "date": "2024-12-31",
            "metricId": "total",
            "value": 1,
            "evidenceRefs": ["evidence-new-years-eve"],
        }
    ]
    result = aggregate_dimension_series(
        _series(observations=observations),
        _request(
            grain="week", startDate="2024-12-31", endDate="2024-12-31"
        ),
    )

    point = result["points"][0]
    assert point["periodStart"] == "2024-12-30"
    assert point["periodEnd"] == "2025-01-05"


def test_empty_range_returns_the_frozen_unavailable_shape_without_mutation() -> None:
    series = _series(observations=[])
    request = _request()
    original_series = deepcopy(series)
    original_request = deepcopy(request)

    result = aggregate_dimension_series(series, request)

    assert result == {
        "status": "empty",
        "request": request,
        "points": [],
        "message": "所选日期范围没有可验证记录。",
        "sourceLabel": "统一脱敏模拟时序数据",
        "isSimulated": True,
    }
    UnavailableDimensionSeriesResponse.model_validate(result)
    assert series == original_series
    assert request == original_request


@pytest.mark.parametrize(
    "overrides",
    [
        {"projectId": ""},
        {"dimensionId": "risk"},
        {"metricIds": []},
        {"startDate": "2024-02-30"},
        {"startDate": "2024-03-01", "endDate": "2024-02-29"},
        {"timezone": ""},
        {"timezone": "Mars"},
        {"grain": "quarter"},
    ],
)
def test_invalid_request_fields_return_invalid_shape(overrides: dict[str, object]) -> None:
    result = aggregate_dimension_series(_series(), _request(**overrides))

    assert result["status"] == "invalid"
    assert result["points"] == []
    assert set(result) == {
        "status",
        "request",
        "points",
        "message",
        "sourceLabel",
        "isSimulated",
    }


def test_unsupported_grain_and_invalid_observations_never_report_available() -> None:
    unsupported = aggregate_dimension_series(
        _series(supported_grains=["month", "year"]),
        _request(grain="day"),
    )
    assert unsupported["status"] == "unavailable"
    UnavailableDimensionSeriesResponse.model_validate(unsupported)

    invalid_observations = deepcopy(_series())
    invalid_observations["observations"][0]["evidenceRefs"] = []
    invalid = aggregate_dimension_series(invalid_observations, _request())
    assert invalid["status"] == "invalid"
    assert invalid["points"] == []

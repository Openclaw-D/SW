"""Deterministic calendar aggregation for the frozen workbench time-series contract."""

from __future__ import annotations

import calendar
import math
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


_DIMENSION_IDS = frozenset(
    {"compliance", "transaction", "production", "revenue", "debt", "cashflow"}
)
_TIME_GRAINS = frozenset({"day", "week", "month", "year"})
_TIME_AGGREGATIONS = frozenset({"sum", "average", "last"})
_DEFAULT_SOURCE_LABEL = "统一脱敏时序数据"
_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_TIMEZONE_PATTERN = re.compile(
    r"(?:UTC|GMT|[A-Za-z][A-Za-z0-9._+-]*(?:/[A-Za-z0-9._+-]+)+)\Z"
)


@dataclass(frozen=True)
class _Metric:
    id: str
    label: str
    unit: str
    aggregation: str


@dataclass(frozen=True)
class _Observation:
    id: str
    date: date
    metric_id: str
    value: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class _Bucket:
    id: str
    label: str
    start: str
    end: str


def aggregate_dimension_series(
    series_mapping: Mapping[str, object] | None,
    request_mapping: Mapping[str, object],
) -> dict[str, Any]:
    """Aggregate one camelCase ``DimensionTimeSeries`` mapping.

    The function deliberately returns contract-shaped ``invalid``, ``empty``, or
    ``unavailable`` values for all expected data problems. It never mutates either
    input and does not depend on locale, the host timezone, or third-party packages.
    Date-only observations are grouped as calendar dates in the requested timezone;
    the timezone identifier is validated but no instant conversion is necessary.
    """

    request = _request_snapshot(request_mapping)
    source_label = _source_label(series_mapping)

    request_error = _validate_request(request)
    if request_error is not None:
        return _unavailable("invalid", request, request_error, source_label)

    dimension_id = request["dimensionId"]
    grain = request["grain"]
    requested_metric_ids = request["metricIds"]
    assert isinstance(dimension_id, str)
    assert isinstance(grain, str)
    assert isinstance(requested_metric_ids, list)

    if not isinstance(series_mapping, Mapping) or series_mapping.get(
        "dimensionId"
    ) != dimension_id:
        return _unavailable(
            "unavailable",
            request,
            "当前维度没有可用的时序接口。",
            source_label,
        )

    supported_grains = _string_list(series_mapping.get("supportedGrains"))
    if supported_grains is None or any(
        item not in _TIME_GRAINS for item in supported_grains
    ):
        return _unavailable(
            "invalid", request, "时序数据的可用粒度定义无效。", source_label
        )
    if grain not in supported_grains:
        return _unavailable(
            "unavailable",
            request,
            f"当前维度不适用{grain}粒度。",
            source_label,
        )

    metrics = _parse_metrics(series_mapping.get("metrics"))
    if metrics is None:
        return _unavailable(
            "invalid", request, "时序指标定义无效。", source_label
        )
    metric_by_id = {metric.id: metric for metric in metrics}
    metric_ids = _deduplicate(requested_metric_ids)
    if any(metric_id not in metric_by_id for metric_id in metric_ids):
        return _unavailable(
            "invalid", request, "请求包含未知或空指标。", source_label
        )

    observations = _parse_observations(
        series_mapping.get("observations"), metric_by_id
    )
    if observations is None:
        return _unavailable(
            "invalid",
            request,
            "时序记录缺少合法日期、数值或证据引用。",
            source_label,
        )

    start_date = _parse_iso_date(request["startDate"])
    end_date = _parse_iso_date(request["endDate"])
    assert start_date is not None and end_date is not None
    selected_metric_ids = set(metric_ids)
    selected = sorted(
        (
            observation
            for observation in observations
            if observation.metric_id in selected_metric_ids
            and start_date <= observation.date <= end_date
        ),
        key=lambda observation: (
            observation.date,
            observation.id,
            observation.metric_id,
        ),
    )
    if not selected:
        return _unavailable(
            "empty", request, "所选日期范围没有可验证记录。", source_label
        )

    buckets: dict[str, tuple[_Bucket, list[_Observation]]] = {}
    try:
        for observation in selected:
            bucket = _calendar_bucket(observation.date, grain)
            current = buckets.setdefault(bucket.id, (bucket, []))
            current[1].append(observation)
    except (OverflowError, ValueError):
        return _unavailable(
            "invalid", request, "时序记录超出可聚合的公历范围。", source_label
        )

    points: list[dict[str, Any]] = []
    for bucket_id in sorted(buckets):
        bucket, bucket_observations = buckets[bucket_id]
        measures: list[dict[str, Any]] = []
        for metric_id in metric_ids:
            records = [
                observation
                for observation in bucket_observations
                if observation.metric_id == metric_id
            ]
            if not records:
                continue
            metric = metric_by_id[metric_id]
            value = _aggregate_value(records, metric.aggregation)
            if value is None:
                return _unavailable(
                    "invalid",
                    request,
                    "时序聚合结果超出有限数值范围。",
                    source_label,
                )
            measures.append(
                {
                    "id": (
                        f"timeseries-{dimension_id}-{grain}-{bucket_id}-{metric_id}"
                    ),
                    "label": metric.label,
                    "value": value,
                    "unit": metric.unit,
                    "evidenceRefs": _merged_evidence_refs(records),
                }
            )

        # A bucket originates from at least one selected observation, so this is
        # defensive rather than a silently successful empty chart point.
        if not measures:
            continue
        points.append(
            {
                "id": f"timeseries-{dimension_id}-{grain}-{bucket_id}",
                "label": bucket.label,
                "note": f"{bucket.start} 至 {bucket.end} · {source_label}",
                "periodStart": bucket.start,
                "periodEnd": bucket.end,
                "measures": measures,
            }
        )

    if not points:
        return _unavailable(
            "empty", request, "所选日期范围没有可验证记录。", source_label
        )

    available_request = dict(request)
    available_request["metricIds"] = metric_ids
    return {
        "status": "available",
        "request": available_request,
        "points": points,
        "sourceLabel": source_label,
        "isSimulated": True,
    }


def _request_snapshot(request_mapping: object) -> dict[str, Any]:
    mapping: Mapping[str, object]
    if isinstance(request_mapping, Mapping):
        mapping = request_mapping
    else:
        mapping = {}

    metric_ids_value = mapping.get("metricIds", [])
    if _is_sequence(metric_ids_value):
        metric_ids: list[object] = list(metric_ids_value)
    else:
        metric_ids = []
    return {
        "projectId": _string_or_empty(mapping.get("projectId")),
        "dimensionId": _string_or_empty(mapping.get("dimensionId")),
        "metricIds": metric_ids,
        "grain": _string_or_empty(mapping.get("grain")),
        "startDate": _string_or_empty(mapping.get("startDate")),
        "endDate": _string_or_empty(mapping.get("endDate")),
        "timezone": _string_or_empty(mapping.get("timezone")),
    }


def _validate_request(request: Mapping[str, object]) -> str | None:
    project_id = request.get("projectId")
    if not isinstance(project_id, str) or not project_id.strip():
        return "projectId 不能为空。"

    dimension_id = request.get("dimensionId")
    if not isinstance(dimension_id, str) or dimension_id not in _DIMENSION_IDS:
        return "dimensionId 无效。"

    metric_ids = request.get("metricIds")
    if not isinstance(metric_ids, list) or not metric_ids or any(
        not isinstance(metric_id, str) or not metric_id.strip()
        for metric_id in metric_ids
    ):
        return "请求包含未知或空指标。"

    start_date = _parse_iso_date(request.get("startDate"))
    end_date = _parse_iso_date(request.get("endDate"))
    if start_date is None or end_date is None or start_date > end_date:
        return "起止日期范围无效。"

    timezone = request.get("timezone")
    if not isinstance(timezone, str) or not _TIMEZONE_PATTERN.fullmatch(timezone):
        return "时区标识无效。"

    grain = request.get("grain")
    if not isinstance(grain, str) or grain not in _TIME_GRAINS:
        return "grain 无效。"
    return None


def _parse_metrics(value: object) -> list[_Metric] | None:
    if not _is_sequence(value):
        return None
    metrics: list[_Metric] = []
    seen_ids: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            return None
        metric_id = item.get("id")
        label = item.get("label")
        unit = item.get("unit")
        aggregation = item.get("aggregation")
        if (
            not isinstance(metric_id, str)
            or not metric_id.strip()
            or metric_id in seen_ids
            or not isinstance(label, str)
            or not isinstance(unit, str)
            or not isinstance(aggregation, str)
            or aggregation not in _TIME_AGGREGATIONS
        ):
            return None
        seen_ids.add(metric_id)
        metrics.append(_Metric(metric_id, label, unit, aggregation))
    return metrics


def _parse_observations(
    value: object, metric_by_id: Mapping[str, _Metric]
) -> list[_Observation] | None:
    if not _is_sequence(value):
        return None
    observations: list[_Observation] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        observation_id = item.get("id")
        date_text = item.get("date")
        metric_id = item.get("metricId")
        raw_value = item.get("value")
        evidence_refs = _string_list(item.get("evidenceRefs"))
        parsed_date = _parse_iso_date(date_text)
        numeric_value = _finite_float(raw_value)
        if (
            not isinstance(observation_id, str)
            or not observation_id.strip()
            or not isinstance(date_text, str)
            or parsed_date is None
            or not isinstance(metric_id, str)
            or metric_id not in metric_by_id
            or numeric_value is None
            or evidence_refs is None
            or not evidence_refs
            or any(not evidence_ref.strip() for evidence_ref in evidence_refs)
        ):
            return None
        observations.append(
            _Observation(
                id=observation_id,
                date=parsed_date,
                metric_id=metric_id,
                value=numeric_value,
                evidence_refs=tuple(evidence_refs),
            )
        )
    return observations


def _calendar_bucket(value: date, grain: str) -> _Bucket:
    date_text = value.isoformat()
    if grain == "day":
        return _Bucket(date_text, date_text[5:], date_text, date_text)
    if grain == "week":
        start = value - timedelta(days=value.weekday())
        end = start + timedelta(days=6)
        start_text = start.isoformat()
        return _Bucket(start_text, f"{start_text[5:]}周", start_text, end.isoformat())
    if grain == "month":
        month_id = f"{value.year:04d}-{value.month:02d}"
        start = f"{month_id}-01"
        end = f"{month_id}-{calendar.monthrange(value.year, value.month)[1]:02d}"
        return _Bucket(month_id, f"{value.year}年{value.month}月", start, end)
    if grain == "year":
        year_id = f"{value.year:04d}"
        return _Bucket(year_id, year_id, f"{year_id}-01-01", f"{year_id}-12-31")
    raise ValueError(f"unsupported time grain: {grain}")


def _aggregate_value(records: Sequence[_Observation], aggregation: str) -> float | None:
    try:
        if aggregation == "sum":
            raw_value = math.fsum(record.value for record in records)
        elif aggregation == "average":
            raw_value = math.fsum(record.value for record in records) / len(records)
        elif aggregation == "last":
            # Records have already been sorted by calendar date and stable ID.
            raw_value = records[-1].value
        else:
            return None
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    if not math.isfinite(raw_value):
        return None
    return _round_one(raw_value)


def _round_one(value: float) -> float:
    """Match the Front's Math.round((value + Number.EPSILON) * 10) / 10."""

    scaled = (value + sys.float_info.epsilon) * 10
    if not math.isfinite(scaled):
        return value
    rounded = math.floor(scaled + 0.5) / 10
    return 0.0 if rounded == 0 else rounded


def _merged_evidence_refs(records: Sequence[_Observation]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for record in records:
        for evidence_ref in record.evidence_refs:
            if evidence_ref not in seen:
                seen.add(evidence_ref)
                merged.append(evidence_ref)
    return merged


def _parse_iso_date(value: object) -> date | None:
    if not isinstance(value, str) or not _ISO_DATE_PATTERN.fullmatch(value):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _source_label(series_mapping: object) -> str:
    if isinstance(series_mapping, Mapping):
        source_label = series_mapping.get("sourceLabel")
        if isinstance(source_label, str) and source_label:
            return source_label
    return _DEFAULT_SOURCE_LABEL


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _unavailable(
    status: str,
    request: Mapping[str, object],
    message: str,
    source_label: str,
) -> dict[str, Any]:
    request_copy = dict(request)
    metric_ids = request_copy.get("metricIds")
    request_copy["metricIds"] = list(metric_ids) if isinstance(metric_ids, list) else []
    return {
        "status": status,
        "request": request_copy,
        "points": [],
        "message": message,
        "sourceLabel": source_label,
        "isSimulated": True,
    }


def _deduplicate(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _string_list(value: object) -> list[str] | None:
    if not _is_sequence(value):
        return None
    result = list(value)
    return result if all(isinstance(item, str) for item in result) else None


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _string_or_empty(value: object) -> str:
    return value if isinstance(value, str) else ""

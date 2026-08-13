import { useEffect, useRef, useState } from "react";
import type { DimensionId, DimensionSeriesRequest, DimensionSeriesResponse, TimeGrain } from "../contracts/workbench";
import { createTimeSeriesRequest, resolveTimeSeriesRange } from "../lib/workbenchLogic";
import { copy, formatDimensionName, usePublicLocale } from "../lib/publicLocale";

const grains: Array<{ id: TimeGrain; english: string; chinese: string }> = [
  { id: "day", english: "Day", chinese: "日" },
  { id: "week", english: "Week", chinese: "周" },
  { id: "month", english: "Month", chinese: "月" },
  { id: "year", english: "Year", chinese: "年" },
];

export function TimeSeriesControls({
  projectId,
  dimensionId,
  metricIds,
  supportedGrains,
  query,
  onRequest,
  onResponse,
}: {
  projectId: string;
  dimensionId: DimensionId;
  metricIds: string[];
  supportedGrains: TimeGrain[];
  query: (request: DimensionSeriesRequest) => Promise<DimensionSeriesResponse>;
  onRequest?: (request: DimensionSeriesRequest) => void;
  onResponse: (response: DimensionSeriesResponse | null) => void;
}) {
  const locale = usePublicLocale();
  const [grain, setGrain] = useState<TimeGrain>(supportedGrains.includes("month") ? "month" : supportedGrains[0]);
  const [range, setRange] = useState(() => resolveTimeSeriesRange());
  const { startDate, endDate } = range;
  const [state, setState] = useState<{ kind: "loading" | "available" | "empty" | "unavailable" | "invalid" | "error"; count?: number }>({ kind: "loading" });
  const requestSequence = useRef(0);
  const queryRef = useRef(query);
  const onRequestRef = useRef(onRequest);
  const onResponseRef = useRef(onResponse);
  queryRef.current = query;
  onRequestRef.current = onRequest;
  onResponseRef.current = onResponse;

  useEffect(() => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setState({ kind: "loading" });
    const request = createTimeSeriesRequest({ projectId, dimensionId, metricIds, grain, startDate, endDate });
    onRequestRef.current?.(request);
    queryRef.current(request).then((response) => {
      if (requestSequence.current !== sequence) return;
      onResponseRef.current(response);
      setState(response.status === "available" ? { kind: "available", count: response.points.length } : { kind: response.status });
    }).catch(() => {
      if (requestSequence.current !== sequence) return;
      onResponseRef.current(null);
      setState({ kind: "error" });
    });
  }, [dimensionId, endDate, grain, metricIds.join("|"), projectId, startDate]);

  const changeGrain = (next: TimeGrain) => {
    if (!supportedGrains.includes(next)) return;
    setGrain(next);
  };

  const stateLabel = state.kind === "loading" ? copy(locale, "Loading", "读取中")
    : state.kind === "available" ? copy(locale, `${state.count ?? 0} periods`, `${state.count ?? 0} 个时段`)
      : state.kind === "empty" ? copy(locale, "No data in this range", "区间无数据")
        : state.kind === "unavailable" ? copy(locale, "Grain unavailable for these facts", "粒度不适用")
          : state.kind === "invalid" ? copy(locale, "Invalid date range", "范围无效")
            : copy(locale, "Loading failed", "读取失败");
  const dimensionName = formatDimensionName(dimensionId, locale);

  return (
    <div className="time-series-controls" data-dimension-id={dimensionId}>
      <div aria-label={copy(locale, `${dimensionName} time grain`, `${dimensionName}时间粒度`)} className="time-grain-switch" role="group">
        {grains.map((item) => <button aria-pressed={grain === item.id} disabled={!supportedGrains.includes(item.id)} key={item.id} onClick={() => changeGrain(item.id)} title={supportedGrains.includes(item.id) ? copy(locale, `${item.english} grain`, `${item.chinese}粒度`) : copy(locale, `${item.english} grain is unavailable for the current facts`, `${item.chinese}粒度不适用于当前事实`)} type="button">{copy(locale, item.english, item.chinese)}</button>)}
      </div>
      <label>{copy(locale, "Start", "起始")}<input aria-label={copy(locale, `${dimensionName} start date`, `${dimensionName}起始日期`)} max={endDate || undefined} onChange={(event) => setRange((current) => ({ ...current, startDate: event.target.value }))} type="date" value={startDate} /></label>
      <label>{copy(locale, "End", "结束")}<input aria-label={copy(locale, `${dimensionName} end date`, `${dimensionName}结束日期`)} min={startDate || undefined} onChange={(event) => setRange((current) => ({ ...current, endDate: event.target.value }))} type="date" value={endDate} /></label>
      <span aria-live="polite" className="time-series-status">{stateLabel}</span>
    </div>
  );
}

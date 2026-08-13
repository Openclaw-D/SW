import { useState } from "react";
import type { KeyboardEvent } from "react";
import type { DimensionSeriesGroup, DimensionSeriesMeasure, EvidenceReference, ReviewEvidenceTarget, TimeGrain } from "../contracts/workbench";
import { sameReviewEvidenceTarget } from "../lib/workbenchLogic";
import { copy, formatCanonicalLabel, formatEvidenceLocator, formatUnit, usePublicLocale } from "../lib/publicLocale";
import { Icon } from "./icons";

interface PayrollRow {
  id: string;
  label: string;
  amount: DimensionSeriesMeasure;
  staff: DimensionSeriesMeasure;
  perCapita: DimensionSeriesMeasure;
}

const grainPresentation: Record<TimeGrain, { label: string; perCapitaUnit: string; minimumSlotWidth: number }> = {
  day: { label: "日", perCapitaUnit: "万元/人/日", minimumSlotWidth: 30 },
  week: { label: "周", perCapitaUnit: "万元/人/周", minimumSlotWidth: 48 },
  month: { label: "月", perCapitaUnit: "万元/人/月", minimumSlotWidth: 70 },
  year: { label: "年", perCapitaUnit: "万元/人/年", minimumSlotWidth: 110 },
};

function uniqueEvidenceRefs(...groups: string[][]) {
  return [...new Set(groups.flat().filter(Boolean))];
}

export function payrollEvidenceUnion(primaryEvidenceRefs: string[], secondaryEvidenceRefs: string[]) {
  return uniqueEvidenceRefs(primaryEvidenceRefs, secondaryEvidenceRefs);
}

export function payrollPlotGeometry(pointCount: number, grain: TimeGrain) {
  const plotMargins = { left: 64, right: 64 };
  const minimumInnerWidth = 592;
  const innerPlotWidth = Math.max(minimumInnerWidth, pointCount * grainPresentation[grain].minimumSlotWidth);
  const plotCanvasWidth = innerPlotWidth + plotMargins.left + plotMargins.right;
  const slotWidth = innerPlotWidth / Math.max(pointCount, 1);
  const centers = Array.from({ length: pointCount }, (_, index) => plotMargins.left + (index + .5) * slotWidth);
  const barWidth = Math.max(8, Math.min(30, slotWidth * .55));
  const minimumLabelSpacing = 82;
  const labelEvery = Math.max(1, Math.ceil(minimumLabelSpacing / slotWidth));
  return { plotMargins, innerPlotWidth, plotCanvasWidth, slotWidth, centers, barWidth, minimumLabelSpacing, labelEvery };
}

function periodEvidenceRefs(row: PayrollRow, primary: DimensionSeriesMeasure = row.amount) {
  const secondary = primary.id === row.amount.id ? row.staff : row.amount;
  return payrollEvidenceUnion(primary.evidenceRefs, secondary.evidenceRefs);
}

function evidenceLocation(reference: EvidenceReference | undefined, locale: ReturnType<typeof usePublicLocale>) {
  if (!reference) return copy(locale, "Evidence not linked", "证据未关联");
  return formatEvidenceLocator(reference.locator, reference.locationStatus, locale);
}

function activateWithKeyboard(event: KeyboardEvent<SVGGElement>, action: () => void) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  action();
}

function payrollRows(series: DimensionSeriesGroup | undefined) {
  if (!series || series.id !== "production-payroll") return [];
  return series.points.flatMap((point): PayrollRow[] => {
    const amount = point.measures.find((measure) => measure.label === "工资总额");
    const staff = point.measures.find((measure) => measure.label === "在岗人数");
    const perCapita = point.measures.find((measure) => measure.label === "人均工资");
    if (!amount || !staff || !perCapita || !Number.isFinite(amount.value) || !Number.isFinite(staff.value) || staff.value <= 0) return [];
    return [{ id: point.id, label: point.label, amount, staff, perCapita }];
  });
}

function isPeriodSelected(row: PayrollRow, selectedTarget: ReviewEvidenceTarget | null) {
  if (!selectedTarget || selectedTarget.dimensionId !== "production") return false;
  if (![row.amount.id, row.staff.id, row.perCapita.id].includes(selectedTarget.reviewTargetId ?? "")) return false;
  const selectedEvidenceRefs = selectedTarget.evidenceRefs?.length ? selectedTarget.evidenceRefs : [selectedTarget.evidenceRef];
  return periodEvidenceRefs(row).some((evidenceRef) => selectedEvidenceRefs.includes(evidenceRef));
}

export function ProductionPayrollChart({ series, grain, evidence, selectedTarget, onEvidenceSelect }: {
  series?: DimensionSeriesGroup;
  grain: TimeGrain;
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const [focusedPeriodId, setFocusedPeriodId] = useState<string | null>(null);
  const rows = payrollRows(series);
  const presentation = grainPresentation[grain];
  const periodLabel = copy(locale, ({ day: "day", week: "week", month: "month", year: "year" } as const)[grain], presentation.label);
  const perCapitaUnit = copy(locale, ({ day: "CNY 10k/person/day", week: "CNY 10k/person/week", month: "CNY 10k/person/month", year: "CNY 10k/person/year" } as const)[grain], presentation.perCapitaUnit);
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const targetFor = (evidenceRefs: string[], reviewTargetId: string): ReviewEvidenceTarget | null => evidenceRefs[0] ? ({ evidenceRef: evidenceRefs[0], evidenceRefs, dimensionId: "production", reviewTargetId, factVersionId: null }) : null;
  const totalPayroll = rows.reduce((sum, row) => sum + row.amount.value, 0);
  const latest = rows.at(-1);
  const latestPerCapita = latest ? latest.amount.value / latest.staff.value : 0;
  const temporal = rows.some((row) => row.id.startsWith("timeseries-"));
  const summaries = latest ? [
    { id: "production-payroll-three-month-total", label: temporal ? "所选时段工资" : "三月工资", value: `${totalPayroll.toFixed(1)} ${copy(locale, "CNY 10k", "万元")}`, evidenceRefs: temporal ? uniqueEvidenceRefs(...rows.map((row) => row.amount.evidenceRefs)) : ["evidence-production-payroll-three-month-total"] },
    { id: "production-payroll-latest-staff", label: "期末在岗", value: `${latest.staff.value.toLocaleString()} ${copy(locale, "people", "人")}`, evidenceRefs: temporal ? latest.staff.evidenceRefs : ["evidence-production-payroll-latest-staff"] },
    { id: "production-payroll-latest-per-capita", label: "期末人均", value: `${latestPerCapita.toFixed(2)} ${perCapitaUnit}`, evidenceRefs: temporal ? periodEvidenceRefs(latest) : ["evidence-production-payroll-latest-per-capita-inputs"] },
  ] : [];
  const amountMax = rows.length ? Math.max(5, Math.ceil(Math.max(...rows.map((row) => row.amount.value)) / 5) * 5) : 5;
  const staffMax = rows.length ? Math.max(10, Math.ceil(Math.max(...rows.map((row) => row.staff.value)) / 10) * 10) : 10;
  const { plotMargins, innerPlotWidth, plotCanvasWidth, slotWidth, centers, barWidth, labelEvery } = payrollPlotGeometry(rows.length, grain);
  const plot = { left: plotMargins.left, right: plotMargins.left + innerPlotWidth, top: 72, bottom: 180 };
  const showsLabel = (index: number) => index % labelEvery === 0 || index === rows.length - 1;
  const staffPoints = rows.map((row, index) => ({ x: centers[index], y: plot.bottom - row.staff.value / staffMax * (plot.bottom - plot.top) }));
  const periodFocusClass = (rowId: string) => focusedPeriodId === rowId ? "is-period-focused" : focusedPeriodId ? "is-period-muted" : "";
  const periodFocusHandlers = (rowId: string) => ({
    onBlur: () => setFocusedPeriodId((current) => current === rowId ? null : current),
    onFocus: () => setFocusedPeriodId(rowId),
    onPointerEnter: () => setFocusedPeriodId(rowId),
    onPointerLeave: () => setFocusedPeriodId((current) => current === rowId ? null : current),
  });
  return (
    <section aria-label={copy(locale, "Payroll chart", "人员工资图")} className="production-payroll-panel" data-semantic-localized data-time-grain={grain}>
      <header><div><Icon name="production" /><span><strong>{copy(locale, "Payroll", "人员工资")}</strong><small>{copy(locale, `Total payroll and end-of-period staff use separate axes; per-capita payroll is derived from the two inputs for the same ${periodLabel}.`, `工资总额与期末在岗人数分轴展示；人均工资由同一${presentation.label}期两项输入派生`)}</small></span></div><span>{temporal ? copy(locale, `${rows.length} ${periodLabel} periods`, `${rows.length} 个${presentation.label}时段`) : copy(locale, "Past three months", "近三个月")}</span></header>
      {rows.length ? <>
        <div aria-label={copy(locale, "Key payroll totals", "人员工资关键汇总")} className="production-payroll-summary">
          {summaries.map((summary) => {
            const target = targetFor(summary.evidenceRefs, summary.id);
            const reference = evidenceById.get(summary.evidenceRefs[0]);
            const selected = sameReviewEvidenceTarget(target, selectedTarget);
            return <button aria-label={`${formatCanonicalLabel(summary.label, locale)} ${summary.value} · ${evidenceLocation(reference, locale)}`} aria-pressed={selected} className={selected ? "is-selected" : ""} data-target-id={summary.id} key={summary.id} onClick={() => target && onEvidenceSelect(target)} type="button"><span>{formatCanonicalLabel(summary.label, locale)}</span><strong>{summary.value}</strong></button>;
          })}
        </div>
        <div className="production-payroll-legend" aria-label={copy(locale, "Chart legend", "图表图例")}><span><i className="is-payroll" />{copy(locale, "Total payroll (CNY 10k, left-axis bars)", "工资总额（万元，左轴柱）")}</span><span><i className="is-staff" />{copy(locale, "End-of-period staff (people, right-axis line)", "期末在岗（人，右轴折线）")}</span><span>{copy(locale, "Per-capita unit", "人均单位")}：{perCapitaUnit}</span></div>
        <div className="production-payroll-chart-scroll" data-minimum-plot-width={plotCanvasWidth}>
          <svg aria-label={copy(locale, `Total-payroll bars and end-of-period-staff line at ${periodLabel} grain`, `${presentation.label}粒度工资总额柱形与期末在岗人数折线图`)} className="production-payroll-svg" role="img" style={{ minWidth: `${plotCanvasWidth}px`, width: `max(100%, ${plotCanvasWidth}px)` }} viewBox={`0 0 ${plotCanvasWidth} 220`}>
            <text className="production-payroll-axis-unit" x={plot.left} y="18">{copy(locale, "Left axis · CNY 10k", "左轴 · 万元")}</text>
            <text className="production-payroll-axis-unit is-right" textAnchor="end" x={plot.right} y="18">{copy(locale, "Right axis · people", "右轴 · 人")}</text>
            {[0, .5, 1].map((ratio) => {
              const y = plot.bottom - ratio * (plot.bottom - plot.top);
              return <g aria-hidden="true" key={ratio}><line className="production-payroll-grid-line" x1={plot.left} x2={plot.right} y1={y} y2={y} /><text className="production-payroll-axis-label" textAnchor="end" x={plot.left - 9} y={y + 4}>{(amountMax * ratio).toFixed(ratio === 0 ? 0 : 1)}</text><text className="production-payroll-axis-label is-right" x={plot.right + 9} y={y + 4}>{Math.round(staffMax * ratio)}</text></g>;
            })}
            <line aria-hidden="true" className="production-payroll-label-divider" x1={plot.left} x2={plot.right} y1="56" y2="56" />
            {rows.map((row, index) => {
              const center = centers[index];
              const y = plot.bottom - row.amount.value / amountMax * (plot.bottom - plot.top);
              const evidenceRefs = periodEvidenceRefs(row, row.amount);
              const reference = evidenceById.get(row.amount.evidenceRefs[0]);
              const target = targetFor(evidenceRefs, row.amount.id);
              const selected = isPeriodSelected(row, selectedTarget);
              const action = () => { if (target) onEvidenceSelect(target); };
              return <g {...periodFocusHandlers(row.id)} aria-label={copy(locale, `${formatCanonicalLabel(row.label, locale)} total payroll ${row.amount.value.toFixed(1)} CNY 10k; same-period per-capita ${row.perCapita.value.toFixed(2)} ${perCapitaUnit} · ${evidenceLocation(reference, locale)}`, `${row.label}工资总额${row.amount.value.toFixed(1)}万元，同期人均${row.perCapita.value.toFixed(2)}${presentation.perCapitaUnit}，${evidenceLocation(reference, locale)}`)} aria-pressed={selected} className={`production-payroll-chart-item production-payroll-bar ${periodFocusClass(row.id)} ${selected ? "is-selected" : ""}`} data-period-id={row.id} data-target-id={row.amount.id} key={row.amount.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{copy(locale, `${formatCanonicalLabel(row.label, locale)} total payroll · ${row.amount.value.toFixed(1)} CNY 10k · same-period staff ${row.staff.value.toLocaleString()} people · ${evidenceLocation(reference, locale)}`, `${row.label}工资总额 · ${row.amount.value.toFixed(1)}万元 · 同期在岗 ${row.staff.value.toLocaleString()}人 · ${evidenceLocation(reference, locale)}`)}</title>{showsLabel(index) ? <><line aria-hidden="true" className="production-payroll-label-guide" x1={center} x2={center} y1="30" y2={Math.max(62, y - 7)} /><text className="production-payroll-value-label is-payroll" textAnchor="middle" x={center} y="25">{row.amount.value.toFixed(1)}</text></> : null}<rect height={plot.bottom - y} rx="3" width={barWidth} x={center - barWidth / 2} y={y} /></g>;
            })}
            <polyline aria-hidden="true" className="production-payroll-staff-line" points={staffPoints.map((point) => `${point.x},${point.y}`).join(" ")} />
            {rows.map((row, index) => {
              const point = staffPoints[index];
              const evidenceRefs = periodEvidenceRefs(row, row.staff);
              const reference = evidenceById.get(row.staff.evidenceRefs[0]);
              const target = targetFor(evidenceRefs, row.staff.id);
              const selected = isPeriodSelected(row, selectedTarget);
              const action = () => { if (target) onEvidenceSelect(target); };
              return <g {...periodFocusHandlers(row.id)} aria-label={copy(locale, `${formatCanonicalLabel(row.label, locale)} end-of-period staff ${row.staff.value.toLocaleString()} people; same-period per-capita ${row.perCapita.value.toFixed(2)} ${perCapitaUnit} · ${evidenceLocation(reference, locale)}`, `${row.label}期末在岗${row.staff.value.toLocaleString()}人，同期人均${row.perCapita.value.toFixed(2)}${presentation.perCapitaUnit}，${evidenceLocation(reference, locale)}`)} aria-pressed={selected} className={`production-payroll-chart-item production-payroll-staff-point ${periodFocusClass(row.id)} ${selected ? "is-selected" : ""}`} data-period-id={row.id} data-target-id={row.staff.id} key={row.staff.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{copy(locale, `${formatCanonicalLabel(row.label, locale)} end-of-period staff · ${row.staff.value.toLocaleString()} people · same-period payroll ${row.amount.value.toFixed(1)} CNY 10k · ${evidenceLocation(reference, locale)}`, `${row.label}期末在岗 · ${row.staff.value.toLocaleString()}人 · 同期工资 ${row.amount.value.toFixed(1)}万元 · ${evidenceLocation(reference, locale)}`)}</title>{showsLabel(index) ? <><line aria-hidden="true" className="production-payroll-label-guide is-staff" x1={point.x} x2={point.x} y1="50" y2={Math.max(62, point.y - 7)} /><text className="production-payroll-value-label is-staff" textAnchor="middle" x={point.x} y="47">{row.staff.value}{copy(locale, " ppl", "人")}</text></> : null}<circle cx={point.x} cy={point.y} r={rows.length > 24 ? 3 : 5} /></g>;
            })}
            {rows.map((row, index) => showsLabel(index) ? <text aria-hidden="true" className="production-payroll-period-label" key={row.id} textAnchor="middle" x={centers[index]} y="211">{formatCanonicalLabel(row.label, locale)}</text> : null)}
          </svg>
        </div>
      </> : <div className="production-payroll-empty"><strong>{copy(locale, "Payroll unavailable", "人员工资不可用")}</strong><span>{copy(locale, "Verifiable total-payroll and staff-count data is missing.", "缺少可核验的工资总额与在岗人数数据。")}</span></div>}
    </section>
  );
}

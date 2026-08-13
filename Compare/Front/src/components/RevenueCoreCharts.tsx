import type { CSSProperties, KeyboardEvent } from "react";
import type {
  AssessmentTone,
  DimensionComposition,
  DimensionDetail,
  DimensionMetric,
  DimensionSeriesMeasure,
  EvidenceReference,
  ReviewEvidenceTarget,
} from "../contracts/workbench";
import { copy, formatCanonicalLabel, formatEvidenceLocator, formatUnit, readPublicLocale, usePublicLocale, type PublicLocale } from "../lib/publicLocale";

type EvidenceSelect = (evidenceId: string, targetId: string) => void;
type EvidenceGroupSelect = (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void;

interface RevenueRow {
  id: string;
  label: string;
  income: DimensionSeriesMeasure;
  growth: number | null;
  growthTargetId: string | null;
  growthEvidenceRefs: string[];
}

interface InvoiceRow {
  id: string;
  label: string;
  invoiced: DimensionSeriesMeasure;
  collected: DimensionSeriesMeasure;
  rate: number;
  rateTargetId: string;
  rateEvidenceRefs: string[];
}

function cssVars(values: Record<string, string | number>) {
  return values as CSSProperties;
}

function rounded(value: number, digits = 1) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function niceMaximum(value: number) {
  const safe = Math.max(value, 1);
  const magnitude = 10 ** Math.floor(Math.log10(safe));
  const step = magnitude >= 1000 ? magnitude / 5 : magnitude / 4;
  return Math.ceil(safe / step) * step;
}

function evidenceText(reference: EvidenceReference | undefined, locale: PublicLocale = readPublicLocale()) {
  if (!reference) return copy(locale, "No evidence reference", "无证据引用");
  return formatEvidenceLocator(reference.locator, reference.locationStatus, locale);
}

function isSelected(evidenceRefs: string[], targetId: string, selectedTarget: ReviewEvidenceTarget | null) {
  return selectedTarget?.reviewTargetId === targetId && evidenceRefs.includes(selectedTarget.evidenceRef);
}

function activateWithKeyboard(event: KeyboardEvent<SVGGElement>, action: () => void) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  action();
}

function toneColor(tone: AssessmentTone) {
  if (tone === "positive") return "#30343b";
  if (tone === "attention") return "#7b828c";
  if (tone === "critical") return "#111111";
  return "#59606a";
}

function metricNumber(metric: DimensionMetric | undefined) {
  if (!metric) return null;
  const parsed = Number(metric.value.replace(/[,，]/g, "").match(/-?\d+(?:\.\d+)?/)?.[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function RevenueChart({ rows, evidenceById, selectedTarget, onEvidenceSelect }: { rows: RevenueRow[]; evidenceById: Map<string, EvidenceReference>; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  const locale = usePublicLocale();
  if (!rows.length) return <div className="revenue-chart-empty"><strong>{copy(locale, "Revenue trend unavailable", "营收趋势不可用")}</strong><span>{copy(locale, "A verifiable recognized-revenue series is missing.", "缺少可核验的确认收入序列。")}</span></div>;
  const maximum = niceMaximum(Math.max(...rows.map((row) => row.income.value)));
  const labelBand = { top: 28, height: 46, divider: 51, incomeY: 43, growthY: 68 };
  const plot = { left: 56, right: 468, top: 84, bottom: 202 };
  const pointSpacing = rows.length === 1 ? plot.right - plot.left : (plot.right - plot.left - 84) / (rows.length - 1);
  const centers = rows.map((_, index) => rows.length === 1 ? 262 : plot.left + 42 + index * pointSpacing);
  const barWidth = Math.max(1, Math.min(54, pointSpacing * .66));
  const pointRadius = Math.max(.65, Math.min(5, pointSpacing * .28));
  const growthValues = rows.flatMap((row) => row.growth === null ? [] : [row.growth]);
  const growthMinimum = Math.min(-10, ...growthValues);
  const growthMaximum = Math.max(25, ...growthValues);
  const growthBaselineRatio = .72;
  const growthBaselineY = plot.top + (plot.bottom - plot.top) * growthBaselineRatio;
  const positivePlotHeight = growthBaselineY - plot.top;
  const negativePlotHeight = plot.bottom - growthBaselineY;
  const amountY = (value: number) => plot.bottom - value / maximum * (plot.bottom - plot.top);
  const growthY = (value: number) => value >= 0
    ? growthBaselineY - value / growthMaximum * positivePlotHeight
    : growthBaselineY + Math.abs(value) / Math.abs(growthMinimum) * negativePlotHeight;
  const referenceLabelY = growthBaselineY - 17;
  const labelStep = Math.max(1, Math.ceil(rows.length / 6));
  const showLabel = (index: number) => index % labelStep === 0 || index === rows.length - 1;
  const growthPoints = rows.flatMap((row, index) => row.growth === null ? [] : [{ row, index, x: centers[index], y: growthY(row.growth) }]);
  const amountTicks = [0, maximum / 2, maximum];
  return (
    <svg aria-label={copy(locale, "Revenue trend: recognized-revenue bars use the left CNY-10k axis; growth uses the right percentage axis with an explicit 0% baseline and separate label bands.", "营收趋势：确认收入柱形使用左轴万元，环比折线使用右轴百分比，并标示0%增长基线；数值与环比使用独立标签带")} className="revenue-core-svg revenue-combo-chart" role="img" viewBox="0 0 520 248">
      {amountTicks.map((tick) => { const y = amountY(tick); return <g aria-hidden="true" key={tick}><line className="revenue-grid-line" x1={plot.left} x2={plot.right} y1={y} y2={y} /><text className="revenue-axis-label" textAnchor="end" x={plot.left - 8} y={y + 4}>{Math.round(tick).toLocaleString()}</text></g>; })}
      <text className="revenue-axis-unit" textAnchor="start" x={plot.left} y="18">{copy(locale, "Left axis · CNY 10k", "左轴 · 万元")}</text>
      <text className="revenue-axis-unit" textAnchor="end" x={plot.right} y="18">{copy(locale, "Right axis · growth %", "右轴 · 环比 %")}</text>
      <rect aria-hidden="true" className="revenue-label-band" height={labelBand.height} rx="4" width={plot.right - plot.left} x={plot.left} y={labelBand.top} />
      <line aria-hidden="true" className="revenue-label-band-divider" x1={plot.left} x2={plot.right} y1={labelBand.divider} y2={labelBand.divider} />
      <line aria-hidden="true" className="revenue-growth-baseline" data-baseline-ratio={growthBaselineRatio} x1={plot.left} x2={plot.right} y1={growthBaselineY} y2={growthBaselineY} />
      <text className="revenue-axis-label" textAnchor="start" x={plot.right + 8} y={growthY(growthMaximum) + 4}>{rounded(growthMaximum)}%</text>
      <text className="revenue-axis-label" textAnchor="start" x={plot.right + 8} y={growthY(growthMinimum) + 4}>{rounded(growthMinimum)}%</text>
      {rows.map((row, index) => {
        const evidenceId = row.income.evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const y = amountY(row.income.value);
        const selected = isSelected(row.income.evidenceRefs, row.income.id, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, row.income.id);
        return (
          <g aria-label={`${formatCanonicalLabel(row.label, locale)} ${copy(locale, "recognized income", "确认收入")} ${row.income.value.toLocaleString()} ${formatUnit(row.income.unit, locale)} · ${evidenceText(reference, locale)}`} aria-pressed={selected} className={`revenue-chart-item revenue-income-bar state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="revenue-bar" data-target-id={row.income.id} key={row.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}>
            <title>{formatCanonicalLabel(row.label, locale)} · {copy(locale, "recognized income", "确认收入")} · {row.income.value.toLocaleString()} {formatUnit(row.income.unit, locale)} · {evidenceText(reference, locale)}</title>
            <rect height={plot.bottom - y} rx={Math.min(3, barWidth / 2)} width={barWidth} x={centers[index] - barWidth / 2} y={y} />
            {showLabel(index) ? <text className="revenue-value-label" textAnchor="middle" x={centers[index]} y={labelBand.incomeY}>{row.income.value.toLocaleString()}</text> : null}
            {showLabel(index) ? <text className="revenue-period-label" textAnchor="middle" x={centers[index]} y="238">{formatCanonicalLabel(row.label, locale)}</text> : null}
          </g>
        );
      })}
      {growthPoints.length > 1 ? <polyline aria-hidden="true" className="revenue-growth-line" points={growthPoints.map((point) => `${point.x},${point.y}`).join(" ")} /> : null}
      {growthPoints.map(({ row, index, x, y }) => {
        const targetId = row.growthTargetId!;
        const evidenceId = row.growthEvidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(row.growthEvidenceRefs, targetId, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, targetId);
        return <g aria-label={copy(locale, `${formatCanonicalLabel(row.label, locale)} recognized-income period growth ${row.growth! >= 0 ? "+" : ""}${row.growth}%, deterministically derived from adjacent recognized-income values · ${evidenceText(reference, locale)}`, `${row.label}确认收入环比${row.growth! >= 0 ? "+" : ""}${row.growth}%，由相邻确认收入确定性派生，${evidenceText(reference, locale)}`)} aria-pressed={selected} className={`revenue-chart-item revenue-growth-point state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="revenue-line-point" data-target-id={targetId} key={targetId} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{formatCanonicalLabel(row.label, locale)} · {copy(locale, "period growth", "环比")} · {row.growth! >= 0 ? "+" : ""}{row.growth}% · {evidenceText(reference, locale)}</title><circle cx={x} cy={y} r={pointRadius} />{showLabel(index) ? <text className="revenue-rate-label" textAnchor="middle" x={x} y={labelBand.growthY}>{row.growth! >= 0 ? "+" : ""}{row.growth}%</text> : null}</g>;
      })}
      <g aria-hidden="true" className="revenue-reference-overlay">
        <rect className="revenue-reference-label-bg" height="18" rx="4" width="94" x={plot.left + 4} y={referenceLabelY} />
        <text className="revenue-reference-label" textAnchor="start" x={plot.left + 9} y={referenceLabelY + 13}>{copy(locale, "0% growth baseline", "0% 增长基线")}</text>
      </g>
    </svg>
  );
}

function InvoiceChart({ rows, evidenceById, selectedTarget, onEvidenceSelect }: { rows: InvoiceRow[]; evidenceById: Map<string, EvidenceReference>; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  const locale = usePublicLocale();
  if (!rows.length) return <div className="revenue-chart-empty"><strong>{copy(locale, "Invoice-to-collection cross-check unavailable", "票款互证不可用")}</strong><span>{copy(locale, "Invoices or collections for matching periods are missing.", "缺少同期发票或回款流水。")}</span></div>;
  const maximum = niceMaximum(Math.max(...rows.flatMap((row) => [row.invoiced.value, row.collected.value])));
  const plot = { left: 56, right: 468, top: 36, bottom: 190 };
  const pointSpacing = rows.length === 1 ? plot.right - plot.left : (plot.right - plot.left - 84) / (rows.length - 1);
  const centers = rows.map((_, index) => rows.length === 1 ? 262 : plot.left + 42 + index * pointSpacing);
  const clusterWidth = Math.max(1.2, Math.min(60, pointSpacing * .72));
  const clusterGap = Math.max(.2, Math.min(4, clusterWidth * .08));
  const barWidth = Math.max(.5, (clusterWidth - clusterGap) / 2);
  const pointRadius = Math.max(.65, Math.min(5, pointSpacing * .28));
  const amountY = (value: number) => plot.bottom - value / maximum * (plot.bottom - plot.top);
  const rateMinimum = Math.min(70, ...rows.map((row) => row.rate));
  const rateMaximum = Math.max(100, ...rows.map((row) => row.rate));
  const rateY = (value: number) => plot.bottom - (value - rateMinimum) / Math.max(rateMaximum - rateMinimum, 1) * (plot.bottom - plot.top);
  const referenceLabelY = Math.max(plot.top + 2, Math.min(plot.bottom - 20, rateY(90) - 17));
  const labelStep = Math.max(1, Math.ceil(rows.length / 6));
  const showLabel = (index: number) => index % labelStep === 0 || index === rows.length - 1;
  const ratePoints = rows.map((row, index) => ({ row, index, x: centers[index], y: rateY(row.rate) }));
  return (
    <svg aria-label={copy(locale, "Invoice-to-collection cross-check: grouped invoice and collection bars use the left CNY-10k axis; collection rate uses the right percentage axis and is derived from same-period data.", "票款互证：发票与回款分组柱形使用左轴万元，回款率折线使用右轴百分比并由同期数据派生")} className="revenue-core-svg revenue-invoice-chart" role="img" viewBox="0 0 520 230">
      {[0, maximum / 2, maximum].map((tick) => { const y = amountY(tick); return <g aria-hidden="true" key={tick}><line className="revenue-grid-line" x1={plot.left} x2={plot.right} y1={y} y2={y} /><text className="revenue-axis-label" textAnchor="end" x={plot.left - 8} y={y + 4}>{Math.round(tick).toLocaleString()}</text></g>; })}
      <text className="revenue-axis-unit" x={plot.left} y="18">{copy(locale, "Left axis · CNY 10k", "左轴 · 万元")}</text>
      <text className="revenue-axis-unit" textAnchor="end" x={plot.right} y="18">{copy(locale, "Right axis · collection rate %", "右轴 · 回款率 %")}</text>
      <line aria-hidden="true" className="revenue-rate-reference" x1={plot.left} x2={plot.right} y1={rateY(90)} y2={rateY(90)} />
      <text className="revenue-axis-label" x={plot.right + 8} y={rateY(rateMaximum) + 4}>{rounded(rateMaximum)}%</text>
      <text className="revenue-axis-label" x={plot.right + 8} y={rateY(rateMinimum) + 4}>{rounded(rateMinimum)}%</text>
      {rows.flatMap((row, index) => [row.invoiced, row.collected].map((measure, measureIndex) => {
        const evidenceId = measure.evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(measure.evidenceRefs, measure.id, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, measure.id);
        const y = amountY(measure.value);
        const x = centers[index] + (measureIndex === 0 ? -clusterWidth / 2 : clusterGap / 2);
        return <g aria-label={`${formatCanonicalLabel(row.label, locale)} ${formatCanonicalLabel(measure.label, locale)} ${measure.value.toLocaleString()} ${formatUnit(measure.unit, locale)} · ${evidenceText(reference, locale)}`} aria-pressed={selected} className={`revenue-chart-item revenue-invoice-bar is-${measureIndex === 0 ? "invoiced" : "collected"} state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="invoice-bar" data-target-id={measure.id} key={measure.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{formatCanonicalLabel(row.label, locale)} · {formatCanonicalLabel(measure.label, locale)} · {measure.value.toLocaleString()} {formatUnit(measure.unit, locale)}</title><rect height={plot.bottom - y} rx={Math.min(2, barWidth / 2)} width={barWidth} x={x} y={y} /></g>;
      }))}
      <polyline aria-hidden="true" className="revenue-rate-line" points={ratePoints.map((point) => `${point.x},${point.y}`).join(" ")} />
      {ratePoints.map(({ row, index, x, y }) => {
        const targetId = row.rateTargetId;
        const evidenceRefs = row.rateEvidenceRefs;
        const evidenceId = evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(evidenceRefs, targetId, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, targetId);
        return <g aria-label={copy(locale, `${formatCanonicalLabel(row.label, locale)} collection rate ${row.rate}%, deterministically derived as same-period collections divided by invoices · ${evidenceText(reference, locale)}`, `${row.label}回款率${row.rate}%，由同期回款流水除以发票确定性派生，${evidenceText(reference, locale)}`)} aria-pressed={selected} className={`revenue-chart-item revenue-rate-point state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="invoice-line-point" data-target-id={targetId} key={targetId} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{formatCanonicalLabel(row.label, locale)} · {copy(locale, "collection rate", "回款率")} · {row.rate}% · {evidenceText(reference, locale)}</title><circle cx={x} cy={y} r={pointRadius} />{showLabel(index) ? <><text className="revenue-rate-label" textAnchor="middle" x={x} y={Math.max(plot.top + 10, y - 10)}>{row.rate}%</text><text className="revenue-period-label" textAnchor="middle" x={x} y="215">{formatCanonicalLabel(row.label, locale)}</text></> : null}</g>;
      })}
      <g aria-hidden="true" className="revenue-reference-overlay">
        <rect className="revenue-reference-label-bg" height="18" rx="4" width="88" x={plot.left + 4} y={referenceLabelY} />
        <text className="revenue-reference-label" textAnchor="start" x={plot.left + 9} y={referenceLabelY + 13}>{copy(locale, "90% reference line", "90% 参考线")}</text>
      </g>
    </svg>
  );
}

function polarPoint(cx: number, cy: number, radius: number, angle: number) {
  const radians = (angle - 90) * Math.PI / 180;
  return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
}

function pieSlicePath(cx: number, cy: number, radius: number, start: number, end: number, innerRadius = 0) {
  const outerStart = polarPoint(cx, cy, radius, start);
  const outerEnd = polarPoint(cx, cy, radius, end);
  const largeArc = end - start > 180 ? 1 : 0;
  if (!innerRadius) return `M ${cx} ${cy} L ${outerStart.x} ${outerStart.y} A ${radius} ${radius} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y} Z`;
  const innerEnd = polarPoint(cx, cy, innerRadius, end);
  const innerStart = polarPoint(cx, cy, innerRadius, start);
  return `M ${outerStart.x} ${outerStart.y} A ${radius} ${radius} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y} L ${innerEnd.x} ${innerEnd.y} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${innerStart.x} ${innerStart.y} Z`;
}

function slices(composition: DimensionComposition) {
  const positive = composition.segments.filter((segment) => segment.value > 0);
  const total = positive.reduce((sum, segment) => sum + segment.value, 0);
  let start = 0;
  return positive.map((segment) => {
    const end = start + segment.value / Math.max(total, 1) * 360;
    const result = { segment, start, end, percentage: segment.value / Math.max(total, 1) * 100 };
    start = end;
    return result;
  });
}

function CompositionDonuts({ upstream, downstream, evidenceById, selectedTarget, onEvidenceSelect }: { upstream: DimensionComposition | undefined; downstream: DimensionComposition | undefined; evidenceById: Map<string, EvidenceReference>; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  const locale = usePublicLocale();
  if (!upstream?.segments.length && !downstream?.segments.length) return <div className="revenue-chart-empty"><strong>{copy(locale, "Upstream/downstream composition unavailable", "上下游构成不可用")}</strong><span>{copy(locale, "A verifiable upstream/downstream composition is missing.", "缺少可核验的上下游构成。")}</span></div>;
  const charts = [{ composition: upstream, cx: 145 }, { composition: downstream, cx: 455 }];
  return (
    <svg aria-label={copy(locale, "Upstream/downstream composition: adjacent sectors label category and share directly.", "上下游构成：上游与下游并列扇区直接显示类别和占比")} className="revenue-core-svg revenue-composition-chart" role="img" viewBox="0 0 600 240">
      {charts.map(({ composition, cx }) => composition ? <g key={composition.id}>
        <text className="revenue-pie-title" textAnchor="middle" x={cx} y="22">{formatCanonicalLabel(composition.label, locale)}</text>
        {slices(composition).map(({ segment, start, end, percentage }) => {
          const evidenceId = segment.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          const selected = isSelected(segment.evidenceRefs, segment.id, selectedTarget);
          const action = () => evidenceId && onEvidenceSelect(evidenceId, segment.id);
          const label = polarPoint(cx, 132, 53, start + (end - start) / 2);
          return <g aria-label={`${formatCanonicalLabel(composition.label, locale)} ${formatCanonicalLabel(segment.label, locale)} ${rounded(percentage)}% · ${segment.value} ${formatUnit(segment.unit, locale)} · ${evidenceText(reference, locale)}`} aria-pressed={selected} className={`revenue-chart-item revenue-composition-segment tone-${segment.tone} state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="composition-segment" data-target-id={segment.id} key={segment.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" style={cssVars({ "--revenue-segment-color": toneColor(segment.tone) })} tabIndex={0}><title>{formatCanonicalLabel(composition.label, locale)} {formatCanonicalLabel(segment.label, locale)} · {rounded(percentage)}% · {evidenceText(reference, locale)}</title><path d={pieSlicePath(cx, 132, 94, start, end)} /><text className="revenue-segment-label" textAnchor="middle" x={label.x} y={label.y - 4}><tspan x={label.x}>{formatCanonicalLabel(segment.label, locale)}</tspan><tspan className="revenue-segment-value" dy="17" x={label.x}>{rounded(percentage)}%</tspan></text></g>;
        })}
      </g> : null)}
    </svg>
  );
}

function CollectionChart({ aging, collectionRate, evidenceById, selectedTarget, onEvidenceSelect }: { aging: DimensionComposition | undefined; collectionRate: number | null; evidenceById: Map<string, EvidenceReference>; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  const locale = usePublicLocale();
  if (!aging?.segments.length) return <div className="revenue-chart-empty"><strong>{copy(locale, "Collection aging unavailable", "回款账龄不可用")}</strong><span>{copy(locale, "A verifiable receivables-aging composition is missing.", "缺少可核验的应收账龄构成。")}</span></div>;
  return (
    <svg aria-label={collectionRate === null ? copy(locale, "Collection rate unavailable; receivables aging is shown.", "回款率不可用，并展示应收账龄构成") : copy(locale, `Cumulative collection rate ${collectionRate}%; receivables aging is shown.`, `累计回款率${collectionRate}%，并展示应收账龄构成`)} className="revenue-core-svg revenue-aging-chart" role="img" viewBox="0 0 520 240">
      {slices(aging).map(({ segment, start, end, percentage }) => {
        const evidenceId = segment.evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(segment.evidenceRefs, segment.id, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, segment.id);
        const label = polarPoint(260, 126, 73, start + (end - start) / 2);
        return <g aria-label={`${formatCanonicalLabel(segment.label, locale)} ${copy(locale, "receivables share", "应收占比")} ${rounded(percentage)}% · ${segment.value} ${formatUnit(segment.unit, locale)} · ${evidenceText(reference, locale)}`} aria-pressed={selected} className={`revenue-chart-item revenue-aging-segment tone-${segment.tone} state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="aging-segment" data-target-id={segment.id} key={segment.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" style={cssVars({ "--revenue-segment-color": toneColor(segment.tone) })} tabIndex={0}><title>{formatCanonicalLabel(segment.label, locale)} · {rounded(percentage)}% · {evidenceText(reference, locale)}</title><path d={pieSlicePath(260, 126, 102, start, end, 58)} /><text className="revenue-segment-label" textAnchor="middle" x={label.x} y={label.y - 4}><tspan x={label.x}>{formatCanonicalLabel(segment.label, locale)}</tspan><tspan className="revenue-segment-value" dy="17" x={label.x}>{rounded(percentage)}%</tspan></text></g>;
      })}
      <text className="revenue-collection-label" textAnchor="middle" x="260" y="120">{copy(locale, "Cumulative collection rate", "累计回款率")}</text>
      <text className="revenue-collection-value" textAnchor="middle" x="260" y="148">{collectionRate === null ? copy(locale, "Awaiting verification", "待核验") : `${collectionRate}%`}</text>
    </svg>
  );
}

const profitabilityColors = ["#111111", "#30343b", "#59606a", "#7b828c", "#a6abb2", "#d7d9dd"];
type CoverageRiskLevel = "forbid" | "risk" | "confirm" | "attention" | "support";
const coverageRiskLabels: Record<CoverageRiskLevel, string> = { forbid: "禁止", risk: "风险", confirm: "核实", attention: "关注", support: "支持" };

function coverageRiskLevel(value: number): CoverageRiskLevel {
  if (value >= 2) return "support";
  if (value >= 1.5) return "attention";
  if (value >= 1) return "confirm";
  if (value >= .75) return "risk";
  return "forbid";
}

function ProfitabilityPanel({ composition, metrics, evidenceById, rentEvidenceRefs, selectedTarget, onEvidenceSelect }: { composition: DimensionComposition | undefined; metrics: Map<string, DimensionMetric>; evidenceById: Map<string, EvidenceReference>; rentEvidenceRefs: string[]; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  const locale = usePublicLocale();
  const annualMetric = metrics.get("revenue-income-metric");
  const profitMetric = metrics.get("revenue-net-profit-metric");
  const marginMetric = metrics.get("revenue-net-margin-metric");
  const rentMetric = metrics.get("revenue-rent-first-12-metric");
  const coverageMetric = metrics.get("revenue-rent-coverage-metric");
  const annualRevenue = metricNumber(annualMetric);
  const netProfit = metricNumber(profitMetric);
  const netMargin = metricNumber(marginMetric);
  const firstTwelveRent = metricNumber(rentMetric);
  const coverage = metricNumber(coverageMetric);
  if (!composition?.segments.some((segment) => segment.value > 0) || [annualMetric, profitMetric, marginMetric, rentMetric, coverageMetric].some((metric) => !metric)) {
    return <div className="revenue-chart-empty revenue-profit-empty"><strong>{copy(locale, "Profit and rent coverage unavailable", "利润与租金覆盖不可用")}</strong><span>{copy(locale, "Required inputs are missing.", "缺少必要输入。")}</span></div>;
  }
  const compositionTotal = composition.segments.reduce((sum, segment) => sum + segment.value, 0);
  const profitSegment = composition.segments.find((segment) => segment.id === "revenue-profit-net-profit");
  const invalid = annualRevenue === null || netProfit === null || netMargin === null || firstTwelveRent === null || coverage === null || firstTwelveRent <= 0 || Math.abs(compositionTotal - annualRevenue) > 0.01 || Math.abs((profitSegment?.value ?? NaN) - netProfit) > 0.01 || Math.abs(rounded(netProfit / annualRevenue * 100) - netMargin) > 0.05 || Math.abs(rounded(netProfit / firstTwelveRent, 2) - coverage) > 0.01;
  if (invalid) {
    return <div className="revenue-chart-empty revenue-profit-empty is-error"><strong>{copy(locale, "Profit and rent coverage basis is inconsistent", "利润与租金覆盖口径异常")}</strong><span>{copy(locale, "Annual revenue, the five expense categories, net profit, or the coverage divisor do not reconcile.", "年度营收、五项费用、净利润或覆盖除数未形成闭合关系。")}</span></div>;
  }
  const externalLabelY = new Map([
    ["revenue-profit-site-rent", 230],
    ["revenue-profit-utilities", 196],
    ["revenue-profit-payroll", 162],
    ["revenue-profit-other", 112],
    ["revenue-profit-net-profit", 58],
  ]);
  const annualEvidenceId = annualMetric!.evidenceRefs[0];
  const annualReference = evidenceById.get(annualEvidenceId);
  const annualSelected = isSelected(annualMetric!.evidenceRefs, "revenue-profit-annual-revenue", selectedTarget);
  const coverageLevel = coverageRiskLevel(coverage);
  const formulaFacts = [
    { id: "revenue-cover-profit-input", label: "年度净利润", value: `${netProfit.toLocaleString()} ${copy(locale, "CNY 10k", "万")}`, evidenceRefs: profitMetric!.evidenceRefs, symbol: "", riskLevel: null },
    { id: "revenue-cover-rent-input", label: "前12期项目租金", value: `${firstTwelveRent.toLocaleString()} ${copy(locale, "CNY 10k", "万")}`, evidenceRefs: rentEvidenceRefs, symbol: "÷", riskLevel: null },
    { id: "revenue-cover-result", label: "租金覆盖倍数", value: `${coverage.toFixed(2)}×`, evidenceRefs: coverageMetric!.evidenceRefs, symbol: "=", riskLevel: coverageLevel },
  ];
  return (
    <div className="revenue-profit-layout">
      <button aria-label={copy(locale, `Annual revenue ${annualRevenue.toLocaleString()} CNY 10k · ${evidenceText(annualReference, locale)}`, `年度营收${annualRevenue.toLocaleString()}万元，${evidenceText(annualReference, locale)}`)} aria-pressed={annualSelected} className={`revenue-profit-total state-${annualReference?.locationStatus ?? "missing"} ${annualSelected ? "is-selected" : ""}`} data-target-id="revenue-profit-annual-revenue" onClick={() => annualEvidenceId && onEvidenceSelect(annualEvidenceId, "revenue-profit-annual-revenue")} title={copy(locale, `Annual revenue · ${annualRevenue.toLocaleString()} CNY 10k · ${evidenceText(annualReference, locale)}`, `年度营收 · ${annualRevenue.toLocaleString()}万元 · ${evidenceText(annualReference, locale)}`)} type="button"><span>{copy(locale, "Annual revenue", "年度营收")}</span><strong>{annualRevenue.toLocaleString()} {copy(locale, "CNY 10k", "万")}</strong><small>{copy(locale, "Five expense categories + net profit", "五项费用 + 净利润")}</small></button>
      <div className="revenue-profit-composition">
        <svg aria-label={copy(locale, `2024 annual expense and net-profit composition; annual revenue ${annualRevenue.toLocaleString()} CNY 10k.`, `2024 年度费用与净利润构成，年度营收${annualRevenue.toLocaleString()}万元`)} className="revenue-profit-chart" role="img" viewBox="0 0 430 285">
          {slices(composition).map(({ segment, start, end, percentage }, index) => {
            const evidenceId = segment.evidenceRefs[0];
            const reference = evidenceById.get(evidenceId);
            const selected = isSelected(segment.evidenceRefs, segment.id, selectedTarget);
            const action = () => evidenceId && onEvidenceSelect(evidenceId, segment.id);
            const mid = start + (end - start) / 2;
            const edge = polarPoint(245, 144, 108, mid);
            const isMaterial = segment.id === "revenue-profit-material";
            const label = isMaterial ? { x: 320, y: 230 } : { x: 10, y: externalLabelY.get(segment.id) ?? 260 };
            return <g aria-label={`${formatCanonicalLabel(segment.label, locale)} ${segment.value.toLocaleString()} ${copy(locale, "CNY 10k", "万元")}; ${rounded(percentage, 1)}% ${copy(locale, "of annual revenue", "占年度营收")} · ${evidenceText(reference, locale)}`} aria-pressed={selected} className={`revenue-chart-item revenue-profit-segment state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="revenue-profitability-segment" data-target-id={segment.id} key={segment.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" style={cssVars({ "--revenue-segment-color": profitabilityColors[index % profitabilityColors.length] })} tabIndex={0}>
              <title>{formatCanonicalLabel(segment.label, locale)} · {segment.value.toLocaleString()} {copy(locale, "CNY 10k", "万元")} · {rounded(percentage, 1)}% · {evidenceText(reference, locale)}</title>
              <path d={pieSlicePath(245, 144, 108, start, end, 52)} />
              <polyline className="revenue-profit-leader" points={isMaterial ? `${edge.x},${edge.y} 304,${label.y - 4} 312,${label.y - 4}` : `${edge.x},${edge.y} 132,${label.y - 4} 118,${label.y - 4}`} />
              <text className="revenue-profit-label is-external" textAnchor="start" x={label.x} y={label.y - 5}><tspan x={label.x}>{formatCanonicalLabel(segment.label, locale)}</tspan><tspan className="revenue-profit-label-value" dy="16" x={label.x}>{segment.value.toLocaleString()}{copy(locale, " CNY 10k", "万")} · {rounded(percentage, 1)}%</tspan></text>
            </g>;
          })}
          <text className="revenue-profit-center-label" textAnchor="middle" x="245" y="139">{copy(locale, "Net margin", "净利率")}</text>
          <text className="revenue-profit-center-value" textAnchor="middle" x="245" y="163">{netMargin.toFixed(1)}%</text>
        </svg>
      </div>
      <div className="revenue-coverage-relation">
        <div><strong>{copy(locale, "Rent coverage relationship", "租金覆盖关系")}</strong><small>{copy(locale, "Annual net profit ÷ first 12 project rent periods", "年度净利润 ÷ 前12期项目租金")}</small></div>
        <div aria-label={copy(locale, "Deterministic rent-coverage calculation", "租金覆盖倍数确定性计算")} className="revenue-coverage-formula">
          {formulaFacts.map((fact) => {
            const evidenceId = fact.evidenceRefs[0];
            const reference = evidenceById.get(evidenceId);
            const selected = isSelected(fact.evidenceRefs, fact.id, selectedTarget);
            return <div className="revenue-coverage-step" key={fact.id}>{fact.symbol ? <span aria-hidden="true">{fact.symbol}</span> : null}<button aria-label={`${formatCanonicalLabel(fact.label, locale)} ${fact.value} · ${evidenceText(reference, locale)}${fact.riskLevel ? ` · ${copy(locale, ({ forbid: "Prohibited", risk: "Risk", confirm: "Verify", attention: "Monitor", support: "Support" } as const)[fact.riskLevel], coverageRiskLabels[fact.riskLevel])}` : ""}`} aria-pressed={selected} className={`state-${reference?.locationStatus ?? "missing"} ${fact.riskLevel ? `coverage-risk-${fact.riskLevel}` : ""} ${selected ? "is-selected" : ""}`} data-risk-level={fact.riskLevel ?? undefined} data-target-id={fact.id} onClick={() => evidenceId && onEvidenceSelect(evidenceId, fact.id)} title={`${formatCanonicalLabel(fact.label, locale)} · ${fact.value} · ${evidenceText(reference, locale)}`} type="button"><span>{formatCanonicalLabel(fact.label, locale)}</span><strong>{fact.value}</strong><small>{evidenceText(reference, locale)}</small></button></div>;
          })}
        </div>
        <p>{copy(locale, "The coverage multiple is calculated deterministically from the net profit on this page and the transaction rent schedule only.", "覆盖倍数仅由本页净利润与交易租金计划确定性计算。")}</p>
      </div>
    </div>
  );
}

export function RevenueCoreCharts({ detail, evidence, rentEvidenceRefs, selectedTarget, onEvidenceSelect }: { detail: DimensionDetail; evidence: EvidenceReference[]; rentEvidenceRefs: string[]; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceGroupSelect }) {
  const locale = usePublicLocale();
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const incomeBase = detail.series.flatMap((point) => {
    const income = point.measures.find((measure) => measure.label === "确认收入");
    return income ? [{ id: point.id, label: point.label, income }] : [];
  });
  const revenueRows: RevenueRow[] = incomeBase.map((row, index) => {
    const growthTargetId = index === 0 ? null : `${row.income.id}-growth`;
    return {
      ...row,
      growth: index === 0 || incomeBase[index - 1].income.value <= 0 || row.income.value <= 0 ? null : rounded((row.income.value - incomeBase[index - 1].income.value) / incomeBase[index - 1].income.value * 100),
      growthTargetId,
      growthEvidenceRefs: growthTargetId ? [`evidence-${growthTargetId}-inputs`] : [],
      ...(growthTargetId && !evidenceById.has(`evidence-${growthTargetId}-inputs`) ? { growthEvidenceRefs: [...new Set([...incomeBase[index - 1].income.evidenceRefs, ...row.income.evidenceRefs])] } : {}),
    };
  });
  const invoiceRows: InvoiceRow[] = detail.series.flatMap((point) => {
    const invoiced = point.measures.find((measure) => measure.label === "发票");
    const collected = point.measures.find((measure) => measure.label === "回款流水");
    if (!invoiced || !collected) return [];
    const rateTargetId = `${collected.id}-rate`;
    return [{ id: point.id, label: point.label, invoiced, collected, rate: rounded(collected.value / Math.max(invoiced.value, 1) * 100), rateTargetId, rateEvidenceRefs: [`evidence-${rateTargetId}-inputs`], ...(!evidenceById.has(`evidence-${rateTargetId}-inputs`) ? { rateEvidenceRefs: [...new Set([...invoiced.evidenceRefs, ...collected.evidenceRefs])] } : {}) }];
  });
  const totalInvoiced = invoiceRows.reduce((sum, row) => sum + row.invoiced.value, 0);
  const totalCollected = invoiceRows.reduce((sum, row) => sum + row.collected.value, 0);
  const collectionRate = totalInvoiced > 0 ? rounded(totalCollected / totalInvoiced * 100) : null;
  const compositionById = new Map((detail.compositions ?? []).map((composition) => [composition.id, composition]));
  const upstream = compositionById.get("revenue-upstream");
  const downstream = compositionById.get("revenue-downstream");
  const aging = compositionById.get("revenue-receivable-aging");
  const profitability = compositionById.get("revenue-profitability");
  const metrics = new Map(detail.metrics.map((metric) => [metric.id, metric]));
  const evidenceRefsByTarget = new Map<string, string[]>();
  for (const point of detail.series) for (const measure of point.measures) evidenceRefsByTarget.set(measure.id, measure.evidenceRefs);
  for (const composition of detail.compositions ?? []) for (const segment of composition.segments) evidenceRefsByTarget.set(segment.id, segment.evidenceRefs);
  for (const row of revenueRows) if (row.growthTargetId) evidenceRefsByTarget.set(row.growthTargetId, row.growthEvidenceRefs);
  for (const row of invoiceRows) evidenceRefsByTarget.set(row.rateTargetId, row.rateEvidenceRefs);
  evidenceRefsByTarget.set("revenue-profit-annual-revenue", metrics.get("revenue-income-metric")?.evidenceRefs ?? []);
  evidenceRefsByTarget.set("revenue-cover-profit-input", metrics.get("revenue-net-profit-metric")?.evidenceRefs ?? []);
  evidenceRefsByTarget.set("revenue-cover-rent-input", rentEvidenceRefs);
  evidenceRefsByTarget.set("revenue-cover-result", metrics.get("revenue-rent-coverage-metric")?.evidenceRefs ?? []);
  const selectEvidence: EvidenceSelect = (evidenceId, targetId) => onEvidenceSelect(evidenceId, targetId, evidenceRefsByTarget.get(targetId) ?? [evidenceId]);
  return (
    <div aria-label={copy(locale, "Core revenue charts", "营收核心图表")} className="revenue-core-grid" data-semantic-localized>
      <section aria-labelledby="revenue-trend-title" className="revenue-core-panel revenue-panel-trend">
        <header><div><strong id="revenue-trend-title">{copy(locale, "Revenue trend", "营收趋势")}</strong></div><span>{copy(locale, "CNY 10k / %", "万元 / %")}</span></header>
        <div aria-label={copy(locale, "Revenue-trend legend", "营收趋势图例")} className="revenue-core-legend"><span><i className="is-income" />{copy(locale, "Recognized revenue", "确认收入")}</span><span><i className="is-growth" />{copy(locale, "Period-over-period growth", "环比")}</span></div>
        <RevenueChart evidenceById={evidenceById} onEvidenceSelect={selectEvidence} rows={revenueRows} selectedTarget={selectedTarget} />
      </section>
      <section aria-labelledby="revenue-invoice-title" className="revenue-core-panel revenue-panel-invoice">
        <header><div><strong id="revenue-invoice-title">{copy(locale, "Invoice-to-collection cross-check", "票款互证")}</strong></div><span>{copy(locale, "CNY 10k / %", "万元 / %")}</span></header>
        <div aria-label={copy(locale, "Invoice-to-collection legend", "票款互证图例")} className="revenue-core-legend"><span><i className="is-invoiced" />{copy(locale, "Invoiced", "发票")}</span><span><i className="is-collected" />{copy(locale, "Collected", "回款")}</span><span><i className="is-rate" />{copy(locale, "Collection rate", "回款率")}</span></div>
        <InvoiceChart evidenceById={evidenceById} onEvidenceSelect={selectEvidence} rows={invoiceRows} selectedTarget={selectedTarget} />
      </section>
      <section aria-labelledby="revenue-composition-title" className="revenue-core-panel revenue-panel-composition">
        <header><div><strong id="revenue-composition-title">{copy(locale, "Upstream/downstream composition", "上下游构成")}</strong></div><span>%</span></header>
        <CompositionDonuts downstream={downstream} evidenceById={evidenceById} onEvidenceSelect={selectEvidence} selectedTarget={selectedTarget} upstream={upstream} />
      </section>
      <section aria-labelledby="revenue-aging-title" className="revenue-core-panel revenue-panel-aging">
        <header><div><strong id="revenue-aging-title">{copy(locale, "Collection aging", "回款账龄")}</strong></div><span>%</span></header>
        <CollectionChart aging={aging} collectionRate={collectionRate} evidenceById={evidenceById} onEvidenceSelect={selectEvidence} selectedTarget={selectedTarget} />
      </section>
      <section aria-labelledby="revenue-profit-title" className="revenue-core-panel revenue-panel-profitability">
        <header><div><strong id="revenue-profit-title">{copy(locale, "Profit and rent coverage", "利润与租金覆盖")}</strong></div><span>{copy(locale, "CNY 10k / multiple", "万元 / 倍")}</span></header>
          <ProfitabilityPanel composition={profitability} evidenceById={evidenceById} metrics={metrics} onEvidenceSelect={selectEvidence} rentEvidenceRefs={rentEvidenceRefs} selectedTarget={selectedTarget} />
      </section>
    </div>
  );
}

import type { CSSProperties, KeyboardEvent } from "react";
import type {
  DimensionComposition,
  DimensionCompositionSegment,
  DimensionDetail,
  DimensionMetric,
  DimensionSeriesMeasure,
  EvidenceReference,
  ReviewEvidenceTarget,
} from "../contracts/workbench";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatEvidenceLocator, readPublicLocale, usePublicLocale } from "../lib/publicLocale";

type EvidenceSelect = (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void;

interface CashflowRow {
  id: string;
  label: string;
  inflow: DimensionSeriesMeasure;
  outflow: DimensionSeriesMeasure;
  net: DimensionSeriesMeasure;
  rate: number;
  rateEvidenceRefs: string[];
}

const inflowColors = ["#111111", "#30343b", "#59606a", "#7b828c", "#a6abb2", "#d7d9dd"];
const outflowColors = ["#30343b", "#59606a", "#7b828c", "#a6abb2", "#d7d9dd", "#f1f2f4"];

function cssVars(values: Record<string, string | number>) {
  return values as CSSProperties;
}

function rounded(value: number, digits = 1) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function evidenceText(reference: EvidenceReference | undefined) {
  const locale = readPublicLocale();
  if (!reference) return copy(locale, "Evidence not linked", "证据未关联");
  return formatEvidenceLocator(reference.locator, reference.locationStatus, locale);
}

function surface(english: string, chinese: string) {
  return copy(readPublicLocale(), english, chinese);
}

function canonicalLabel(value: string) {
  return formatCanonicalLabel(value, readPublicLocale());
}

function isSelected(evidenceRefs: string[], targetId: string, selectedTarget: ReviewEvidenceTarget | null) {
  return !!selectedTarget && selectedTarget.reviewTargetId === targetId && evidenceRefs.includes(selectedTarget.evidenceRef);
}

function activateWithKeyboard(event: KeyboardEvent<SVGGElement>, action: () => void) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  action();
}

function niceAmountMaximum(value: number) {
  return Math.max(200, Math.ceil(value / 200) * 200);
}

function polarPoint(cx: number, cy: number, radius: number, angle: number) {
  const radians = (angle - 90) * Math.PI / 180;
  return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
}

function pieSlicePath(cx: number, cy: number, radius: number, start: number, end: number) {
  const startPoint = polarPoint(cx, cy, radius, start);
  const endPoint = polarPoint(cx, cy, radius, end);
  const largeArc = end - start > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${startPoint.x} ${startPoint.y} A ${radius} ${radius} 0 ${largeArc} 1 ${endPoint.x} ${endPoint.y} Z`;
}

function pieSlices(segments: DimensionCompositionSegment[]) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  let cursor = 0;
  return segments.map((segment) => {
    const start = cursor;
    const share = total > 0 ? segment.value / total * 100 : 0;
    cursor += share * 3.6;
    return { segment, share: rounded(share), start, end: cursor };
  });
}

function compactPartyName(segment: DimensionCompositionSegment) {
  const names: Record<string, string> = {
    "cashflow-inflow-huadong": "华东建设",
    "cashflow-inflow-changjiang": "长江实业",
    "cashflow-inflow-zhongyuan": "中原控股",
    "cashflow-inflow-dongnan": "东南贸易",
    "cashflow-inflow-qiming": "启明科技",
    "cashflow-outflow-hongyuan": "宏远建筑",
    "cashflow-outflow-dingsheng": "鼎盛材料",
    "cashflow-outflow-huayi": "华翼租赁",
    "cashflow-outflow-citic": "中信银行",
    "cashflow-outflow-xinda": "信达担保",
  };
  return names[segment.id] ?? segment.label;
}

function CashflowTotals({ metrics, evidenceById, selectedTarget, onEvidenceSelect }: {
  metrics: DimensionMetric[];
  evidenceById: Map<string, EvidenceReference>;
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: EvidenceSelect;
}) {
  const locale = usePublicLocale();
  const totals = metrics.filter((metric) => ["cashflow-in", "cashflow-out", "cashflow-net"].includes(metric.id));
  return (
    <div aria-label={surface("Six-month cash-flow totals", "半年现金流合计")} className="cashflow-total-strip">
      {totals.map((metric) => {
        const evidenceId = metric.evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(metric.evidenceRefs, metric.id, selectedTarget);
        return <button aria-label={`${formatCanonicalLabel(metric.label, locale)} ${formatCanonicalNarrative(metric.value, locale)} · ${evidenceText(reference)}`} aria-pressed={selected} className={`cashflow-total-chip tone-${metric.tone} state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-target-id={metric.id} key={metric.id} onClick={() => evidenceId && onEvidenceSelect(evidenceId, metric.id, metric.evidenceRefs)} type="button"><span>{formatCanonicalLabel(metric.label, locale)}</span><strong>{formatCanonicalNarrative(metric.value, locale)}</strong></button>;
      })}
    </div>
  );
}

function AccountFlowChart({ rows, evidenceById, selectedTarget, onEvidenceSelect }: {
  rows: CashflowRow[];
  evidenceById: Map<string, EvidenceReference>;
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: EvidenceSelect;
}) {
  const locale = usePublicLocale();
  if (rows.length === 0) return <div className="cashflow-core-empty"><strong>{surface("Account cash flow unavailable", "账户流水不可用")}</strong><span>{surface("Verifiable monthly inflow and outflow data is missing.", "缺少可核验的月度流入与流出数据。")}</span></div>;
  const plot = { left: 58, right: 662, top: 76, zero: 196, bottom: 306 };
  const amountMax = niceAmountMaximum(Math.max(...rows.flatMap((row) => [row.inflow.value, row.outflow.value])));
  const rateMax = Math.max(15, Math.ceil(Math.max(...rows.map((row) => row.rate)) / 5) * 5);
  const centers = rows.map((_, index) => rows.length === 1 ? 360 : plot.left + 44 + index * ((plot.right - plot.left - 88) / (rows.length - 1)));
  const inflowY = (value: number) => plot.zero - value / amountMax * (plot.zero - plot.top);
  const outflowHeight = (value: number) => value / amountMax * (plot.bottom - plot.zero);
  const rateY = (value: number) => plot.zero - value / rateMax * (plot.zero - plot.top);
  const ratePoints = rows.map((row, index) => ({ row, x: centers[index], y: rateY(row.rate) }));
  return (
    <svg aria-label={surface("Account cash flow: inflow bars extend upward, outflow bars downward, amounts use the left axis, and the net-inflow-rate line uses a separate right percentage axis with a 0% baseline.", "账户流水：流入柱向上、流出柱向下，金额使用左轴；净流入率折线使用独立右侧百分比轴并以0%为基线")} className="cashflow-core-svg cashflow-account-chart" role="img" viewBox="0 0 720 330">
      {[plot.top, plot.zero, plot.bottom].map((y, index) => <line aria-hidden="true" className={index === 1 ? "cashflow-zero-line" : "cashflow-grid-line"} key={y} x1={plot.left} x2={plot.right} y1={y} y2={y} />)}
      <text className="cashflow-axis-unit" x={plot.left} y="18">{surface("Left axis · amount (CNY 10k)", "左轴 · 金额（万元）")}</text>
      <text className="cashflow-axis-unit is-right" textAnchor="end" x={plot.right} y="18">{surface("Right axis · net-inflow rate (%)", "右轴 · 净流入率（%）")}</text>
      <text className="cashflow-axis-label" textAnchor="end" x={plot.left - 8} y={plot.top + 4}>+{amountMax}</text>
      <text className="cashflow-axis-label" textAnchor="end" x={plot.left - 8} y={plot.zero + 4}>0</text>
      <text className="cashflow-axis-label" textAnchor="end" x={plot.left - 8} y={plot.bottom + 4}>-{amountMax}</text>
      <text className="cashflow-axis-label is-right" x={plot.right + 7} y={plot.top + 4}>{rateMax}%</text>
      <text className="cashflow-axis-label is-right" x={plot.right + 7} y={plot.zero + 4}>0%</text>
      <text className="cashflow-zero-caption" textAnchor="end" x={plot.right} y={plot.zero - 6}>{surface("Amount 0 / net-inflow rate 0%", "金额0 / 净流入率0%")}</text>
      {rows.map((row, index) => {
        const x = centers[index];
        const barY = inflowY(row.inflow.value);
        const inEvidenceId = row.inflow.evidenceRefs[0];
        const outEvidenceId = row.outflow.evidenceRefs[0];
        const inReference = evidenceById.get(inEvidenceId);
        const outReference = evidenceById.get(outEvidenceId);
        const inSelected = isSelected(row.inflow.evidenceRefs, row.inflow.id, selectedTarget);
        const outSelected = isSelected(row.outflow.evidenceRefs, row.outflow.id, selectedTarget);
        const inAction = () => inEvidenceId && onEvidenceSelect(inEvidenceId, row.inflow.id, row.inflow.evidenceRefs);
        const outAction = () => outEvidenceId && onEvidenceSelect(outEvidenceId, row.outflow.id, row.outflow.evidenceRefs);
        return <g key={row.id}>
          <g aria-label={surface(`${formatCanonicalLabel(row.label, locale)} inflow ${row.inflow.value} CNY 10k · ${evidenceText(inReference)}`, `${row.label}流入${row.inflow.value}万元，${evidenceText(inReference)}`)} aria-pressed={inSelected} className={`cashflow-chart-item cashflow-inflow-bar state-${inReference?.locationStatus ?? "missing"} ${inSelected ? "is-selected" : ""}`} data-chart-kind="cashflow-inflow-bar" data-target-id={row.inflow.id} onClick={inAction} onKeyDown={(event) => activateWithKeyboard(event, inAction)} role="button" tabIndex={0}><title>{formatCanonicalLabel(row.label, locale)} · {surface("inflow", "流入")} · {row.inflow.value} {surface("CNY 10k", "万元")} · {evidenceText(inReference)}</title><rect height={plot.zero - barY} rx="3" width="28" x={x - 14} y={barY} /><text className="cashflow-amount-label" textAnchor="middle" x={x} y={barY - 7}>{row.inflow.value}</text></g>
          <g aria-label={surface(`${formatCanonicalLabel(row.label, locale)} outflow ${row.outflow.value} CNY 10k · ${evidenceText(outReference)}`, `${row.label}流出${row.outflow.value}万元，${evidenceText(outReference)}`)} aria-pressed={outSelected} className={`cashflow-chart-item cashflow-outflow-bar state-${outReference?.locationStatus ?? "missing"} ${outSelected ? "is-selected" : ""}`} data-chart-kind="cashflow-outflow-bar" data-target-id={row.outflow.id} onClick={outAction} onKeyDown={(event) => activateWithKeyboard(event, outAction)} role="button" tabIndex={0}><title>{formatCanonicalLabel(row.label, locale)} · {surface("outflow", "流出")} · {row.outflow.value} {surface("CNY 10k", "万元")} · {evidenceText(outReference)}</title><rect height={outflowHeight(row.outflow.value)} rx="3" width="28" x={x - 14} y={plot.zero} /><text className="cashflow-amount-label is-outflow" textAnchor="middle" x={x} y={plot.zero + outflowHeight(row.outflow.value) - 8}>-{row.outflow.value}</text></g>
          <text aria-hidden="true" className="cashflow-period-label" textAnchor="middle" x={x} y="324">{formatCanonicalLabel(row.label, locale)}</text>
        </g>;
      })}
      <polyline aria-hidden="true" className="cashflow-rate-line" points={ratePoints.map((point) => `${point.x},${point.y}`).join(" ")} />
      {ratePoints.map(({ row, x, y }) => {
        const reference = evidenceById.get(row.rateEvidenceRefs[0]);
        const targetId = `${row.id}-net-rate`;
        const selected = isSelected(row.rateEvidenceRefs, targetId, selectedTarget);
        const action = () => onEvidenceSelect(row.rateEvidenceRefs[0], targetId, row.rateEvidenceRefs);
        return <g aria-label={surface(`${canonicalLabel(row.label)} net-inflow rate ${row.rate.toFixed(1)}%, deterministically derived as inflow minus outflow divided by inflow · ${evidenceText(reference)}`, `${row.label}净流入率${row.rate.toFixed(1)}%，由流入减流出后除以流入确定性派生，${evidenceText(reference)}`)} aria-pressed={selected} className={`cashflow-chart-item cashflow-rate-point state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="cashflow-net-rate-point" data-target-id={targetId} key={targetId} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{canonicalLabel(row.label)} · {surface("net-inflow rate", "净流入率")} · {row.rate.toFixed(1)}% · {evidenceText(reference)}</title><line aria-hidden="true" className="cashflow-rate-label-guide" x1={x} x2={x} y1="55" y2={Math.max(62, y - 7)} /><text className="cashflow-rate-label" textAnchor="middle" x={x} y="49">+{row.rate.toFixed(1)}%</text><circle cx={x} cy={y} r="5" /></g>;
      })}
    </svg>
  );
}

function PartyPie({ composition, colors, evidenceById, selectedTarget, onEvidenceSelect }: {
  composition: DimensionComposition | undefined;
  colors: string[];
  evidenceById: Map<string, EvidenceReference>;
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: EvidenceSelect;
}) {
  if (!composition || composition.segments.length === 0) return <div className="cashflow-core-empty is-party"><strong>{surface(`${composition ? canonicalLabel(composition.label) : "Counterparty"} composition unavailable`, `${composition?.label ?? "交易对手"}构成不可用`)}</strong><span>{surface("Verifiable counterparty-composition data is missing.", "缺少可核验的交易对手构成数据。")}</span></div>;
  const slices = pieSlices(composition.segments);
  const total = composition.segments.reduce((sum, segment) => sum + segment.value, 0);
  return (
    <div className="cashflow-party-unit">
      <header><strong>{canonicalLabel(composition.label)}</strong><span>{surface(`Total ${total.toLocaleString()} CNY 10k`, `合计 ${total.toLocaleString()} 万元`)}</span></header>
      <svg aria-label={surface(`${canonicalLabel(composition.label)} counterparty-composition pie; sectors directly label compact name, share, and payment term.`, `${composition.label}交易对手构成饼图，扇区直接标注精简名称、占比和账期`)} className="cashflow-core-svg cashflow-party-pie" role="img" viewBox="0 0 340 300">
        {slices.map(({ segment, share, start, end }, index) => {
          const mid = start + (end - start) / 2;
          const labelAngle = mid + (segment.id === "cashflow-outflow-xinda" ? 5 : 0);
          const labelRadius = segment.id === "cashflow-outflow-citic" ? 108 : ["cashflow-inflow-zhongyuan", "cashflow-outflow-huayi"].includes(segment.id) ? 102 : share < 10 ? 104 : share < 13 ? 91 : 77;
          const point = polarPoint(170, 158, labelRadius, labelAngle);
          const evidenceId = segment.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          const selected = isSelected(segment.evidenceRefs, segment.id, selectedTarget);
          const action = () => evidenceId && onEvidenceSelect(evidenceId, segment.id, segment.evidenceRefs);
          return <g aria-label={surface(`${canonicalLabel(composition.label)} ${canonicalLabel(segment.label)} ${segment.value} CNY 10k, share ${share.toFixed(1)}%, payment term ${segment.note ? canonicalLabel(segment.note) : "not provided"} · ${evidenceText(reference)}`, `${composition.label}${segment.label}${segment.value}万元，占比${share.toFixed(1)}%，账期${segment.note ?? "未提供"}，${evidenceText(reference)}`)} aria-pressed={selected} className={`cashflow-chart-item cashflow-party-segment state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind={`cashflow-${composition.id === "cashflow-inflow-parties" ? "inflow" : "outflow"}-party-segment`} data-target-id={segment.id} key={segment.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" style={cssVars({ "--cashflow-segment-color": colors[index % colors.length] })} tabIndex={0}><title>{canonicalLabel(segment.label)} · {segment.value} {surface("CNY 10k", "万元")} · {share.toFixed(1)}% · {segment.note ? canonicalLabel(segment.note) : surface("Payment term not provided", "未提供账期")} · {evidenceText(reference)}</title><path d={pieSlicePath(170, 158, 132, start, end)} /><text className={share < 10 ? "cashflow-party-label is-compact" : "cashflow-party-label"} textAnchor="middle" x={point.x} y={point.y - 12}><tspan x={point.x}>{canonicalLabel(compactPartyName(segment))}</tspan><tspan className="cashflow-party-share" dy="15" x={point.x}>{share.toFixed(1)}%</tspan><tspan className="cashflow-party-term" dy="14" x={point.x}>{segment.note ? canonicalLabel(segment.note) : "—"}</tspan></text></g>;
        })}
      </svg>
    </div>
  );
}

export function CashflowCoreCharts({ detail, evidence, selectedTarget, onEvidenceSelect }: {
  detail: DimensionDetail;
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: EvidenceSelect;
}) {
  const locale = usePublicLocale();
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const rows: CashflowRow[] = detail.series.flatMap((point) => {
    const inflow = point.measures.find((measure) => measure.label === "流入");
    const outflow = point.measures.find((measure) => measure.label === "流出");
    const net = point.measures.find((measure) => measure.label === "净额");
    if (!inflow || !outflow || !net) return [];
    const derivedEvidenceId = `evidence-${point.id}-net-rate-inputs`;
    const rateEvidenceRefs = evidenceById.has(derivedEvidenceId)
      ? [derivedEvidenceId]
      : Array.from(new Set([...inflow.evidenceRefs, ...outflow.evidenceRefs]));
    return [{ id: point.id, label: point.label, inflow, outflow, net, rate: rounded((inflow.value - outflow.value) / Math.max(inflow.value, 1) * 100), rateEvidenceRefs }];
  });
  const compositions = new Map((detail.compositions ?? []).map((composition) => [composition.id, composition]));
  const inflowParties = compositions.get("cashflow-inflow-parties");
  const outflowParties = compositions.get("cashflow-outflow-parties");
  const concentration = (composition: DimensionComposition | undefined) => {
    if (!composition || composition.segments.length === 0) return null;
    const total = composition.segments.reduce((sum, segment) => sum + segment.value, 0);
    const topFive = composition.segments.filter((segment) => segment.label !== "其他").reduce((sum, segment) => sum + segment.value, 0);
    return rounded(topFive / Math.max(total, 1) * 100);
  };
  const inflowConcentration = concentration(inflowParties);
  const outflowConcentration = concentration(outflowParties);
  return (
    <div aria-label={copy(locale, "Core cash-flow charts", "流水核心图表")} className="cashflow-core-grid" data-semantic-localized>
      <section aria-labelledby="cashflow-account-title" className="cashflow-core-panel cashflow-account-panel">
        <header><div><strong id="cashflow-account-title">{copy(locale, "Account cash flow", "账户流水")}</strong><small>{copy(locale, "Inflows extend upward and outflows downward; net-inflow rate uses a separate percentage axis.", "流入向上、流出向下；净流入率使用独立百分比轴")}</small></div><span>{rows.length} {copy(locale, "periods · CNY 10k", "个时段 · 万元")}</span></header>
        <CashflowTotals evidenceById={evidenceById} metrics={detail.metrics} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} />
        <div aria-label={copy(locale, "Account-cash-flow legend", "账户流水图例")} className="cashflow-core-legend"><span><i className="is-inflow" />{copy(locale, "Inflow", "流入")}</span><span><i className="is-outflow" />{copy(locale, "Outflow", "流出")}</span><span><i className="is-rate" />{copy(locale, "Net-inflow rate", "净流入率")}</span><small>{copy(locale, "Explicit 0% baseline", "0%基线明确")}</small></div>
        <AccountFlowChart evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} rows={rows} selectedTarget={selectedTarget} />
      </section>
      <section aria-labelledby="cashflow-parties-title" className="cashflow-core-panel cashflow-parties-panel">
        <header><div><strong id="cashflow-parties-title">{copy(locale, "Counterparties", "交易对手")}</strong><small>{copy(locale, "Inflow- and outflow-party amount composition; sectors label share and payment term directly.", "流入方与流出方金额构成，扇区直接标注占比和账期")}</small></div><span>{copy(locale, "Six-month basis", "半年口径")}</span></header>
        <div aria-label={copy(locale, "Counterparty Top-5 concentration", "交易对手前五名集中度")} className="cashflow-party-summary"><div><span>{copy(locale, "Inflow parties Top 5", "流入方前五名")}</span><strong>{inflowConcentration === null ? copy(locale, "Unavailable", "不可用") : `${inflowConcentration.toFixed(1)}%`}</strong></div><div><span>{copy(locale, "Outflow parties Top 5", "流出方前五名")}</span><strong>{outflowConcentration === null ? copy(locale, "Unavailable", "不可用") : `${outflowConcentration.toFixed(1)}%`}</strong></div></div>
        <div className="cashflow-party-pair"><PartyPie colors={inflowColors} composition={inflowParties} evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} /><PartyPie colors={outflowColors} composition={outflowParties} evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} /></div>
      </section>
    </div>
  );
}

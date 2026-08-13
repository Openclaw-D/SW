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
import { copy, formatCanonicalLabel, formatEvidenceLocator, readPublicLocale, usePublicLocale } from "../lib/publicLocale";

type EvidenceSelect = (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void;

interface DebtHistoryRow {
  id: string;
  label: string;
  enterprise: DimensionSeriesMeasure;
  personal: DimensionSeriesMeasure;
}

interface DebtRepaymentRow {
  id: string;
  label: string;
  due: DimensionSeriesMeasure;
  capacity: DimensionSeriesMeasure;
  coverage: number;
}

const debtCategoryColors = ["#111111", "#30343b", "#59606a", "#7b828c", "#a6abb2", "#d7d9dd"];
const exposureGlobalLimit = 1000;
const formalExposureChannels: Record<string, { limit: number; color: string }> = {
  "200直": { limit: 200, color: "#111111" },
  "200核心": { limit: 200, color: "#30343b" },
  "300核心": { limit: 300, color: "#59606a" },
  "500核心": { limit: 500, color: "#7b828c" },
};

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

function evidenceText(reference: EvidenceReference | undefined) {
  const locale = readPublicLocale();
  if (!reference) return copy(locale, "No evidence reference", "无证据引用");
  return formatEvidenceLocator(reference.locator, reference.locationStatus, locale);
}

function surface(english: string, chinese: string) {
  return copy(readPublicLocale(), english, chinese);
}

function canonicalLabel(value: string) {
  return formatCanonicalLabel(value, readPublicLocale());
}

function debtChannelLabel(value: string) {
  const labels: Record<string, [string, string]> = {
    "200直": ["CNY 2m direct channel", "200直"],
    "200核心": ["CNY 2m core channel", "200核心"],
    "300核心": ["CNY 3m core channel", "300核心"],
    "500核心": ["CNY 5m core channel", "500核心"],
  };
  const pair = labels[value];
  return pair ? copy(readPublicLocale(), ...pair) : canonicalLabel(value);
}

function isSelected(evidenceRefs: string[], targetId: string, selectedTarget: ReviewEvidenceTarget | null) {
  return selectedTarget?.reviewTargetId === targetId && evidenceRefs.includes(selectedTarget.evidenceRef);
}

function activateWithKeyboard(event: KeyboardEvent<SVGGElement>, action: () => void) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  action();
}

function polarPoint(cx: number, cy: number, radius: number, angle: number) {
  const radians = (angle - 90) * Math.PI / 180;
  return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
}

function pieSlicePath(cx: number, cy: number, radius: number, start: number, end: number, innerRadius = 0) {
  const startPoint = polarPoint(cx, cy, radius, start);
  const endPoint = polarPoint(cx, cy, radius, end);
  const largeArc = end - start > 180 ? 1 : 0;
  if (innerRadius > 0) {
    const innerEnd = polarPoint(cx, cy, innerRadius, end);
    const innerStart = polarPoint(cx, cy, innerRadius, start);
    return `M ${startPoint.x} ${startPoint.y} A ${radius} ${radius} 0 ${largeArc} 1 ${endPoint.x} ${endPoint.y} L ${innerEnd.x} ${innerEnd.y} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${innerStart.x} ${innerStart.y} Z`;
  }
  return `M ${cx} ${cy} L ${startPoint.x} ${startPoint.y} A ${radius} ${radius} 0 ${largeArc} 1 ${endPoint.x} ${endPoint.y} Z`;
}

function compositionSlices(composition: DimensionComposition) {
  const segments = composition.segments.filter((segment) => segment.value > 0);
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  let start = 0;
  return segments.map((segment) => {
    const percentage = segment.value / Math.max(total, 1) * 100;
    const end = start + percentage * 3.6;
    const slice = { segment, percentage, start, end };
    start = end;
    return slice;
  });
}

function shortDebtLabel(segment: DimensionCompositionSegment) {
  if (segment.label === "法定代表人") return "法代";
  return segment.label;
}

function metricNumber(metric: DimensionMetric | undefined) {
  if (!metric) return null;
  const parsed = Number(metric.value.replace(/[,，]/g, "").match(/-?\d+(?:\.\d+)?/)?.[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function exposureShare(segment: DimensionCompositionSegment) {
  const value = Number(segment.note?.match(/份额(\d+)%/)?.[1]);
  return Number.isFinite(value) ? value : null;
}

function DebtProjectExposure({ composition, metrics, evidenceById, selectedTarget, onEvidenceSelect }: { composition: DimensionComposition | undefined; metrics: Map<string, DimensionMetric>; evidenceById: Map<string, EvidenceReference>; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  const requiredFactIds = ["debt-exposure-history", "debt-exposure-current", "debt-exposure-total", "debt-exposure-deduplication"];
  const displayedFactIds = ["debt-exposure-current", "debt-exposure-total", "debt-exposure-deduplication"];
  const requiredFacts = requiredFactIds.map((id) => metrics.get(id));
  const displayedFacts = displayedFactIds.map((id) => metrics.get(id));
  if (!composition?.segments.some((segment) => segment.value > 0) || requiredFacts.some((metric) => !metric)) {
    return <div className="debt-chart-empty debt-exposure-empty"><strong>{surface("Project channel exposure unavailable", "项目通道敞口不可用")}</strong><span>{surface("Exposure inputs are missing from DimensionDetail.metrics or compositions.", "DimensionDetail.metrics 或 compositions 中缺少敞口输入。")}</span></div>;
  }
  const history = metricNumber(metrics.get("debt-exposure-history"));
  const current = metricNumber(metrics.get("debt-exposure-current"));
  const total = metricNumber(metrics.get("debt-exposure-total"));
  const compositionTotal = composition.segments.reduce((sum, segment) => sum + segment.value, 0);
  const uniqueLabels = new Set(composition.segments.map((segment) => segment.label));
  const channelMetadata = composition.segments.map((segment) => ({
    presentation: formalExposureChannels[segment.label],
    share: exposureShare(segment),
    contractMatches: segment.note?.includes("formal-product-channels-v2") === true,
  }));
  const selectedCapacity = channelMetadata.reduce((sum, item) => sum + (item.presentation?.limit ?? 0), 0);
  const shareTotal = channelMetadata.reduce((sum, item) => sum + (item.share ?? 0), 0);
  const invalid = history === null
    || current === null
    || total === null
    || Math.abs(history + current - total) > 0.01
    || Math.abs(compositionTotal - total) > 0.01
    || composition.segments.length !== Object.keys(formalExposureChannels).length
    || uniqueLabels.size !== composition.segments.length
    || channelMetadata.some((item) => !item.presentation || item.share === null || !item.contractMatches)
    || composition.segments.some((segment) => segment.value <= 0 || segment.value > formalExposureChannels[segment.label].limit)
    || shareTotal !== 100
    || total > selectedCapacity
    || total > exposureGlobalLimit;
  if (invalid) {
    return <div className="debt-chart-empty debt-exposure-empty is-error"><strong>{surface("Project channel exposure basis is inconsistent", "项目通道敞口口径异常")}</strong><span>{surface("Amount reconciliation, formal-channel uniqueness, channel limits, or integer shares failed validation.", "金额闭合、正式通道唯一性、额度上限或整数份额未通过校验。")}</span></div>;
  }
  const historyMetric = metrics.get("debt-exposure-history")!;
  const centerEvidenceId = historyMetric.evidenceRefs[0];
  const centerReference = evidenceById.get(centerEvidenceId);
  const centerTargetId = "debt-exposure-history-center";
  const centerSelected = isSelected(historyMetric.evidenceRefs, centerTargetId, selectedTarget);
  const centerAction = () => centerEvidenceId && onEvidenceSelect(centerEvidenceId, centerTargetId, historyMetric.evidenceRefs);
  return (
    <div className="debt-exposure-layout">
      <svg aria-label={surface(`Project channel exposure: center is historical outstanding ${history}W; outer-ring formal channel allocation totals ${total}W; current financing ${current}W.`, `项目通道敞口：圆心为历史存量${history}W，外圈正式产品通道分配合计${total}W，本次融资${current}W`)} className="debt-core-svg debt-exposure-chart" role="img" viewBox="0 0 500 270">
        {compositionSlices(composition).map(({ segment, percentage, start, end }, index) => {
          const evidenceId = segment.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          const selected = isSelected(segment.evidenceRefs, segment.id, selectedTarget);
          const action = () => evidenceId && onEvidenceSelect(evidenceId, segment.id, segment.evidenceRefs);
          const channel = formalExposureChannels[segment.label];
          const share = exposureShare(segment)!;
          const label = polarPoint(250, 136, 92, start + (end - start) / 2);
          return <g aria-label={surface(`${debtChannelLabel(segment.label)} project allocation ${segment.value.toLocaleString()} CNY 10k; channel limit ${channel.limit} CNY 10k; displayed share ${share}%; exact share ${rounded(percentage)}% · ${evidenceText(reference)}`, `${segment.label}项目分配${segment.value.toLocaleString()}W，通道限额${channel.limit}W，整数份额${share}%，精确份额${rounded(percentage)}%，${evidenceText(reference)}`)} aria-pressed={selected} className={`debt-chart-item debt-exposure-segment state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="debt-project-exposure-segment" data-target-id={segment.id} key={segment.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" style={cssVars({ "--debt-segment-color": channel.color })} tabIndex={0}>
            <title>{segment.label} · 分配 {segment.value.toLocaleString()}W · 限额 {channel.limit}W · 份额 {share}% · {evidenceText(reference)}</title>
            <path d={pieSlicePath(250, 136, 118, start, end, 61)} />
            <text className="debt-pie-label debt-exposure-label" textAnchor="middle" x={label.x} y={label.y - 5}><tspan x={label.x}>{canonicalLabel(segment.label)}</tspan><tspan className="debt-pie-share" dy="17" x={label.x}>{segment.value.toLocaleString()}W</tspan></text>
          </g>;
        })}
        <g aria-label={surface(`Historical exposure ${history} CNY 10k · ${evidenceText(centerReference)}`, `历史存量敞口${history}W，${evidenceText(centerReference)}`)} aria-pressed={centerSelected} className={`debt-chart-item debt-exposure-center state-${centerReference?.locationStatus ?? "missing"} ${centerSelected ? "is-selected" : ""}`} data-chart-kind="debt-project-exposure-history" data-target-id={centerTargetId} onClick={centerAction} onKeyDown={(event) => activateWithKeyboard(event, centerAction)} role="button" tabIndex={0}>
          <title>{surface("Historical exposure", "历史存量敞口")} · {history} {surface("CNY 10k", "W")} · {evidenceText(centerReference)}</title>
          <circle cx="250" cy="136" r="54" />
          <text textAnchor="middle" x="250" y="129">{surface("Historical outstanding", "历史存量")}</text>
          <text className="debt-exposure-history-value" textAnchor="middle" x="250" y="155">{history.toLocaleString()}W</text>
        </g>
      </svg>
      <div aria-label={surface("Project channel exposure quick facts", "项目通道敞口快速事实")} className="debt-exposure-facts">
        {displayedFacts.map((metric) => {
          const evidenceId = metric!.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          const selected = isSelected(metric!.evidenceRefs, metric!.id, selectedTarget);
          return <button aria-label={`${canonicalLabel(metric!.label)} ${canonicalLabel(metric!.value)} · ${canonicalLabel(metric!.note)} · ${evidenceText(reference)}`} aria-pressed={selected} className={`tone-${metric!.tone} state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-target-id={metric!.id} key={metric!.id} onClick={() => evidenceId && onEvidenceSelect(evidenceId, metric!.id, metric!.evidenceRefs)} title={`${canonicalLabel(metric!.label)} · ${canonicalLabel(metric!.value)} · ${evidenceText(reference)}`} type="button"><span>{canonicalLabel(metric!.label)}</span><strong>{canonicalLabel(metric!.value)}</strong><small>{canonicalLabel(metric!.note)}</small></button>;
        })}
      </div>
    </div>
  );
}

function DebtSubjectPie({ composition, evidenceById, selectedTarget, onEvidenceSelect }: { composition: DimensionComposition | undefined; evidenceById: Map<string, EvidenceReference>; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  if (!composition?.segments.some((segment) => segment.value > 0)) return <div className="debt-chart-empty"><strong>{surface(`${composition ? canonicalLabel(composition.label) : "Debt composition"} unavailable`, `${composition?.label ?? "负债构成"}不可用`)}</strong><span>{surface("DimensionDetail.compositions has no entity composition that can be plotted.", "DimensionDetail.compositions 中没有可绘制的主体构成。")}</span></div>;
  return (
    <svg aria-label={surface(`${canonicalLabel(composition.label)} creditor-composition pie; categories and shares are labeled directly.`, `${composition.label}债权人构成饼图，类别和占比直接标注`)} className="debt-core-svg debt-subject-pie" role="img" viewBox="0 0 520 260">
      {compositionSlices(composition).map(({ segment, percentage, start, end }, index) => {
        const evidenceId = segment.evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(segment.evidenceRefs, segment.id, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, segment.id, segment.evidenceRefs);
        const compact = percentage < 14;
        const label = polarPoint(260, 132, compact ? 88 : 76, start + (end - start) / 2);
        return (
          <g aria-label={surface(`${canonicalLabel(composition.label)} ${canonicalLabel(segment.label)} ${segment.value.toLocaleString()} CNY 10k; share ${rounded(percentage)}% · ${evidenceText(reference)}`, `${composition.label}${segment.label}${segment.value.toLocaleString()}${segment.unit}，占比${rounded(percentage)}%，${evidenceText(reference)}`)} aria-pressed={selected} className={`debt-chart-item debt-pie-segment ${compact ? "is-compact" : ""} state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind={composition.id === "debt-enterprise-creditors" ? "debt-enterprise-segment" : "debt-personal-segment"} data-target-id={segment.id} key={segment.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" style={cssVars({ "--debt-segment-color": debtCategoryColors[index % debtCategoryColors.length] })} tabIndex={0}>
            <title>{segment.label} · {segment.value.toLocaleString()}{segment.unit} · {rounded(percentage)}% · {evidenceText(reference)}</title>
            <path d={pieSlicePath(260, 132, 112, start, end)} />
            <text className="debt-pie-label" textAnchor="middle" x={label.x} y={label.y - 5}><tspan x={label.x}>{canonicalLabel(shortDebtLabel(segment))}</tspan><tspan className="debt-pie-share" dy="17" x={label.x}>{rounded(percentage)}%</tspan></text>
          </g>
        );
      })}
    </svg>
  );
}

function DebtTrendChart({ rows, evidenceById, selectedTarget, onEvidenceSelect }: { rows: DebtHistoryRow[]; evidenceById: Map<string, EvidenceReference>; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  if (!rows.length) return <div className="debt-chart-empty"><strong>{surface("Debt trend unavailable", "负债趋势不可用")}</strong><span>{surface("Enterprise or personal debt is missing from DimensionDetail.series.", "DimensionDetail.series 中缺少企业或个人主体负债。")}</span></div>;
  const totals = rows.map((row) => row.enterprise.value + row.personal.value);
  const maximum = niceMaximum(Math.max(...totals));
  const plot = { left: 54, right: 476, top: 38, bottom: 202 };
  const centers = rows.map((_, index) => rows.length === 1 ? 265 : plot.left + 50 + index * ((plot.right - plot.left - 100) / (rows.length - 1)));
  const y = (value: number) => plot.bottom - value / maximum * (plot.bottom - plot.top);
  const totalPoints = rows.map((row, index) => ({ row, total: totals[index], x: centers[index], y: y(totals[index]) }));
  return (
    <svg aria-label={surface("Debt trend: enterprise and personal debt use stacked bars; total debt is deterministically derived from both values for each period and plotted on the same amount axis.", "负债趋势：企业负债与个人负债堆叠柱，总负债折线由同一期间两项主体负债确定性派生，金额同轴")} className="debt-core-svg debt-trend-chart" role="img" viewBox="0 0 520 250">
      {[0, maximum / 2, maximum].map((tick) => { const tickY = y(tick); return <g aria-hidden="true" key={tick}><line className="debt-grid-line" x1={plot.left} x2={plot.right} y1={tickY} y2={tickY} /><text className="debt-axis-label" textAnchor="end" x={plot.left - 8} y={tickY + 4}>{Math.round(tick).toLocaleString()}</text></g>; })}
      <text className="debt-axis-unit" x={plot.left} y="18">{surface("Amount · CNY 10k", "金额 · 万元")}</text>
      {rows.flatMap((row, index) => {
        const enterpriseY = y(row.enterprise.value);
        const totalY = y(row.enterprise.value + row.personal.value);
        return [
          { measure: row.enterprise, className: "is-enterprise", x: centers[index] - 28, y: enterpriseY, height: plot.bottom - enterpriseY, kind: "debt-enterprise-bar" },
          { measure: row.personal, className: "is-personal", x: centers[index] - 28, y: totalY, height: enterpriseY - totalY, kind: "debt-personal-bar" },
        ].map(({ measure, className, x, y: barY, height, kind }) => {
          const evidenceId = measure.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          const selected = isSelected(measure.evidenceRefs, measure.id, selectedTarget);
          const action = () => evidenceId && onEvidenceSelect(evidenceId, measure.id, measure.evidenceRefs);
          return <g aria-label={surface(`${canonicalLabel(row.label)} ${canonicalLabel(measure.label)} ${measure.value.toLocaleString()} CNY 10k · ${evidenceText(reference)}`, `${row.label}${measure.label}${measure.value.toLocaleString()}${measure.unit}，${evidenceText(reference)}`)} aria-pressed={selected} className={`debt-chart-item debt-stacked-bar ${className} state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind={kind} data-target-id={measure.id} key={measure.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{canonicalLabel(row.label)} · {canonicalLabel(measure.label)} · {measure.value.toLocaleString()} {surface("CNY 10k", measure.unit)} · {evidenceText(reference)}</title><rect height={height} rx="2" width="56" x={x} y={barY} /></g>;
        });
      })}
      <polyline aria-hidden="true" className="debt-total-line" points={totalPoints.map((point) => `${point.x},${point.y}`).join(" ")} />
      {totalPoints.map(({ row, total, x, y: pointY }) => {
        const targetId = `${row.id}-total`;
        const derivedEvidenceId = `evidence-${targetId}-inputs`;
        const evidenceRefs = evidenceById.has(derivedEvidenceId) ? [derivedEvidenceId] : [...new Set([...row.enterprise.evidenceRefs, ...row.personal.evidenceRefs])];
        const evidenceId = evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(evidenceRefs, targetId, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, targetId, evidenceRefs);
        return <g aria-label={surface(`${canonicalLabel(row.label)} total debt ${total.toLocaleString()} CNY 10k, deterministically derived as enterprise plus personal debt · ${evidenceText(reference)}`, `${row.label}总负债${total.toLocaleString()}万元，由企业负债加个人负债确定性派生，${evidenceText(reference)}`)} aria-pressed={selected} className={`debt-chart-item debt-total-point state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="debt-total-point" data-target-id={targetId} key={targetId} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{canonicalLabel(row.label)} · {surface("total debt", "总负债")} · {total.toLocaleString()} {surface("CNY 10k", "万元")} · {evidenceText(reference)}</title><circle cx={x} cy={pointY} r="5" /><text className="debt-total-label" textAnchor="middle" x={x} y={Math.max(plot.top + 10, pointY - 10)}>{total.toLocaleString()}</text><text className="debt-period-label" textAnchor="middle" x={x} y="238">{canonicalLabel(row.label)}</text></g>;
      })}
    </svg>
  );
}

function DebtRepaymentChart({ rows, evidenceById, selectedTarget, onEvidenceSelect }: { rows: DebtRepaymentRow[]; evidenceById: Map<string, EvidenceReference>; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  if (!rows.length) return <div className="debt-chart-empty"><strong>{surface("Repayment capacity unavailable", "偿债能力不可用")}</strong><span>{surface("DimensionDetail.seriesGroups has no future repayment series.", "DimensionDetail.seriesGroups 中没有未来偿债序列。")}</span></div>;
  const maximum = niceMaximum(Math.max(...rows.flatMap((row) => [row.due.value, row.capacity.value])));
  const totalDue = rows.reduce((sum, row) => sum + row.due.value, 0);
  const totalCapacity = rows.reduce((sum, row) => sum + row.capacity.value, 0);
  const aggregateCoverage = rounded(totalCapacity / Math.max(totalDue, 1) * 100);
  const plot = { left: 50, right: 614, top: 42, bottom: 202 };
  const centers = rows.map((_, index) => rows.length === 1 ? 330 : plot.left + 24 + index * ((plot.right - plot.left - 48) / (rows.length - 1)));
  const y = (value: number) => plot.bottom - value / maximum * (plot.bottom - plot.top);
  const points = rows.map((row, index) => ({ row, x: centers[index], y: y(row.capacity.value) }));
  return (
    <svg aria-label={surface(`Repayment capacity: next-12-month debt-due bars and repayment-capacity line use one CNY-10k axis; aggregate coverage ${aggregateCoverage}% is deterministically derived from the two totals.`, `偿债能力：未来12月到期负债柱形与可偿还能力折线使用同一万元轴，合计覆盖率${aggregateCoverage}%由两项合计确定性派生`)} className="debt-core-svg debt-repayment-chart" role="img" viewBox="0 0 660 250">
      {[0, maximum / 2, maximum].map((tick) => { const tickY = y(tick); return <g aria-hidden="true" key={tick}><line className="debt-grid-line" x1={plot.left} x2={plot.right} y1={tickY} y2={tickY} /><text className="debt-axis-label" textAnchor="end" x={plot.left - 7} y={tickY + 4}>{Math.round(tick)}</text></g>; })}
      <text className="debt-axis-unit" x={plot.left} y="18">{surface("Amount · CNY 10k", "金额 · 万元")}</text>
      <text className="debt-derived-summary" textAnchor="end" x={plot.right} y="18">{surface(`Next-12-month coverage ${aggregateCoverage}%`, `未来12月覆盖率 ${aggregateCoverage}%`)}</text>
      {rows.map((row, index) => {
        const evidenceId = row.due.evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(row.due.evidenceRefs, row.due.id, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, row.due.id, row.due.evidenceRefs);
        const barY = y(row.due.value);
        return <g aria-label={surface(`${canonicalLabel(row.label)} debt due ${row.due.value} CNY 10k · ${evidenceText(reference)}`, `${row.label}到期负债${row.due.value}万元，${evidenceText(reference)}`)} aria-pressed={selected} className={`debt-chart-item debt-due-bar state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="debt-due-bar" data-target-id={row.due.id} key={row.due.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{canonicalLabel(row.label)} · {surface("debt due", "到期负债")} · {row.due.value} {surface("CNY 10k", "万元")} · {evidenceText(reference)}</title><rect height={plot.bottom - barY} rx="2" width="18" x={centers[index] - 9} y={barY} /></g>;
      })}
      <polyline aria-hidden="true" className="debt-capacity-line" points={points.map((point) => `${point.x},${point.y}`).join(" ")} />
      {points.map(({ row, x, y: pointY }, index) => {
        const evidenceId = row.capacity.evidenceRefs[0];
        const reference = evidenceById.get(evidenceId);
        const selected = isSelected(row.capacity.evidenceRefs, row.capacity.id, selectedTarget);
        const action = () => evidenceId && onEvidenceSelect(evidenceId, row.capacity.id, row.capacity.evidenceRefs);
        return <g aria-label={surface(`${canonicalLabel(row.label)} repayment capacity ${row.capacity.value} CNY 10k; coverage versus debt due ${row.coverage}%, deterministically derived · ${evidenceText(reference)}`, `${row.label}可偿还能力${row.capacity.value}万元，与到期负债比较覆盖率${row.coverage}%，确定性派生，${evidenceText(reference)}`)} aria-pressed={selected} className={`debt-chart-item debt-capacity-point state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-chart-kind="debt-capacity-point" data-target-id={row.capacity.id} key={row.capacity.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{canonicalLabel(row.label)} · {surface("repayment capacity", "可偿还能力")} · {row.capacity.value} {surface("CNY 10k", "万元")} · {surface("coverage", "覆盖率")} {row.coverage}% · {evidenceText(reference)}</title><circle cx={x} cy={pointY} r="4.5" />{index % 2 === 0 || index === rows.length - 1 ? <text className="debt-period-label" textAnchor="middle" x={x} y="238">{canonicalLabel(row.label)}</text> : null}</g>;
      })}
    </svg>
  );
}

export function DebtCoreCharts({ detail, evidence, selectedTarget, onEvidenceSelect }: { detail: DimensionDetail; evidence: EvidenceReference[]; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: EvidenceSelect }) {
  const locale = usePublicLocale();
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const compositions = new Map((detail.compositions ?? []).map((composition) => [composition.id, composition]));
  const enterprise = compositions.get("debt-enterprise-creditors");
  const personal = compositions.get("debt-personal-creditors");
  const projectExposure = compositions.get("debt-project-exposure");
  const metrics = new Map(detail.metrics.map((metric) => [metric.id, metric]));
  const historyRows: DebtHistoryRow[] = detail.series.flatMap((point) => {
    const enterpriseMeasure = point.measures.find((measure) => measure.label === "企业负债");
    const personalMeasure = point.measures.find((measure) => measure.label === "个人负债");
    return enterpriseMeasure && personalMeasure ? [{ id: point.id, label: point.label, enterprise: enterpriseMeasure, personal: personalMeasure }] : [];
  });
  const repaymentGroup = detail.seriesGroups?.find((group) => group.id === "debt-repayment");
  const repaymentRows: DebtRepaymentRow[] = (repaymentGroup?.points ?? []).flatMap((point) => {
    const due = point.measures.find((measure) => measure.label === "到期负债");
    const capacity = point.measures.find((measure) => measure.label === "可偿还能力");
    return due && capacity ? [{ id: point.id, label: point.label, due, capacity, coverage: rounded(capacity.value / Math.max(due.value, 1) * 100) }] : [];
  });
  const compositionTotal = (composition: DimensionComposition | undefined) => composition?.segments.reduce((sum, segment) => sum + segment.value, 0) ?? 0;
  return (
    <div aria-label={copy(locale, "Core debt charts", "负债核心图表")} className="debt-core-grid" data-semantic-localized>
      <section aria-labelledby="debt-exposure-title" className="debt-core-panel debt-panel-exposure"><header><div><strong id="debt-exposure-title">{copy(locale, "Project channel exposure", "项目通道敞口")}</strong><small>{copy(locale, "Center: historical outstanding exposure; outer ring: formal product-channel allocation.", "圆心为历史存量，外圈为正式产品通道分配")}</small></div><span>W</span></header><DebtProjectExposure composition={projectExposure} evidenceById={evidenceById} metrics={metrics} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} /></section>
      <section aria-labelledby="debt-enterprise-title" className="debt-core-panel debt-panel-enterprise"><header><div><strong id="debt-enterprise-title">{copy(locale, "Enterprise debt", "企业负债")}</strong><small>{copy(locale, "Creditor categories and shares are labeled directly.", "债权人类别与占比直接标注")}</small></div><span>{compositionTotal(enterprise).toLocaleString()} {copy(locale, "CNY 10k", "万元")}</span></header><DebtSubjectPie composition={enterprise} evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} /></section>
      <section aria-labelledby="debt-personal-title" className="debt-core-panel debt-panel-personal"><header><div><strong id="debt-personal-title">{copy(locale, "Personal debt", "个人负债")}</strong><small>{copy(locale, "Controller, spouse, shareholder, legal representative, and relatives.", "实控人、配偶、股东、法代与亲属")}</small></div><span>{compositionTotal(personal).toLocaleString()} {copy(locale, "CNY 10k", "万元")}</span></header><DebtSubjectPie composition={personal} evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} /></section>
      <section aria-labelledby="debt-trend-title" className="debt-core-panel debt-panel-trend"><header><div><strong id="debt-trend-title">{copy(locale, "Debt trend", "负债趋势")}</strong><small>{copy(locale, "Enterprise + personal debt are stacked; total debt is derived on the same axis.", "企业 + 个人堆叠，总负债同轴派生")}</small></div><span>{copy(locale, "CNY 10k", "万元")}</span></header><div aria-label={copy(locale, "Debt-trend legend", "负债趋势图例")} className="debt-core-legend"><span><i className="is-enterprise" />{copy(locale, "Enterprise debt", "企业负债")}</span><span><i className="is-personal" />{copy(locale, "Personal debt", "个人负债")}</span><span><i className="is-total" />{copy(locale, "Total debt", "总负债")}</span></div><DebtTrendChart evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} rows={historyRows} selectedTarget={selectedTarget} /></section>
      <section aria-labelledby="debt-repayment-title" className="debt-core-panel debt-panel-repayment"><header><div><strong id="debt-repayment-title">{copy(locale, "Repayment capacity", "偿债能力")}</strong><small>{copy(locale, "Next-12-month debt-due bars + repayment-capacity line.", "未来12月到期负债柱 + 可偿还能力折线")}</small></div><span>{copy(locale, "CNY 10k", "万元")}</span></header><div aria-label={copy(locale, "Repayment-capacity legend", "偿债能力图例")} className="debt-core-legend"><span><i className="is-due" />{copy(locale, "Debt due", "到期负债")}</span><span><i className="is-capacity" />{copy(locale, "Repayment capacity", "可偿还能力")}</span></div><DebtRepaymentChart evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} rows={repaymentRows} selectedTarget={selectedTarget} /></section>
    </div>
  );
}

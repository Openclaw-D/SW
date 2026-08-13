import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { DimensionDefinition, DimensionDetail, DimensionId, DimensionSeriesGroup, DimensionSeriesRequest, DimensionSeriesResponse, DimensionViewMode, EvidenceReference, FinancedEquipmentLedger, Material, OnsiteAsset, OperatingEquipmentStatus, ProductionEnergySeries, ProductionStage, PublicReferenceImage, ReviewEvidenceTarget, TimeGrain } from "../contracts/workbench";
import { displayBusinessText, scoreToGrade } from "../lib/workbenchLogic";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatDimensionName, formatEvidenceLocator, formatUnit, usePublicLocale } from "../lib/publicLocale";
import { CashflowCoreCharts } from "./CashflowCoreCharts";
import { DebtCoreCharts } from "./DebtCoreCharts";
import { dimensionColorVar, Icon } from "./icons";
import { ProductionEnergyChart } from "./ProductionEnergyChart";
import { ProductionOnsitePanel } from "./ProductionOnsitePanel";
import { ProductionPayrollChart } from "./ProductionPayrollChart";
import { ProductionStagesPanel } from "./ProductionStagesPanel";
import { RevenueCoreCharts } from "./RevenueCoreCharts";
import { TransactionWorkspace } from "./TransactionWorkspace";
import { TimeSeriesControls } from "./TimeSeriesControls";
import { Tag } from "./ui";

function cssVars(values: Record<string, string | number>) {
  return values as CSSProperties;
}

function evidenceText(reference: EvidenceReference | undefined, locale: ReturnType<typeof usePublicLocale>) {
  if (!reference) return copy(locale, "No evidence reference", "无引用");
  return formatEvidenceLocator(reference.locator, reference.locationStatus, locale);
}

function EvidenceMark({ reference }: { reference: EvidenceReference | undefined }) {
  const locale = usePublicLocale();
  return <small className={`plane-evidence state-${reference?.locationStatus ?? "missing"}`}><Icon name="link" />{evidenceText(reference, locale)}</small>;
}

const chartColors = ["#111111", "#30343b", "#59606a", "#a6abb2"];

const timeSeriesConfigs: Partial<Record<DimensionId, { metricIds: string[]; supportedGrains: TimeGrain[] }>> = {
  production: { metricIds: ["electricity", "output", "payroll", "staff", "utilization"], supportedGrains: ["day", "week", "month", "year"] },
  revenue: { metricIds: ["orders", "invoices", "collections", "income"], supportedGrains: ["day", "week", "month", "year"] },
  debt: { metricIds: ["enterprise", "personal", "due", "capacity"], supportedGrains: ["month", "year"] },
  cashflow: { metricIds: ["inflow", "outflow", "net"], supportedGrains: ["day", "week", "month", "year"] },
};

function LineSeriesChart({ detail, evidenceById, selectedEvidenceId, selectedTargetId, onEvidenceSelect }: { detail: DimensionDetail; evidenceById: Map<string, EvidenceReference>; selectedEvidenceId: string | null; selectedTargetId: string | null; onEvidenceSelect: (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void }) {
  const locale = usePublicLocale();
  const values = detail.series.flatMap((point) => point.measures.map((measure) => measure.value));
  const maximum = Math.max(...values, 1);
  const minimum = Math.min(...values, 0);
  const span = Math.max(maximum - minimum, 1);
  const measureCount = Math.max(...detail.series.map((point) => point.measures.length), 0);
  if (!detail.series.length || measureCount === 0) return <div className="inline-empty"><strong>{copy(locale, "No trend data", "暂无趋势")}</strong><span>{copy(locale, "This dimension has no time series that can be plotted.", "当前栏目没有可绘制时序。")}</span></div>;
  const position = (pointIndex: number, value: number) => ({
    x: detail.series.length === 1 ? 50 : 8 + pointIndex / (detail.series.length - 1) * 84,
    y: 54 - (value - minimum) / span * 44,
  });
  return (
    <div className={`semantic-line-chart visual-${detail.visual}`} aria-label={copy(locale, `${formatDimensionName(detail.dimensionId, locale)} trend chart`, `${formatDimensionName(detail.dimensionId, locale)}趋势图`)} data-semantic-localized>
      <div className="line-chart-canvas">
        <svg aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 100 60">
          {[...Array(measureCount)].map((_, measureIndex) => {
            const points = detail.series.flatMap((point, pointIndex) => { const measure = point.measures[measureIndex]; if (!measure) return []; const { x, y } = position(pointIndex, measure.value); return [`${x},${y}`]; }).join(" ");
            return <polyline fill="none" key={`line-${measureIndex}`} points={points} stroke={chartColors[measureIndex % chartColors.length]} strokeWidth="1.7" vectorEffect="non-scaling-stroke" />;
          })}
        </svg>
        {detail.series.flatMap((point, pointIndex) => point.measures.map((measure, measureIndex) => {
          const evidenceId = measure.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          const { x, y } = position(pointIndex, measure.value);
          return <button aria-label={`${formatCanonicalLabel(point.label, locale)} ${formatCanonicalLabel(measure.label, locale)} ${measure.value.toLocaleString()} ${formatUnit(measure.unit, locale)} · ${evidenceText(reference, locale)}`} className={`line-chart-point state-${reference?.locationStatus ?? "missing"} ${measure.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === measure.id ? "is-selected" : ""}`} id={`fact-${measure.id}`} key={measure.id} onClick={() => evidenceId && onEvidenceSelect(evidenceId, measure.id, measure.evidenceRefs)} style={cssVars({ "--point-color": chartColors[measureIndex % chartColors.length], "--point-x": `${x}%`, "--point-y": `${y / 60 * 100}%` })} type="button"><span>{measure.value.toLocaleString()}</span></button>;
        }))}
      </div>
      <div className="line-chart-axis">{detail.series.map((point) => <span key={point.id}>{formatCanonicalLabel(point.label, locale)}</span>)}</div>
      <div className="semantic-chart-legend" aria-label={copy(locale, "Chart legend", "图表图例")}>{detail.series[0].measures.map((measure, index) => <span key={measure.id}><i style={cssVars({ "--legend-color": chartColors[index % chartColors.length] })} />{formatCanonicalLabel(measure.label, locale)} · {formatUnit(measure.unit, locale)}</span>)}</div>
    </div>
  );
}

function DonutChart({ items, evidenceById, selectedEvidenceId, selectedTargetId, onEvidenceSelect, label }: { items: Array<{ id: string; label: string; value: number; evidenceRefs: string[] }>; evidenceById: Map<string, EvidenceReference>; selectedEvidenceId: string | null; selectedTargetId: string | null; onEvidenceSelect: (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void; label: string }) {
  const locale = usePublicLocale();
  const positive = items.filter((item) => item.value > 0);
  const total = positive.reduce((sum, item) => sum + item.value, 0);
  let offset = 0;
  if (!total) return <div className="inline-empty"><strong>{copy(locale, "No composition data", "暂无构成")}</strong><span>{copy(locale, "The available values are insufficient to plot this composition.", "当前数值不足以绘制构成图。")}</span></div>;
  return (
    <div className="donut-chart" aria-label={formatCanonicalLabel(label, locale)} data-semantic-localized>
      <svg viewBox="0 0 100 100">
        <circle className="donut-track" cx="50" cy="50" fill="none" pathLength="100" r="34" strokeWidth="16" />
        {positive.map((item, index) => {
          const percentage = item.value / total * 100;
          const currentOffset = offset;
          offset += percentage;
          const evidenceId = item.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          return <circle aria-label={`${formatCanonicalLabel(item.label, locale)} ${percentage.toFixed(1)}% · ${evidenceText(reference, locale)}`} className={`donut-segment ${item.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === item.id ? "is-selected" : ""}`} cx="50" cy="50" fill="none" key={item.id} onClick={() => evidenceId && onEvidenceSelect(evidenceId, item.id, item.evidenceRefs)} onKeyDown={(event) => { if ((event.key === "Enter" || event.key === " ") && evidenceId) onEvidenceSelect(evidenceId, item.id, item.evidenceRefs); }} pathLength="100" r="34" role="button" stroke={chartColors[index % chartColors.length]} strokeDasharray={`${percentage} ${100 - percentage}`} strokeDashoffset={-currentOffset} strokeWidth="16" tabIndex={0}><title>{formatCanonicalLabel(item.label, locale)} · {item.value.toLocaleString()}</title></circle>;
        })}
        <text className="donut-total" textAnchor="middle" x="50" y="49">{total.toLocaleString()}</text><text className="donut-unit" textAnchor="middle" x="50" y="60">{copy(locale, "Total", "合计")}</text>
      </svg>
      <div className="donut-legend" aria-label={copy(locale, "Chart legend", "图表图例")}>{positive.map((item, index) => { const evidenceId = item.evidenceRefs[0]; const reference = evidenceById.get(evidenceId); return <button className={item.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === item.id ? "is-selected" : ""} key={item.id} onClick={() => evidenceId && onEvidenceSelect(evidenceId, item.id, item.evidenceRefs)} type="button"><i style={cssVars({ "--legend-color": chartColors[index % chartColors.length] })} /><span>{formatCanonicalLabel(item.label, locale)}<small>{evidenceText(reference, locale)}</small></span><strong>{(item.value / total * 100).toFixed(1)}%</strong></button>; })}</div>
    </div>
  );
}

function BarComparison({ items, evidenceById, selectedEvidenceId, selectedTargetId, onEvidenceSelect }: { items: Array<{ id: string; label: string; value: number; evidenceRefs: string[] }>; evidenceById: Map<string, EvidenceReference>; selectedEvidenceId: string | null; selectedTargetId: string | null; onEvidenceSelect: (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void }) {
  const locale = usePublicLocale();
  const maximum = Math.max(...items.map((item) => item.value), 1);
  return <div className="comparison-bars" aria-label={copy(locale, "Amount comparison", "金额对比")} data-semantic-localized>{items.map((item) => { const evidenceId = item.evidenceRefs[0]; const reference = evidenceById.get(evidenceId); return <button className={item.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === item.id ? "is-selected" : ""} key={item.id} onClick={() => evidenceId && onEvidenceSelect(evidenceId, item.id, item.evidenceRefs)} type="button"><span><b>{formatCanonicalLabel(item.label, locale)}</b><small>{evidenceText(reference, locale)}</small></span><i><span style={cssVars({ "--comparison-width": `${item.value / maximum * 100}%` })} /></i><strong>{item.value.toLocaleString()}</strong></button>; })}</div>;
}

function RevenueSourceChain({ detail, evidenceById, selectedEvidenceId, selectedTargetId, onEvidenceSelect }: { detail: DimensionDetail; evidenceById: Map<string, EvidenceReference>; selectedEvidenceId: string | null; selectedTargetId: string | null; onEvidenceSelect: (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void }) {
  const locale = usePublicLocale();
  const latest = detail.series.at(-1);
  if (!latest) return null;
  return <section className="revenue-source-chain" data-semantic-localized><header><strong>{copy(locale, "Revenue source chain", "营收来源链")} · {formatCanonicalLabel(latest.label, locale)}</strong><small>{formatCanonicalNarrative(displayBusinessText(latest.note ?? ""), locale)}</small></header><div className="source-chain-nodes">{latest.measures.map((measure) => { const evidenceId = measure.evidenceRefs[0]; const reference = evidenceById.get(evidenceId); return <span className="source-chain-unit" key={measure.id}><button className={measure.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === measure.id ? "is-selected" : ""} onClick={() => evidenceId && onEvidenceSelect(evidenceId, measure.id, measure.evidenceRefs)} type="button"><b>{formatCanonicalLabel(measure.label, locale)}</b><strong>{measure.value.toLocaleString()} {formatUnit(measure.unit, locale)}</strong><small><Icon name="link" />{evidenceText(reference, locale)}</small></button></span>; })}</div><div className="source-chain-differences" aria-label={copy(locale, "Differences between revenue aggregation bases", "营收汇总口径差异")}>{latest.measures.slice(1).map((measure, index) => { const previous = latest.measures[index]; const difference = measure.value - previous.value; const evidenceRefs = measure.comparisonEvidenceRefs?.length ? measure.comparisonEvidenceRefs : [...new Set([...previous.evidenceRefs, ...measure.evidenceRefs])]; const evidenceId = evidenceRefs[0]; const reference = evidenceById.get(evidenceId ?? ""); const targetId = `${measure.id}-difference`; return <button className={evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === targetId ? "is-selected" : ""} key={targetId} onClick={() => evidenceId && onEvidenceSelect(evidenceId, targetId, evidenceRefs)} type="button"><span>{formatCanonicalLabel(previous.label, locale)} → {formatCanonicalLabel(measure.label, locale)}</span><strong>{difference >= 0 ? "+" : ""}{difference.toLocaleString()} {formatUnit(measure.unit, locale)}</strong><small><Icon name="link" />{evidenceText(reference, locale)}</small></button>; })}</div><footer>{copy(locale, `Basis: ${formatCanonicalNarrative(displayBusinessText(latest.note ?? ""), locale)} · Every node and aggregate difference is linked to a source cell; a difference is not a conversion rate for the same transaction cohort.`, `口径：${displayBusinessText(latest.note ?? "")} · 节点与汇总差异均绑定来源单元格；差异不等同同批业务转化率`)}</footer></section>;
}

function StructurePlane({ detail, evidenceById, selectedEvidenceId, selectedTargetId, onEvidenceSelect }: { detail: DimensionDetail; evidenceById: Map<string, EvidenceReference>; selectedEvidenceId: string | null; selectedTargetId: string | null; onEvidenceSelect: (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void }) {
  const locale = usePublicLocale();
  const isTransaction = detail.visual === "transaction-structure";
  const transactionItems = detail.series.slice(0, 2).flatMap((point) => point.measures.slice(0, 1).map((measure) => ({ id: measure.id, label: measure.label, value: measure.value, evidenceRefs: measure.evidenceRefs })));
  const comparisonItems = detail.series.slice(2).flatMap((point) => point.measures.slice(0, 1).map((measure) => ({ id: measure.id, label: measure.label, value: measure.value, evidenceRefs: measure.evidenceRefs })));
  const debtItems = detail.breakdown.flatMap((item) => { const value = Number(item.value.replaceAll(",", "").match(/-?\d+(?:\.\d+)?/)?.[0] ?? 0); return value > 0 ? [{ id: item.id, label: item.label, value, evidenceRefs: item.evidenceRefs }] : []; });
  return (
    <div className={`structure-plane ${isTransaction ? "is-transaction" : "is-debt"}`}>
      {isTransaction ? <div className="structure-flow" aria-label={copy(locale, "Transaction relationships and funding structure", "交易关系与资金结构")}>
        {detail.breakdown.map((item, index) => {
          const evidenceId = item.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          return (
            <div className="flow-unit" key={item.id}>
              <button aria-label={`${formatCanonicalLabel(item.label, locale)} · ${evidenceText(reference, locale)}`} className={`structure-node tone-${item.tone} state-${reference?.locationStatus ?? "missing"} ${item.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === item.id ? "is-selected" : ""}`} id={`fact-${item.id}`} onClick={() => evidenceId && onEvidenceSelect(evidenceId, item.id, item.evidenceRefs)} type="button">
                <span>{formatCanonicalLabel(item.label, locale)}</span><strong>{formatCanonicalNarrative(item.value, locale)}</strong><small>{formatCanonicalNarrative(item.detail, locale)}</small><EvidenceMark reference={reference} />
              </button>
              {index < detail.breakdown.length - 1 ? <span aria-hidden="true" className="flow-arrow">→</span> : null}
            </div>
          );
        })}
      </div> : null}
      <div className="structure-charts">
        <DonutChart evidenceById={evidenceById} items={isTransaction ? transactionItems : debtItems} label={isTransaction ? "交易融资构成" : "负债结构"} onEvidenceSelect={onEvidenceSelect} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} />
        {isTransaction ? <BarComparison evidenceById={evidenceById} items={comparisonItems} onEvidenceSelect={onEvidenceSelect} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} /> : <LineSeriesChart detail={detail} evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} />}
      </div>
    </div>
  );
}

function TrendPlane({ detail, evidenceById, selectedEvidenceId, selectedTargetId, onEvidenceSelect }: { detail: DimensionDetail; evidenceById: Map<string, EvidenceReference>; selectedEvidenceId: string | null; selectedTargetId: string | null; onEvidenceSelect: (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void }) {
  return (
    <div className={`trend-plane ${detail.visual === "cashflow-series" ? "is-cashflow" : ""}`}>
      <LineSeriesChart detail={detail} evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} />
    </div>
  );
}

function PlanarVisual({ detail, evidence, selectedEvidenceId, selectedTargetId, onEvidenceSelect }: { detail: DimensionDetail; evidence: EvidenceReference[]; selectedEvidenceId: string | null; selectedTargetId: string | null; onEvidenceSelect: (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void }) {
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  if (detail.visual === "transaction-structure" || detail.visual === "debt-structure") return <StructurePlane detail={detail} evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} />;
  if (detail.visual === "production-series") return null;
  return <TrendPlane detail={detail} evidenceById={evidenceById} onEvidenceSelect={onEvidenceSelect} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} />;
}

function ViewSwitch({ value, available, onChange }: { value: DimensionViewMode; available: DimensionViewMode[]; onChange: (value: DimensionViewMode) => void }) {
  const locale = usePublicLocale();
  return <div className="view-switch" aria-label={copy(locale, "Switch between visual and table views", "切换平面或表格视图")} role="group">{available.map((mode) => <button aria-pressed={value === mode} className={value === mode ? "is-active" : ""} key={mode} onClick={() => onChange(mode)} type="button">{mode === "visual" ? copy(locale, "Visual", "平面") : copy(locale, "Table", "表格")}</button>)}</div>;
}

export function ReviewSectionSummary({ sectionId, title, summary, expanded, controls, headingAriaHidden, headingId, onToggle }: { sectionId: string; title: string; summary: string; expanded: boolean; controls?: ReactNode; headingAriaHidden?: boolean; headingId?: string; onToggle: () => void }) {
  const locale = usePublicLocale();
  const bodyId = `review-section-body-${sectionId}`;
  const localizedTitle = formatCanonicalLabel(title, locale);
  const actionLabel = copy(locale, `${expanded ? "Collapse" : "Expand"} ${localizedTitle} details`, expanded ? `向上收起${title}明细` : `向下展开${title}明细`);
  return (
    <header className="section-header review-section-summary">
      <div className="review-section-summary-main">
        {headingAriaHidden ? <strong aria-hidden="true" className="review-section-visible-title">{localizedTitle}</strong> : <h1 id={headingId}>{localizedTitle}</h1>}
        <p>{formatCanonicalNarrative(summary, locale)}</p>
      </div>
      <div className="section-badges">
        {controls}
        <button aria-controls={bodyId} aria-expanded={expanded} aria-label={actionLabel} className={`section-fold-toggle direction-${expanded ? "up" : "down"}`} data-review-section-toggle={sectionId} onClick={onToggle} title={actionLabel} type="button"><Icon name="chevron" /></button>
      </div>
    </header>
  );
}

function TemporalDetailTable({ points, evidenceById, selectedEvidenceId, selectedTargetId, groupedMeasureLabels = [], onEvidenceSelect }: {
  points: Extract<DimensionSeriesResponse, { status: "available" }>["points"];
  evidenceById: Map<string, EvidenceReference>;
  selectedEvidenceId: string | null;
  selectedTargetId: string | null;
  groupedMeasureLabels?: string[];
  onEvidenceSelect: (evidenceId: string, targetId: string, evidenceRefs?: string[]) => void;
}) {
  const locale = usePublicLocale();
  const rows = [...points].sort((left, right) => right.periodStart.localeCompare(left.periodStart));
  return <div aria-label={copy(locale, "Time-series detail, latest period first", "时序明细，最新时段在前")} className="time-series-detail-table" data-semantic-localized role="table"><div className="time-series-detail-head" role="row"><span role="columnheader">{copy(locale, "Period", "时段")}</span><span role="columnheader">{copy(locale, "Metric", "指标")}</span><span role="columnheader">{copy(locale, "Value", "数值")}</span><span role="columnheader">{copy(locale, "Evidence", "证据")}</span></div>{rows.flatMap((point) => {
    const groupedMeasures = point.measures.filter((measure) => groupedMeasureLabels.includes(measure.label));
    const groupedEvidenceRefs = [...new Set(groupedMeasures.flatMap((measure) => measure.evidenceRefs))];
    const groupedTargetIds = new Set(groupedMeasures.map((measure) => measure.id));
    const groupedPeriodSelected = groupedTargetIds.has(selectedTargetId ?? "") && groupedEvidenceRefs.includes(selectedEvidenceId ?? "");
    return point.measures.map((measure) => {
      const evidenceId = measure.evidenceRefs[0];
      const reference = evidenceById.get(evidenceId);
      const selected = groupedMeasureLabels.includes(measure.label) ? groupedPeriodSelected : measure.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === measure.id;
      const selectionRefs = groupedMeasureLabels.includes(measure.label) ? [evidenceId, ...groupedEvidenceRefs.filter((item) => item !== evidenceId)] : measure.evidenceRefs;
      return <button aria-pressed={selected} className={`time-series-detail-row state-${reference?.locationStatus ?? "missing"} ${selected ? "is-selected" : ""}`} data-period-start={point.periodStart} data-target-id={measure.id} key={`${point.id}-${measure.id}`} onClick={() => evidenceId && onEvidenceSelect(evidenceId, measure.id, selectionRefs)} role="row" type="button"><span role="cell"><strong>{formatCanonicalLabel(point.label, locale)}</strong><small>{point.periodStart} — {point.periodEnd}</small></span><span role="cell">{formatCanonicalLabel(measure.label, locale)}</span><strong role="cell">{measure.value.toLocaleString()} {formatUnit(measure.unit, locale)}</strong><span role="cell"><Icon name="link" />{evidenceText(reference, locale)}</span></button>;
    });
  })}</div>;
}

export function DimensionDetailView({
  borrower,
  dimension,
  detail,
  financedEquipment,
  materials,
  onsiteAssets,
  operatingEquipment,
  productionEnergy,
  productionStages,
  referenceImages,
  selectedProductionStageId,
  evidence,
  selectedTarget,
  expanded,
  onEvidenceSelect,
  onProductionStageSelect,
  onTimeSeriesRequest,
  onToggleExpanded,
  projectId,
}: {
  borrower: string;
  dimension: DimensionDefinition;
  detail: DimensionDetail;
  financedEquipment?: FinancedEquipmentLedger;
  materials: Material[];
  onsiteAssets?: OnsiteAsset[];
  operatingEquipment?: OperatingEquipmentStatus[];
  productionEnergy?: ProductionEnergySeries;
  productionStages?: ProductionStage[];
  referenceImages: PublicReferenceImage[];
  selectedProductionStageId?: string;
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  expanded: boolean;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
  onProductionStageSelect?: (stageId: string, imageId: string) => void;
  onTimeSeriesRequest?: (request: DimensionSeriesRequest) => Promise<DimensionSeriesResponse>;
  onToggleExpanded: () => void;
  projectId: string;
}) {
  const locale = usePublicLocale();
  const [view, setView] = useState<DimensionViewMode>(detail.defaultView);
  const [timeSeriesResponse, setTimeSeriesResponse] = useState<DimensionSeriesResponse | null>(null);
  const [timeSeriesRequest, setTimeSeriesRequest] = useState<DimensionSeriesRequest | null>(null);
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const selectedEvidenceId = selectedTarget?.evidenceRef ?? null;
  const selectedTargetId = selectedTarget?.reviewTargetId ?? null;
  const selectEvidence = (evidenceRefs: string[], targetId: string, factVersionId: string | null = null) => { if (evidenceRefs[0]) onEvidenceSelect({ evidenceRef: evidenceRefs[0], evidenceRefs, dimensionId: dimension.id, reviewTargetId: targetId, factVersionId }); };
  const selectLegacyEvidence = (evidenceId: string, targetId: string, evidenceRefs: string[] = [evidenceId]) => selectEvidence(evidenceRefs, targetId);
  const temporalPoints = timeSeriesResponse?.status === "available" ? timeSeriesResponse.points : null;
  const effectiveDetail: DimensionDetail = temporalPoints ? {
    ...detail,
    series: temporalPoints,
    seriesGroups: dimension.id === "debt"
      ? [
          ...(detail.seriesGroups ?? []).filter((group) => group.id !== "debt-repayment"),
          { id: "debt-repayment", label: "所选时段偿债计划", points: temporalPoints },
        ]
      : detail.seriesGroups,
  } : detail;
  const productionTemporalSeries: ProductionEnergySeries | undefined = dimension.id === "production" && temporalPoints ? {
    status: "available",
    electricityMetric: "usage",
    electricityUnit: "kWh",
    outputMetric: "absolute",
    outputUnit: "件",
    aggregation: "sum",
    points: temporalPoints.flatMap((point) => {
      const electricity = point.measures.find((measure) => measure.label === "用电量");
      const output = point.measures.find((measure) => measure.label === "完工产量");
      return electricity && output ? [{ id: point.id, date: point.periodStart, label: point.label, electricity: electricity.value, output: output.value, electricityEvidenceRefs: electricity.evidenceRefs, outputEvidenceRefs: output.evidenceRefs, isSimulated: true as const }] : [];
    }),
    message: "统一时序接口返回的脱敏模拟聚合结果。",
    sourceLabel: timeSeriesResponse?.sourceLabel ?? "P3 脱敏模拟时序包",
    isSimulated: true,
  } : productionEnergy;
  const productionPayrollSeries: DimensionSeriesGroup | undefined = dimension.id === "production" && temporalPoints ? {
    id: "production-payroll",
    label: "所选时段人员工资",
    points: temporalPoints.flatMap((point) => {
      const amount = point.measures.find((measure) => measure.label === "工资总额");
      const staff = point.measures.find((measure) => measure.label === "在岗人数");
      if (!amount || !staff || staff.value <= 0) return [];
      return [{ ...point, measures: [amount, staff, { id: `${point.id}-per-capita`, label: "人均工资", value: amount.value / staff.value, unit: "万元/人", evidenceRefs: [...new Set([...amount.evidenceRefs, ...staff.evidenceRefs])] }] }];
    }),
  } : dimension.id === "production" && timeSeriesRequest ? undefined : detail.seriesGroups?.find((group) => group.id === "production-payroll");
  const timeConfig = timeSeriesConfigs[dimension.id];
  const timeControls = timeConfig && onTimeSeriesRequest ? <TimeSeriesControls dimensionId={dimension.id} metricIds={timeConfig.metricIds} onRequest={(request) => { setTimeSeriesRequest(request); setTimeSeriesResponse(null); }} onResponse={setTimeSeriesResponse} projectId={projectId} query={onTimeSeriesRequest} supportedGrains={timeConfig.supportedGrains} /> : null;
  return (
    <section className={`dimension-section dimension-detail-section ${expanded ? "is-section-expanded" : "is-section-collapsed"}`} data-dimension-id={dimension.id} data-semantic-localized id={`dimension-${dimension.id}`} style={cssVars({ "--dimension-color": dimensionColorVar[dimension.id] })}>
      <ReviewSectionSummary controls={<><Tag tone="neutral">{scoreToGrade(dimension.score)} · {dimension.score}{copy(locale, " points", "分")}</Tag><ViewSwitch available={detail.availableViews} onChange={setView} value={view} /></>} expanded={expanded} onToggle={onToggleExpanded} sectionId={dimension.id} summary={detail.conclusion} title={dimension.name} />
      <div className="review-section-body" hidden={!expanded} id={`review-section-body-${dimension.id}`}>
        {dimension.id === "transaction" ? <p className="project-data-boundary">{copy(locale, "Data boundary: this project uses de-identified simulation. Public reference images are supporting context only and do not represent a real customer or approval opinion.", "数据边界：本项目为脱敏模拟；公开参考图仅作辅助，不代表真实客户或审批意见。")}</p> : null}
        {dimension.id !== "production" ? timeControls : null}
        {view === "visual" ? <>
          {dimension.id === "transaction" && financedEquipment ? <TransactionWorkspace borrower={borrower} evidence={evidence} ledger={financedEquipment} materials={materials} onEvidenceSelect={onEvidenceSelect} referenceImages={referenceImages} selectedTarget={selectedTarget} /> : dimension.id === "production" && operatingEquipment && productionEnergy && productionStages && onProductionStageSelect ? <>
            <div className="production-dashboard">
              {onsiteAssets ? <ProductionOnsitePanel assets={onsiteAssets} evidence={evidence} materials={materials} onEvidenceSelect={onEvidenceSelect} operatingEquipment={operatingEquipment} selectedTarget={selectedTarget} /> : null}
              <ProductionStagesPanel evidence={evidence} materials={materials} onEvidenceSelect={onEvidenceSelect} onStageSelect={onProductionStageSelect} selectedTarget={selectedTarget} selectedStageId={selectedProductionStageId ?? productionStages[0]?.id ?? ""} stages={productionStages} />
              <div className="production-time-controls-sticky">{timeControls}</div>
              <ProductionPayrollChart evidence={evidence} grain={timeSeriesResponse?.request.grain ?? timeSeriesRequest?.grain ?? "month"} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} series={productionPayrollSeries} />
              <ProductionEnergyChart controlledByTimeSeries={!!temporalPoints} evidence={evidence} grain={timeSeriesResponse?.request.grain ?? timeSeriesRequest?.grain ?? "month"} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} series={productionTemporalSeries ?? productionEnergy} />
            </div>
          </> : dimension.id === "revenue" ? <div className="revenue-visual-workspace">
            <RevenueCoreCharts detail={effectiveDetail} evidence={evidence} onEvidenceSelect={selectLegacyEvidence} rentEvidenceRefs={financedEquipment?.repaymentSchedule.firstTwelveEvidenceRefs ?? []} selectedTarget={selectedTarget} />
            <RevenueSourceChain detail={effectiveDetail} evidenceById={evidenceById} onEvidenceSelect={selectLegacyEvidence} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} />
          </div> : dimension.id === "debt" ? <div className="debt-visual-workspace">
            <DebtCoreCharts detail={effectiveDetail} evidence={evidence} onEvidenceSelect={selectLegacyEvidence} selectedTarget={selectedTarget} />
          </div> : dimension.id === "cashflow" ? <div className="cashflow-visual-workspace">
            <CashflowCoreCharts detail={effectiveDetail} evidence={evidence} onEvidenceSelect={selectLegacyEvidence} selectedTarget={selectedTarget} />
            <aside aria-label={copy(locale, "Cash-flow key conclusions", "流水关键结论")} className="cashflow-key-conclusions"><header><strong>{copy(locale, "Key conclusions", "关键结论")}</strong><small>{copy(locale, "Preserves the established verification thread", "保留原有核验主线")}</small></header><div>{detail.breakdown.map((item) => { const reference = evidenceById.get(item.evidenceRefs[0]); return <button aria-label={`${formatCanonicalLabel(item.label, locale)} · ${evidenceText(reference, locale)}`} aria-pressed={item.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === item.id} className={`cashflow-conclusion-item tone-${item.tone} state-${reference?.locationStatus ?? "missing"} ${item.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === item.id ? "is-selected" : ""}`} data-target-id={item.id} id={`fact-${item.id}`} key={item.id} onClick={() => selectEvidence(item.evidenceRefs, item.id)} type="button"><span><strong>{formatCanonicalLabel(item.label, locale)}</strong><small>{formatCanonicalNarrative(item.detail, locale)}</small></span><b>{formatCanonicalNarrative(item.value, locale)}</b><EvidenceMark reference={reference} /></button>; })}</div></aside>
          </div> : <div className={`dimension-visual-grid dimension-information-board is-${dimension.id}`}>
            <div className="dimension-chart-panel"><header><div><Icon name={dimension.id} /><strong>{formatDimensionName(dimension.id, locale, dimension.name)} {copy(locale, "visual", "平面")}</strong></div><small>{formatUnit(detail.unit, locale)} · {copy(locale, "Select a node to locate its evidence", "点击节点定位")}</small></header><PlanarVisual detail={detail} evidence={evidence} onEvidenceSelect={selectLegacyEvidence} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} /></div>
            <aside className="dimension-breakdown dimension-insight-panel"><header><strong>{copy(locale, "Key conclusions", "关键结论")}</strong><small>{copy(locale, "Trace every item back to evidence", "逐项回到证据")}</small></header>{detail.breakdown.map((item) => { const reference = evidenceById.get(item.evidenceRefs[0]); return <button aria-label={`${formatCanonicalLabel(item.label, locale)} · ${evidenceText(reference, locale)}`} className={`breakdown-row tone-${item.tone} state-${reference?.locationStatus ?? "missing"} ${item.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === item.id ? "is-selected" : ""}`} id={`fact-${item.id}`} key={item.id} onClick={() => selectEvidence(item.evidenceRefs, item.id)} type="button"><span><span>{formatCanonicalLabel(item.label, locale)}</span><small>{formatCanonicalNarrative(item.detail, locale)}</small><EvidenceMark reference={reference} /></span><strong>{formatCanonicalNarrative(item.value, locale)}</strong></button>; })}</aside>
          </div>}
        </> : <>{temporalPoints ? <TemporalDetailTable evidenceById={evidenceById} groupedMeasureLabels={dimension.id === "production" ? ["工资总额", "在岗人数"] : []} onEvidenceSelect={selectLegacyEvidence} points={temporalPoints} selectedEvidenceId={selectedEvidenceId} selectedTargetId={selectedTargetId} /> : null}<div className="dimension-detail-table" role="table" aria-label={copy(locale, `${formatDimensionName(dimension.id, locale, dimension.name)} detail table`, `${dimension.name}明细表`)}><div className="detail-table-head" role="row"><span role="columnheader">{copy(locale, "Field", "字段")}</span><span role="columnheader">{copy(locale, "Result", "结果")}</span><span role="columnheader">{copy(locale, "Basis", "依据")}</span><span role="columnheader">{copy(locale, "Evidence", "证据")}</span></div>{detail.breakdown.map((item) => { const reference = evidenceById.get(item.evidenceRefs[0]); return <button className={`detail-table-row state-${reference?.locationStatus ?? "missing"} ${item.evidenceRefs.includes(selectedEvidenceId ?? "") && selectedTargetId === item.id ? "is-selected" : ""}`} id={`fact-${item.id}`} key={item.id} onClick={() => selectEvidence(item.evidenceRefs, item.id)} role="row" type="button"><strong role="cell">{formatCanonicalLabel(item.label, locale)}</strong><span role="cell">{formatCanonicalNarrative(item.value, locale)}</span><span role="cell">{formatCanonicalNarrative(item.detail, locale)}</span><span role="cell"><Icon name="link" />{evidenceText(reference, locale)}</span></button>; })}</div></>}
        <footer className="dimension-conclusion"><div><span>{copy(locale, "Conclusion", "结论")}</span><strong>{formatCanonicalNarrative(detail.conclusion, locale)}</strong></div><small>{formatCanonicalNarrative(detail.sourceLabel, locale)}</small></footer>
      </div>
    </section>
  );
}

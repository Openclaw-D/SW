import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type { EvidenceReference, ProductionEnergySeries, ReviewEvidenceTarget, TimeGrain } from "../contracts/workbench";
import { aggregateProductionEnergy, displayBusinessText, productionSeriesStatus, sameReviewEvidenceTarget, type ProductionGranularity } from "../lib/workbenchLogic";
import { productionEnergyEvidenceUnion, productionEnergyPlotGeometry, type ProductionEnergyDisplayGrain } from "../lib/productionEnergyGeometry";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatEvidenceLocator, formatUnit, usePublicLocale } from "../lib/publicLocale";
import { Icon } from "./icons";

function evidenceLocation(reference: EvidenceReference | undefined, locale: ReturnType<typeof usePublicLocale>) {
  if (!reference) return copy(locale, "No evidence reference", "无引用");
  return formatEvidenceLocator(reference.locator, reference.locationStatus, locale);
}

const grainLabels: Record<ProductionEnergyDisplayGrain, string> = { day: "日", week: "周", month: "月", quarter: "季", year: "年" };

export function ProductionEnergyChart({ series, evidence, selectedTarget, controlledByTimeSeries = false, grain = "month", onEvidenceSelect }: {
  series: ProductionEnergySeries;
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  controlledByTimeSeries?: boolean;
  grain?: TimeGrain;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const grainLabel = (value: ProductionEnergyDisplayGrain) => copy(locale, ({ day: "day", week: "week", month: "month", quarter: "quarter", year: "year" } as const)[value], grainLabels[value]);
  const [granularity, setGranularity] = useState<ProductionGranularity>("month");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [focusedPeriodId, setFocusedPeriodId] = useState<string | null>(null);
  const evidenceById = useMemo(() => new Map(evidence.map((item) => [item.id, item])), [evidence]);
  const contractState = productionSeriesStatus(series);
  const aggregation = useMemo(
    () => controlledByTimeSeries && contractState.status === "available"
      ? { status: "available" as const, points: series.points.map((point) => ({ ...point })) }
      : contractState.status === "available"
      ? aggregateProductionEnergy(series.points, granularity, startDate, endDate)
      : { status: contractState.status, message: contractState.message, points: [] as [] },
    [contractState.message, contractState.status, controlledByTimeSeries, endDate, granularity, series.points, startDate],
  );
  const maximumElectricity = aggregation.status === "available" ? Math.max(1, ...aggregation.points.map((point) => point.electricity)) : 1;
  const maximumOutput = aggregation.status === "available" ? Math.max(1, ...aggregation.points.map((point) => point.output)) : 1;
  const electricityAxisMax = Math.ceil(maximumElectricity / 5_000) * 5_000;
  const outputAxisMax = Math.ceil(maximumOutput / 2_000) * 2_000;
  const maximumElectricityEvidenceCount = aggregation.status === "available" ? Math.max(0, ...aggregation.points.map((point) => point.electricityEvidenceRefs.length)) : 0;
  const maximumOutputEvidenceCount = aggregation.status === "available" ? Math.max(0, ...aggregation.points.map((point) => point.outputEvidenceRefs.length)) : 0;
  const focusClass = (periodId: string) => focusedPeriodId ? focusedPeriodId === periodId ? "is-item-active" : "is-item-muted" : "";
  const focusProps = (periodId: string) => ({ onFocus: () => setFocusedPeriodId(periodId), onBlur: () => setFocusedPeriodId((current) => current === periodId ? null : current), onPointerEnter: () => setFocusedPeriodId(periodId), onPointerLeave: () => setFocusedPeriodId((current) => current === periodId ? null : current) });
  const targetFor = (evidenceRefs: string[], reviewTargetId: string): ReviewEvidenceTarget | null => evidenceRefs[0] ? ({ evidenceRef: evidenceRefs[0], evidenceRefs, dimensionId: "production", reviewTargetId, factVersionId: null }) : null;
  const pointCount = aggregation.status === "available" ? aggregation.points.length : 0;
  const activeGrain: ProductionEnergyDisplayGrain = controlledByTimeSeries ? grain : granularity;
  const plotGeometry = productionEnergyPlotGeometry(pointCount, activeGrain);
  const showsLabel = (index: number) => index % plotGeometry.labelEvery === 0 || index === pointCount - 1;
  const selectedEvidenceRefs = selectedTarget?.evidenceRefs?.length ? selectedTarget.evidenceRefs : selectedTarget ? [selectedTarget.evidenceRef] : [];
  return (
    <section className="production-energy-panel" aria-label={copy(locale, "Electricity usage and completed output chart", "用电量与完工产量图")} data-semantic-localized>
      <header>
        <div><Icon name="production" /><span><strong>{copy(locale, "Electricity usage / completed output", "用电量 / 完工产量")}</strong><small>{formatUnit(series.electricityUnit, locale)} {copy(locale, "and", "与")} {formatUnit(series.outputUnit, locale)} {copy(locale, `use separate axes; absolute values summed within each ${grainLabel(activeGrain)}.`, `分轴显示；${grainLabels[activeGrain]}内求和的绝对值`)}</small></span></div>
        {!controlledByTimeSeries ? <div className="production-time-controls">
          <div aria-label={copy(locale, "Time grain", "时间粒度")} role="group">
            {(["month", "quarter"] as const).map((value) => <button aria-pressed={granularity === value} className={granularity === value ? "is-active" : ""} key={value} onClick={() => setGranularity(value)} type="button">{grainLabel(value)}</button>)}
            <button aria-disabled="true" disabled title={copy(locale, "Only monthly materials are available; they cannot be reliably aggregated by week.", "当前只有月度材料，不能可靠聚合为周")} type="button">{copy(locale, "Week unavailable", "周不可用")}</button>
          </div>
          <label>{copy(locale, "Start", "起始")}<input aria-label={copy(locale, "Production-series start date", "生产序列起始日期")} onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} /></label>
          <label>{copy(locale, "End", "结束")}<input aria-label={copy(locale, "Production-series end date", "生产序列结束日期")} onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} /></label>
          <button onClick={() => { setStartDate(""); setEndDate(""); }} type="button">{copy(locale, "All", "全部")}</button>
        </div> : <span className="time-series-inline-status">{copy(locale, `Unified ${grainLabel(activeGrain)} periods · summed within each period`, `统一${grainLabels[activeGrain]}时段 · ${grainLabels[activeGrain]}内求和`)}</span>}
      </header>
      {aggregation.status === "available" ? <div className="production-energy-chart">
        <div className="production-axis is-electricity" aria-hidden="true">{[4, 3, 2, 1, 0].map((step) => <span key={step}>{Math.round(electricityAxisMax * step / 4).toLocaleString()}</span>)}</div>
        <div className="production-energy-scroll">
        <div className="production-chart-grid" role="list" aria-label={copy(locale, `Electricity usage and completed output at ${grainLabel(activeGrain)} grain`, `${grainLabels[activeGrain]}粒度用电量与完工产量`)} style={{ "--production-columns": Math.max(pointCount, 1), "--production-energy-min-width": `${plotGeometry.minimumPlotWidth}px`, "--production-energy-slot-width": `${plotGeometry.slotWidth}px` } as CSSProperties}>
          <div className="production-grid-lines" aria-hidden="true">{[0, 1, 2, 3, 4].map((line) => <i key={line} />)}</div>
          <svg aria-hidden="true" className="production-output-line" preserveAspectRatio="none" viewBox="0 0 100 100"><polyline points={aggregation.points.map((point, index) => `${plotGeometry.lineCenters[index]},${100 - point.output / outputAxisMax * 82}`).join(" ")} /></svg>
          {aggregation.points.map((point, index) => {
            const electricityEvidenceId = point.electricityEvidenceRefs[0];
            const outputEvidenceId = point.outputEvidenceRefs[0];
            const outputPosition = point.output / outputAxisMax * 82;
            const periodEvidenceRefs = productionEnergyEvidenceUnion(point.electricityEvidenceRefs, point.outputEvidenceRefs);
            const electricityTarget = targetFor(productionEnergyEvidenceUnion(point.electricityEvidenceRefs, point.outputEvidenceRefs), `${point.id}-electricity`);
            const outputTarget = targetFor(productionEnergyEvidenceUnion(point.outputEvidenceRefs, point.electricityEvidenceRefs), `${point.id}-output`);
            const exactTargetSelected = sameReviewEvidenceTarget(electricityTarget, selectedTarget) || sameReviewEvidenceTarget(outputTarget, selectedTarget);
            const periodSelected = exactTargetSelected || ([`${point.id}-electricity`, `${point.id}-output`].includes(selectedTarget?.reviewTargetId ?? "") && periodEvidenceRefs.some((evidenceRef) => selectedEvidenceRefs.includes(evidenceRef)));
            return <div className="production-chart-item" data-production-point-id={point.id} key={point.id} role="listitem" title={copy(locale, `${formatCanonicalLabel(point.label, locale)} · electricity ${point.electricity.toLocaleString()} ${formatUnit(series.electricityUnit, locale)} · output ${point.output.toLocaleString()} ${formatUnit(series.outputUnit, locale)} · ${point.electricityEvidenceRefs.length} electricity evidence refs · ${point.outputEvidenceRefs.length} output evidence refs`, `${point.label} · 用电 ${point.electricity.toLocaleString()} ${series.electricityUnit} · 产量 ${point.output.toLocaleString()} ${series.outputUnit} · 电表证据 ${point.electricityEvidenceRefs.length} 条 · 产量证据 ${point.outputEvidenceRefs.length} 条`)}>
              <div className="production-chart-plot">
                <button aria-label={copy(locale, `${formatCanonicalLabel(point.label, locale)} electricity usage ${point.electricity.toLocaleString()} ${formatUnit(series.electricityUnit, locale)}; selects completed output for the same period; ${evidenceLocation(evidenceById.get(electricityEvidenceId), locale)}`, `${point.label}用电量 ${point.electricity.toLocaleString()} ${series.electricityUnit}；同期完工产量共同选择；${evidenceLocation(evidenceById.get(electricityEvidenceId), locale)}`)} aria-pressed={periodSelected} className={`production-electricity-bar ${focusClass(point.id)} ${periodSelected ? "is-selected" : ""}`} data-period-id={point.id} id={`fact-${point.id}-electricity`} onClick={() => electricityTarget && onEvidenceSelect(electricityTarget)} style={{ "--bar-height": `${point.electricity / electricityAxisMax * 82}%` } as CSSProperties} title={copy(locale, `${point.electricity.toLocaleString()} ${formatUnit(series.electricityUnit, locale)} · ${periodEvidenceRefs.length} input evidence refs for this period`, `${point.electricity.toLocaleString()} ${series.electricityUnit} · 同周期共 ${periodEvidenceRefs.length} 条输入证据`)} type="button" {...focusProps(point.id)}>{showsLabel(index) ? <span>{point.electricity.toLocaleString()}</span> : null}</button>
                <button aria-label={copy(locale, `${formatCanonicalLabel(point.label, locale)} completed output ${point.output.toLocaleString()} ${formatUnit(series.outputUnit, locale)}; selects electricity usage for the same period; ${evidenceLocation(evidenceById.get(outputEvidenceId), locale)}`, `${point.label}完工产量 ${point.output.toLocaleString()} ${series.outputUnit}；同期用电量共同选择；${evidenceLocation(evidenceById.get(outputEvidenceId), locale)}`)} aria-pressed={periodSelected} className={`production-output-point ${focusClass(point.id)} ${periodSelected ? "is-selected" : ""}`} data-period-id={point.id} id={`fact-${point.id}-output`} onClick={() => outputTarget && onEvidenceSelect(outputTarget)} style={{ "--point-bottom": `${outputPosition}%` } as CSSProperties} title={copy(locale, `${point.output.toLocaleString()} ${formatUnit(series.outputUnit, locale)} · ${periodEvidenceRefs.length} input evidence refs for this period`, `${point.output.toLocaleString()} ${series.outputUnit} · 同周期共 ${periodEvidenceRefs.length} 条输入证据`)} type="button" {...focusProps(point.id)}><i />{showsLabel(index) ? <span>{point.output.toLocaleString()}</span> : null}</button>
              </div>
              <strong>{showsLabel(index) ? formatCanonicalLabel(point.label, locale) : ""}</strong>
            </div>;
          })}
        </div>
        </div>
        <div className="production-axis is-output" aria-hidden="true">{[4, 3, 2, 1, 0].map((step) => <span key={step}>{Math.round(outputAxisMax * step / 4).toLocaleString()}</span>)}</div>
      </div> : <div className={`production-chart-empty state-${aggregation.status}`}><strong>{aggregation.status === "empty" ? copy(locale, "No data in the selected range", "所选区间无数据") : aggregation.status === "missing" ? copy(locale, "Production series missing", "生产序列缺失") : aggregation.status === "invalid" ? copy(locale, "Production series invalid", "生产序列无效") : copy(locale, "Production series unavailable", "生产序列不可用")}</strong><span>{formatCanonicalNarrative(aggregation.message, locale)}</span></div>}
      <div className="production-chart-legend" aria-label={copy(locale, "Chart legend", "图表图例")}><span><i className="is-electricity" />{copy(locale, `Electricity usage (${formatUnit(series.electricityUnit, locale)}, left-axis bars)`, `用电量（${series.electricityUnit}，左轴柱）`)}</span><span><i className="is-output" />{copy(locale, `Completed output (${formatUnit(series.outputUnit, locale)}, right-axis points)`, `完工产量（${series.outputUnit}，右轴点）`)}</span><small>{formatCanonicalNarrative(displayBusinessText(series.sourceLabel), locale)}</small></div>
      {aggregation.status === "available" ? <p className="production-evidence-summary">{copy(locale, `The bar and point for each period are selected together and locate every input evidence reference. An aggregate point currently contains at most ${maximumElectricityEvidenceCount} electricity refs and ${maximumOutputEvidenceCount} output refs.`, `同周期柱与点共同选择并定位全部输入证据；当前聚合点最多包含电表 ${maximumElectricityEvidenceCount} 条、产量 ${maximumOutputEvidenceCount} 条。`)}</p> : null}
    </section>
  );
}

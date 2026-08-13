import type { CSSProperties, KeyboardEvent } from "react";
import type { EvidenceReference, FinancedEquipmentLedger, FinancedEquipmentLine, ReviewEvidenceTarget, TransactionRepaymentSchedule } from "../contracts/workbench";
import { analyzeRepaymentSchedule, formatFinancingRatio, repaymentChartLabelPeriods, sameReviewEvidenceTarget } from "../lib/workbenchLogic";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatEvidenceLocator, usePublicLocale, type PublicLocale } from "../lib/publicLocale";
import { Icon } from "./icons";

function evidenceLocation(reference: EvidenceReference | undefined, locale: PublicLocale) {
  if (!reference) return copy(locale, "Evidence not linked", "证据未关联");
  return formatEvidenceLocator(reference.locator, reference.locationStatus, locale);
}

function targetFor(evidenceRefs: string[] | undefined, reviewTargetId: string): ReviewEvidenceTarget | null {
  return evidenceRefs?.[0] ? { evidenceRef: evidenceRefs[0], evidenceRefs, dimensionId: "transaction", reviewTargetId, factVersionId: null } : null;
}

function activateWithKeyboard(event: KeyboardEvent<SVGGElement>, action: () => void) {
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  action();
}

function tenThousands(value: number, locale: PublicLocale, digits = 2) {
  return `${(value / 10_000).toFixed(digits)} ${copy(locale, "CNY 10k", "万元")}`;
}

export function TransactionCoreParameters({ ledger, current, evidence, selectedTarget, onEvidenceSelect }: {
  ledger: FinancedEquipmentLedger;
  current: FinancedEquipmentLine;
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const contractTotal = ledger.lines.reduce((sum, line) => sum + line.quantity * line.contractUnitPrice, 0);
  const financedAmount = contractTotal - ledger.downPaymentAmount;
  const financingRatio = contractTotal > 0 ? financedAmount / contractTotal * 100 : null;
  const items = [
    { id: `transaction-core-supplier-rating-${current.id}`, label: "供应商评级", value: current.supplierRating ?? "待核验", context: current.supplier, evidenceRefs: current.supplierRatingEvidenceRefs, available: !!current.supplierRating },
    { id: `transaction-core-brand-rating-${current.id}`, label: "品牌评级", value: current.brandRating ?? "待核验", context: current.brand, evidenceRefs: current.brandRatingEvidenceRefs, available: !!current.brandRating },
    { id: "transaction-core-project-amount", label: "项目金额", value: tenThousands(contractTotal, locale, 1), context: "合同设备合计", evidenceRefs: ledger.projectAmountEvidenceRefs, available: contractTotal > 0 },
    { id: "transaction-core-financing-ratio", label: "融资成数", value: formatFinancingRatio(financingRatio), context: "融资额 / 合同总额", evidenceRefs: ledger.financingRatioEvidenceRefs, available: financingRatio !== null },
  ];
  return (
    <section aria-label={copy(locale, "Core transaction parameters", "交易核心参数")} className="transaction-core-parameters" data-semantic-localized>
      <header><div><Icon name="transaction" /><span><strong>{copy(locale, "Core transaction parameters", "交易核心参数")}</strong><small>{copy(locale, "Ratings follow the selected equipment; amount and financing ratio use the project-level basis.", "评级随当前设备切换；金额与融资成数使用项目口径")}</small></span></div><b>{formatCanonicalNarrative(current.brand, locale)} · {formatCanonicalNarrative(current.model, locale)}</b></header>
      <div>
        {items.map((item) => {
          const target = targetFor(item.evidenceRefs, item.id);
          const reference = evidenceById.get(item.evidenceRefs?.[0] ?? "");
          const selected = sameReviewEvidenceTarget(target, selectedTarget);
          return <button aria-disabled={!target} aria-label={`${formatCanonicalLabel(item.label, locale)} ${formatCanonicalNarrative(item.value, locale)} · ${formatCanonicalNarrative(item.context, locale)} · ${target ? evidenceLocation(reference, locale) : copy(locale, "Awaiting verification", "待核验")}`} aria-pressed={selected} className={`${item.available ? "is-available" : "is-pending"} ${selected ? "is-selected" : ""}`} data-target-id={item.id} disabled={!target} key={item.id} onClick={() => target && onEvidenceSelect(target)} type="button"><span>{formatCanonicalLabel(item.label, locale)}</span><strong>{formatCanonicalNarrative(item.value, locale)}</strong><small>{formatCanonicalNarrative(item.context, locale)}</small><em><Icon name="link" />{target ? evidenceLocation(reference, locale) : copy(locale, "Awaiting verification", "待核验")}</em></button>;
        })}
      </div>
    </section>
  );
}

export function TransactionRepaymentChart({ schedule, evidence, selectedTarget, onEvidenceSelect }: {
  schedule: TransactionRepaymentSchedule;
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const analysis = analyzeRepaymentSchedule(schedule);
  const state = analysis.status;
  const scheduleTitle = copy(locale, `${schedule.termMonths}-period rent schedule`, `${schedule.termMonths}期租金计划`);
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  if (state !== "available") {
    const title = state === "missing" ? copy(locale, "Rent schedule pending", "租金计划待补") : state === "invalid" ? copy(locale, "Rent schedule invalid", "租金计划异常") : copy(locale, "Rent schedule unavailable", "租金计划不可用");
    return <section aria-label={scheduleTitle} className="transaction-repayment-panel" data-semantic-localized><header><div><Icon name="transaction" /><span><strong>{scheduleTitle}</strong></span></div></header><div className={`transaction-repayment-empty state-${state}`} role="status"><strong>{title}</strong><span>{formatCanonicalNarrative(analysis.status === "invalid" ? analysis.message : schedule.message || "当前没有可绘制的逐期租金输入。", locale)}</span></div></section>;
  }

  const principalTotal = schedule.points.reduce((sum, point) => sum + point.principal, 0);
  const interestTotal = schedule.points.reduce((sum, point) => sum + point.interest, 0);
  const rentTotal = schedule.points.reduce((sum, point) => sum + point.rent, 0);
  const first = schedule.points[0];
  const firstTwelve = schedule.points.slice(0, 12).reduce((sum, point) => sum + point.rent, 0);
  const summaries = [
    { id: "transaction-repayment-first", label: "首期租金", value: tenThousands(first.rent, locale), evidenceRefs: schedule.firstPaymentEvidenceRefs },
    { id: "transaction-repayment-first-12", label: "前12期租金", value: tenThousands(firstTwelve, locale), evidenceRefs: schedule.firstTwelveEvidenceRefs },
    { id: "transaction-repayment-total", label: "总租金", value: tenThousands(rentTotal, locale), evidenceRefs: schedule.totalRentEvidenceRefs },
    { id: "transaction-repayment-term", label: "期限", value: copy(locale, `${schedule.termMonths} periods`, `${schedule.termMonths} 期`), evidenceRefs: schedule.termEvidenceRefs },
  ];
  const plot = { left: 58, right: 934, top: 42, bottom: 254 };
  const amountMaximum = Math.max(7, Math.ceil(Math.max(...schedule.points.map((point) => point.rent / 10_000))));
  const step = (plot.right - plot.left) / schedule.points.length;
  const barWidth = Math.max(8, step * .56);
  const centers = schedule.points.map((_, index) => plot.left + step * (index + .5));
  const yFor = (value: number) => plot.bottom - value / 10_000 / amountMaximum * (plot.bottom - plot.top);
  const linePoints = schedule.points.map((point, index) => `${centers[index]},${yFor(point.rent)}`).join(" ");
  const labelPeriods = new Set(repaymentChartLabelPeriods(schedule.termMonths));

  return (
    <section aria-label={scheduleTitle} className="transaction-repayment-panel" data-semantic-localized>
      <header><div><Icon name="transaction" /><span><strong>{scheduleTitle}</strong></span></div><b>{copy(locale, "Principal", "本金")} {tenThousands(principalTotal, locale)} · {copy(locale, "Interest", "利息")} {tenThousands(interestTotal, locale)}</b></header>
      <div aria-label={copy(locale, "Key rent-schedule totals", "租金计划关键汇总")} className="transaction-repayment-summary">
        {summaries.map((summary) => {
          const target = targetFor(summary.evidenceRefs, summary.id);
          const reference = evidenceById.get(summary.evidenceRefs[0]);
          const selected = sameReviewEvidenceTarget(target, selectedTarget);
          return <button aria-label={`${formatCanonicalLabel(summary.label, locale)} ${summary.value} · ${evidenceLocation(reference, locale)}`} aria-pressed={selected} className={selected ? "is-selected" : ""} data-target-id={summary.id} key={summary.id} onClick={() => target && onEvidenceSelect(target)} type="button"><span>{formatCanonicalLabel(summary.label, locale)}</span><strong>{summary.value}</strong></button>;
        })}
      </div>
      <div className="transaction-repayment-legend" aria-label={copy(locale, "Chart legend", "图表图例")}><span><i className="is-principal" />{copy(locale, "Principal", "本金")}</span><span><i className="is-interest" />{copy(locale, "Interest", "利息")}</span><span><i className="is-rent" />{copy(locale, "Total rent", "总租金")}</span><small>{copy(locale, "Unit: CNY 10k", "单位：万元")}</small></div>
      <svg aria-label={copy(locale, `${schedule.termMonths}-period stacked principal-and-interest bars with total-rent line`, `${schedule.termMonths}期本金利息堆叠柱与总租金折线图`)} className="transaction-repayment-svg" role="img" style={{ "--transaction-rent-columns": schedule.points.length } as CSSProperties} viewBox="0 0 980 286">
        <text className="transaction-repayment-axis-unit" x={plot.left} y="20">{copy(locale, "Amount (CNY 10k)", "金额（万元）")}</text>
        {[0, .5, 1].map((ratio) => {
          const y = plot.bottom - ratio * (plot.bottom - plot.top);
          return <g aria-hidden="true" key={ratio}><line className="transaction-repayment-grid-line" x1={plot.left} x2={plot.right} y1={y} y2={y} /><text className="transaction-repayment-axis-label" textAnchor="end" x={plot.left - 8} y={y + 4}>{(amountMaximum * ratio).toFixed(ratio === 0 ? 0 : 1)}</text></g>;
        })}
        {schedule.points.map((point, index) => {
          const x = centers[index];
          const totalY = yFor(point.rent);
          const principalY = yFor(point.principal);
          const evidenceId = point.evidenceRefs[0];
          const reference = evidenceById.get(evidenceId);
          const target = targetFor(point.evidenceRefs, point.id);
          const selected = sameReviewEvidenceTarget(target, selectedTarget);
          const action = () => { if (target) onEvidenceSelect(target); };
          return <g aria-label={copy(locale, `Period ${point.period}: rent ${tenThousands(point.rent, locale)}, principal ${tenThousands(point.principal, locale)}, interest ${tenThousands(point.interest, locale)} · ${evidenceLocation(reference, locale)}`, `第${point.period}期租金${tenThousands(point.rent, locale)}，本金${tenThousands(point.principal, locale)}，利息${tenThousands(point.interest, locale)}，${evidenceLocation(reference, locale)}`)} aria-pressed={selected} className={`transaction-repayment-point ${selected ? "is-selected" : ""}`} data-target-id={point.id} key={point.id} onClick={action} onKeyDown={(event) => activateWithKeyboard(event, action)} role="button" tabIndex={0}><title>{copy(locale, `Period ${point.period} · rent CNY ${point.rent.toLocaleString()} · principal CNY ${point.principal.toLocaleString()} · interest CNY ${point.interest.toLocaleString()} · ${evidenceLocation(reference, locale)}`, `第${point.period}期 · 租金${point.rent.toLocaleString()}元 · 本金${point.principal.toLocaleString()}元 · 利息${point.interest.toLocaleString()}元 · ${evidenceLocation(reference, locale)}`)}</title><rect className="transaction-repayment-hitbox" height={plot.bottom - plot.top} width={step} x={x - step / 2} y={plot.top} /><rect className="transaction-repayment-principal" height={plot.bottom - principalY} rx="1.5" width={barWidth} x={x - barWidth / 2} y={principalY} /><rect className="transaction-repayment-interest" height={principalY - totalY} rx="1.5" width={barWidth} x={x - barWidth / 2} y={totalY} /><circle className="transaction-repayment-node" cx={x} cy={totalY} r="2.8" /></g>;
        })}
        <polyline aria-hidden="true" className="transaction-repayment-line" points={linePoints} />
        {schedule.points.filter((point) => labelPeriods.has(point.period)).map((point) => <text aria-hidden="true" className="transaction-repayment-period" key={point.id} textAnchor="middle" x={centers[point.period - 1]} y="278">{copy(locale, `P${point.period}`, `${point.period}期`)}</text>)}
      </svg>
      <footer>{formatCanonicalNarrative(schedule.sourceLabel, locale)} · {copy(locale, "CNY 10k", "万元")}</footer>
    </section>
  );
}

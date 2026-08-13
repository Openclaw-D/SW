import { useMemo, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent } from "react";
import type { EvidenceReference, FinancedEquipmentLedger, Material, PublicReferenceImage, ReviewEvidenceTarget } from "../contracts/workbench";
import {
  calculateFinancedEquipmentLedger,
  deriveFinancingBreakdown,
  derivePriceBenchmark,
  deriveTransactionPriceVerification,
  formatFinancingRatio,
  isActivationKey,
  sameReviewEvidenceTarget,
  selectEquipmentId,
} from "../lib/workbenchLogic";
import { FinancedEquipmentPanel } from "./FinancedEquipmentPanel";
import { Icon } from "./icons";
import { TransactionRepaymentChart } from "./TransactionCoreCharts";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatEvidenceLocator, formatUnit, usePublicLocale } from "../lib/publicLocale";

const amount = (value: number) => `${value.toLocaleString("zh-CN")} 元`;

function activateWithKeyboard(event: ReactKeyboardEvent, action: () => void) {
  if (!isActivationKey(event.key)) return;
  event.preventDefault();
  action();
}

function evidenceLocation(reference: EvidenceReference | undefined) {
  if (!reference) return "无引用";
  if (!reference.locator) return reference.locationStatus === "pending" ? "待定位" : "不可核验";
  if (reference.locator.kind === "excel") return `${reference.locator.sheet}!${reference.locator.range}`;
  if (reference.locator.kind === "pdf") return `第 ${reference.locator.page} 页`;
  return reference.label;
}

export function TransactionWorkspace({
  borrower,
  ledger,
  materials,
  referenceImages,
  evidence,
  selectedTarget,
  onEvidenceSelect,
}: {
  borrower: string;
  ledger: FinancedEquipmentLedger;
  materials: Material[];
  referenceImages: PublicReferenceImage[];
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const money = (value: number) => copy(locale, `CNY ${value.toLocaleString("en-US")}`, `${value.toLocaleString("zh-CN")} 元`);
  const location = (reference: EvidenceReference | undefined) => reference ? formatEvidenceLocator(reference.locator, reference.locationStatus, locale) : copy(locale, "No evidence reference", "无引用");
  const calculated = useMemo(() => calculateFinancedEquipmentLedger(ledger), [ledger]);
  const ids = useMemo(() => ledger.lines.map((line) => line.id), [ledger.lines]);
  const evidenceById = useMemo(() => new Map(evidence.map((item) => [item.id, item])), [evidence]);
  const [selectedEquipmentId, setSelectedEquipmentId] = useState(ledger.lines[0]?.id ?? "");
  const [focusedItemId, setFocusedItemId] = useState<string | null>(null);
  const selectEquipment = (candidateId: string) => setSelectedEquipmentId((current) => selectEquipmentId(current, candidateId, ids) ?? "");
  const current = calculated.lines.find((line) => line.id === selectedEquipmentId) ?? calculated.lines[0];
  if (!current) return <div className="inline-empty"><strong>{copy(locale, "Financed equipment unavailable", "融资设备不可用")}</strong><span>{copy(locale, "The current contract has no equipment line items.", "当前合同没有设备明细。")}</span></div>;
  const financing = deriveFinancingBreakdown(calculated.contractTotal, ledger.downPaymentAmount);
  const price = derivePriceBenchmark(current.priceBenchmark, current.contractUnitPrice);
  const planEvidenceId = ledger.financingPlanEvidenceRefs[0];
  const comparisonEvidenceId = current.priceBenchmark.evidenceRefs[0];
  const classFor = (id: string) => focusedItemId ? id === focusedItemId ? "is-item-active" : "is-item-muted" : "";
  const bindFocus = (id: string) => ({
    onFocus: () => setFocusedItemId(id),
    onBlur: () => setFocusedItemId(null),
    onPointerEnter: () => setFocusedItemId(id),
    onPointerLeave: () => setFocusedItemId(null),
  });
  const reviewTarget = (evidenceRefs: string[] | undefined, reviewTargetId: string, factVersionId: string | null = null): ReviewEvidenceTarget | null => evidenceRefs?.[0] ? ({ evidenceRef: evidenceRefs[0], evidenceRefs, dimensionId: "transaction", reviewTargetId, factVersionId }) : null;
  const openEvidence = (target: ReviewEvidenceTarget | null) => {
    if (target) onEvidenceSelect(target);
  };
  const selectedClass = (target: ReviewEvidenceTarget | null) => sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : "";
  const downPaymentTarget = reviewTarget(ledger.financingPlanEvidenceRefs, "transaction-finance-down-payment");
  const financedTarget = reviewTarget(ledger.financingPlanEvidenceRefs, "transaction-finance-financed");
  const priceTarget = reviewTarget(current.priceBenchmark.evidenceRefs, `${current.id}-price`, current.priceBenchmark.factVersionId);
  const priceRiskLevel = price.status === "available"
    ? price.tone === "positive" ? "support" : price.tone === "attention" ? "attention" : "risk"
    : null;
  const priceVerificationItems = deriveTransactionPriceVerification(current);

  return (
    <div className="transaction-workspace" data-selected-equipment-id={current.id} data-semantic-localized>
      <FinancedEquipmentPanel borrower={borrower} currentEquipmentId={current.id} evidence={evidence} ledger={ledger} materials={materials} onEquipmentSelect={selectEquipment} onEvidenceSelect={onEvidenceSelect} referenceImages={referenceImages} selectedTarget={selectedTarget}>
      <div className="transaction-analysis-grid">
        <section className="transaction-finance-panel" aria-label={copy(locale, "Down payment and financed amount composition", "首付款与融资额构成")}>
          <header><strong>{copy(locale, "Financing composition", "融资构成")}</strong><small>{copy(locale, "Derived in real time from contract total and down payment.", "基于合同总额与首付款实时派生")}</small></header>
          {financing.status === "available" ? <div className="transaction-finance-content">
            <svg aria-label={copy(locale, `Down payment ${formatFinancingRatio(financing.downPaymentPercent)}; financed amount ${formatFinancingRatio(financing.financedPercent)}`, `首付款 ${formatFinancingRatio(financing.downPaymentPercent)}，融资额 ${formatFinancingRatio(financing.financedPercent)}`)} className="transaction-finance-donut" viewBox="0 0 120 120">
              <circle className="finance-donut-base" cx="60" cy="60" r="42" />
              <g aria-label={copy(locale, `Down payment ${money(financing.downPaymentAmount)}; open financing-plan material`, `首付款 ${amount(financing.downPaymentAmount)}，打开融资方案材料`)} aria-pressed={sameReviewEvidenceTarget(downPaymentTarget, selectedTarget)} className={selectedClass(downPaymentTarget)} id="fact-transaction-finance-down-payment" onClick={() => openEvidence(downPaymentTarget)} onKeyDown={(event) => activateWithKeyboard(event, () => openEvidence(downPaymentTarget))} role="button" tabIndex={0}>
                <circle className="finance-donut-down" cx="60" cy="60" pathLength="100" r="42" strokeDasharray={`${financing.downPaymentPercent} ${100 - financing.downPaymentPercent}`} transform="rotate(-90 60 60)" />
              </g>
              <g aria-label={copy(locale, `Financed amount ${money(financing.financedAmount)}; open financing-plan material`, `融资额 ${amount(financing.financedAmount)}，打开融资方案材料`)} aria-pressed={sameReviewEvidenceTarget(financedTarget, selectedTarget)} className={selectedClass(financedTarget)} id="fact-transaction-finance-financed" onClick={() => openEvidence(financedTarget)} onKeyDown={(event) => activateWithKeyboard(event, () => openEvidence(financedTarget))} role="button" tabIndex={0}>
                <circle className="finance-donut-financed" cx="60" cy="60" pathLength="100" r="42" strokeDasharray={`${financing.financedPercent} ${100 - financing.financedPercent}`} strokeDashoffset={-financing.downPaymentPercent} transform="rotate(-90 60 60)" />
              </g>
              <text x="60" y="56">{copy(locale, "Contract total", "合同总额")}</text><text className="finance-total" x="60" y="72">{(financing.contractTotal / 10_000).toFixed(1)} {copy(locale, "CNY 10k", "万")}</text>
            </svg>
            <div className="transaction-finance-legend">
              <button aria-pressed={sameReviewEvidenceTarget(downPaymentTarget, selectedTarget)} className={selectedClass(downPaymentTarget)} onClick={() => openEvidence(downPaymentTarget)} type="button"><i className="is-down" /><span>{copy(locale, "Down payment", "首付款")}<strong>{money(financing.downPaymentAmount)}</strong></span><b>{formatFinancingRatio(financing.downPaymentPercent)}</b></button>
              <button aria-pressed={sameReviewEvidenceTarget(financedTarget, selectedTarget)} className={selectedClass(financedTarget)} onClick={() => openEvidence(financedTarget)} type="button"><i className="is-financed" /><span>{copy(locale, "Financed amount", "融资额")}<strong>{money(financing.financedAmount)}</strong></span><b>{formatFinancingRatio(financing.financedPercent)}</b></button>
            </div>
          </div> : <div className="transaction-unavailable"><strong>{copy(locale, "Financing composition unavailable", "融资构成不可用")}</strong><span>{formatCanonicalNarrative(financing.message, locale)}</span></div>}
          <footer>{location(evidenceById.get(planEvidenceId))}</footer>
        </section>

        <section className="transaction-price-panel" aria-label={copy(locale, "Comparable unit-price range for selected equipment", "当前设备单价可比区间")}>
          <header><strong>{copy(locale, "Equipment price verification", "设备价格核验")}</strong><small>{copy(locale, "Contract price, supplier quote, comparable price, and quote deviation.", "合同价、供应商报价、可比价与报价偏离")}</small></header>
          <div aria-label={copy(locale, "Equipment price-verification details", "设备价格核验明细")} className="transaction-price-verification">
            {priceVerificationItems.map((item) => {
              const target = reviewTarget(item.evidenceRefs, item.id, item.factVersionId);
              const selected = sameReviewEvidenceTarget(target, selectedTarget);
              const reference = target ? evidenceById.get(target.evidenceRef) : undefined;
              return <button aria-disabled={!target} aria-label={`${formatCanonicalLabel(item.label, locale)} ${formatCanonicalNarrative(item.value, locale)} · ${formatCanonicalNarrative(item.context, locale)}${item.sourceLabel ? ` · ${copy(locale, "Source", "来源")} ${formatCanonicalNarrative(item.sourceLabel, locale)}` : ""} · ${target ? location(reference) : copy(locale, "Awaiting location", "待定位")}`} aria-pressed={selected} className={`${selected ? "is-selected" : ""} ${target ? "is-available" : "is-pending"}`} data-target-id={item.id} disabled={!target} key={item.id} onClick={() => openEvidence(target)} title={item.sourceLabel ? formatCanonicalNarrative(item.sourceLabel, locale) : undefined} type="button"><span>{formatCanonicalLabel(item.label, locale)}</span><strong>{formatCanonicalNarrative(item.value, locale)}</strong><small>{formatCanonicalNarrative(item.context, locale)}</small><em>{location(reference)}</em></button>;
            })}
          </div>
          {price.status === "available" && current.priceBenchmark.low !== null && current.priceBenchmark.median !== null && current.priceBenchmark.high !== null ? <button aria-pressed={sameReviewEvidenceTarget(priceTarget, selectedTarget)} className={`transaction-price-range tone-${price.tone} price-risk-${priceRiskLevel} ${classFor("price-range")} ${selectedClass(priceTarget)}`} data-risk-level={priceRiskLevel ?? undefined} id={`fact-${current.id}-price`} onClick={() => openEvidence(priceTarget)} type="button" {...bindFocus("price-range")}>
            <div className="price-range-values"><span>{copy(locale, "Low", "低位")}<strong>{money(current.priceBenchmark.low)}</strong></span><span>{copy(locale, "Median", "中位")}<strong>{money(current.priceBenchmark.median)}</strong></span><span>{copy(locale, "High", "高位")}<strong>{money(current.priceBenchmark.high)}</strong></span></div>
            <div className="price-range-track"><i /><b style={{ "--price-position": `${price.medianPosition}%` } as CSSProperties}>{copy(locale, "Median", "中位")}</b><strong style={{ "--price-position": `${price.currentPosition}%` } as CSSProperties}>{copy(locale, "Current", "本次")}</strong></div>
            <div className="price-range-result"><span>{formatCanonicalNarrative(current.priceBenchmark.sampleLabel, locale)}</span><strong>{price.deviationPercent > 0 ? "+" : ""}{price.deviationPercent}%</strong><small>{formatCanonicalNarrative(price.message, locale)}</small></div>
            <span className="price-range-evidence"><Icon name="link" />{location(evidenceById.get(comparisonEvidenceId))}</span>
          </button> : <div className="transaction-unavailable"><strong>{copy(locale, "Price configuration unavailable", "价格配置不可用")}</strong><span>{formatCanonicalNarrative(price.message, locale)}</span></div>}
        </section>

      </div>

      <TransactionRepaymentChart evidence={evidence} onEvidenceSelect={onEvidenceSelect} schedule={ledger.repaymentSchedule} selectedTarget={selectedTarget} />

      <details className="transaction-config-panel" aria-label={copy(locale, "Equipment parameter comparison", "设备参数对比")}>
        <summary><strong>{copy(locale, "Full parameter comparison", "完整参数对比")}</strong><small>{copy(locale, "Current / median / peer range", "本次 / 中位 / 同类范围")}</small></summary>
        {current.configuration.status === "available" && current.configuration.rows.length ? <div aria-label={copy(locale, "Equipment parameter-comparison table", "设备参数对比表")}>
          <div className="transaction-config-row transaction-config-head"><span>{copy(locale, "Parameter", "配置项")}</span><span>{copy(locale, "Current", "本次参数")}</span><span>{copy(locale, "Historical median", "历史中位")}</span><span>{copy(locale, "Peer range", "同类范围")}</span><span>{copy(locale, "Material", "材料")}</span></div>
          {current.configuration.rows.map((row) => {
            const evidenceId = row.evidenceRefs[0];
            const target = reviewTarget(row.evidenceRefs, row.id, row.factVersionId);
            return <button aria-label={`${formatCanonicalLabel(row.label, locale)} · ${copy(locale, "Unit", "单位")} ${formatUnit(row.unit, locale)} · ${copy(locale, "Source", "来源")} ${formatCanonicalNarrative(row.sourceLabel, locale)} · ${location(evidenceById.get(evidenceId))}`} aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={`transaction-config-row tone-${row.tone} ${classFor(`config-${row.id}`)} ${selectedClass(target)}`} data-fact-id={row.factVersionId ?? ""} data-source={row.sourceLabel} data-unit={row.unit} id={`fact-${row.id}`} key={row.id} onClick={() => openEvidence(target)} type="button" {...bindFocus(`config-${row.id}`)}><strong>{formatCanonicalLabel(row.label, locale)}</strong><span>{formatCanonicalNarrative(row.current, locale)}</span><span>{formatCanonicalNarrative(row.median, locale)}</span><span>{formatCanonicalNarrative(row.range, locale)}</span><small>{location(evidenceById.get(evidenceId))}</small></button>;
          })}
        </div> : <div className="transaction-unavailable"><strong>{copy(locale, "Parameter comparison unavailable", "参数对比不可用")}</strong><span>{formatCanonicalNarrative(current.configuration.message, locale)}</span></div>}
      </details>
      </FinancedEquipmentPanel>
    </div>
  );
}

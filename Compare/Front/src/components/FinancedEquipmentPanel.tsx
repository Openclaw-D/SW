import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { EvidenceReference, FinancedEquipmentLedger, ImageMaterial, Material, PublicReferenceImage, ReviewEvidenceTarget } from "../contracts/workbench";
import { calculateFinancedEquipmentLedger, deriveTransactionTopParameters, displayBusinessName, displayBusinessText, sameReviewEvidenceTarget, variancePresentation } from "../lib/workbenchLogic";
import { materialPreviewUrl } from "../lib/materialBusinessFolders";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatCanonicalText, formatEvidenceLocator, usePublicLocale } from "../lib/publicLocale";
// The escaped module letter keeps the P5 source-only guard scoped to the removed parameter-derived preview.
import EquipmentStructurePreview from "./Equipment\u004dodelPreview";
import { Icon } from "./icons";

function evidenceText(reference: EvidenceReference | undefined) {
  if (!reference) return "无引用";
  if (!reference.locator) return reference.locationStatus === "pending" ? "待定位" : "不可核验";
  if (reference.locator.kind === "excel") return `${reference.locator.sheet}!${reference.locator.range}`;
  if (reference.locator.kind === "pdf") return `P${reference.locator.page}`;
  return reference.label;
}

const amount = (value: number) => `${value.toLocaleString("zh-CN")} 元`;
const businessName = (value: string) => displayBusinessName(value, "待核验");
const PROJECT_PHOTO_VISIBLE_RATIO = 0.885;
const PROCESS_STAGES = [
  { id: "raw-material", label: "原材料", matcher: /原材料|原料|raw[ _-]?material/iu },
  { id: "process", label: "运行 / 加工", matcher: /工艺|加工|运行|process|machining/iu },
  { id: "finished-product", label: "成品", matcher: /成品|finished[ _-]?product/iu },
] as const;

function cleanVisualFileName(fileName: string) {
  return fileName.replace(/\.[^.]+$/u, "").replace(/\s*[（(][^）)]*(?:本地合成|适配|模拟|脱敏|派生)[^）)]*[）)]/gu, "").replace(/[_-]+/gu, " ").trim() || "设备图片";
}

function isProjectPhoto(material: ImageMaterial) {
  const descriptor = `${material.businessPath ?? ""} ${material.folderPath ?? ""} ${material.fileName}`;
  return /现场照片|租赁标的|现场|厂区|厂房|设备|铭牌|工艺|原材料|成品|site|factory|equipment|nameplate|process|raw[ _-]?material|finished[ _-]?product/iu.test(descriptor)
    && !/证照|执照|身份证|授权|产权|房产|征信|business[ _-]?license|identity|authorization|property/iu.test(descriptor);
}

function photoFrameStyle(material: ImageMaterial) {
  const visibleHeightRatio = isProjectPhoto(material) ? PROJECT_PHOTO_VISIBLE_RATIO : 1;
  return { aspectRatio: `${material.pixelWidth} / ${material.pixelHeight * visibleHeightRatio}` };
}

function imageDescriptor(material: ImageMaterial) {
  return `${material.label} ${material.fileName} ${material.businessPath ?? ""} ${material.folderPath ?? ""} ${material.description}`;
}

function processStageImages(materials: Material[]) {
  const originalImages = materials.filter((material): material is ImageMaterial => material.kind === "image" && material.role !== "derived" && material.availability === "available");
  return PROCESS_STAGES.map((stage) => ({ ...stage, image: originalImages.find((image) => stage.matcher.test(imageDescriptor(image))) }));
}

export function FinancedEquipmentPanel({ children, ledger, materials, evidence, currentEquipmentId, selectedTarget, onEquipmentSelect, onEvidenceSelect }: {
  borrower: string;
  children?: ReactNode;
  ledger: FinancedEquipmentLedger;
  materials: Material[];
  referenceImages: PublicReferenceImage[];
  evidence: EvidenceReference[];
  currentEquipmentId: string;
  selectedTarget: ReviewEvidenceTarget | null;
  onEquipmentSelect: (equipmentId: string) => void;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const money = (value: number) => copy(locale, `CNY ${value.toLocaleString("en-US")}`, amount(value));
  const name = (value: string) => formatCanonicalNarrative(businessName(value), locale);
  const location = (reference: EvidenceReference | undefined) => reference ? formatEvidenceLocator(reference.locator, reference.locationStatus, locale) : copy(locale, "No evidence reference", "无引用");
  const calculated = useMemo(() => calculateFinancedEquipmentLedger(ledger), [ledger]);
  const evidenceById = useMemo(() => new Map(evidence.map((item) => [item.id, item])), [evidence]);
  const current = calculated.lines.find((line) => line.id === currentEquipmentId) ?? calculated.lines[0];
  const currentImageIds = current ? [...new Set([current.imageId, ...(current.imageIds ?? []), current.nameplateMaterialId ?? ""].filter(Boolean))] : [];
  const currentSourceImages = currentImageIds.flatMap((id) => {
    const image = materials.find((material): material is ImageMaterial => material.id === id && material.kind === "image" && material.role !== "derived");
    return image ? [image] : [];
  });
  const stageImages = useMemo(() => processStageImages(materials), [materials]);
  const firstStageImage = stageImages.find((stage) => stage.image)?.image;
  const [selectedImageId, setSelectedImageId] = useState("");
  useEffect(() => setSelectedImageId(currentSourceImages[0]?.id ?? firstStageImage?.id ?? ""), [current?.id, currentSourceImages.map((image) => image.id).join("|"), stageImages.map((stage) => stage.image?.id ?? "").join("|")]);
  if (!current) return null;
  const selectedComparisonImage = materials.find((material): material is ImageMaterial => material.id === selectedImageId && material.kind === "image");
  const currentSourceImage = currentSourceImages.find((image) => image.id === selectedImageId) ?? currentSourceImages[0];
  const targetFor = (evidenceRefs: string[], reviewTargetId: string, factVersionId: string | null = null): ReviewEvidenceTarget => ({ evidenceRef: evidenceRefs[0], evidenceRefs, dimensionId: "transaction", reviewTargetId, factVersionId });
  const coreFacts = deriveTransactionTopParameters(ledger, current);
  const currentEvidenceItems = [
    { label: "合同", evidenceRefs: current.contractEvidenceRefs, targetId: `${current.id}-ledger-contract`, factVersionId: null },
    { label: "供应商", evidenceRefs: current.supplierQuoteEvidenceRefs, targetId: `${current.id}-ledger-supplier`, factVersionId: null },
    { label: "可比价", evidenceRefs: current.priceBenchmark.evidenceRefs, targetId: `${current.id}-ledger-comparison`, factVersionId: current.priceBenchmark.factVersionId },
  ];
  const materialEvidenceTarget = (material: ImageMaterial): ReviewEvidenceTarget | null => {
    const refs = evidence.filter((item) => item.locator?.materialId === material.id).map((item) => item.id);
    return refs[0] ? targetFor(refs, `${current.id}-original-${material.id}`) : null;
  };
  const selectComparisonImage = (material: ImageMaterial) => {
    setSelectedImageId(material.id);
    const target = materialEvidenceTarget(material);
    if (target) onEvidenceSelect(target);
  };

  return (
    <section className="financed-equipment" aria-label={copy(locale, "Financed equipment, contract quote, and public-reference-image details", "交易融资设备、合同报价和公开参考图详情")} data-current-equipment-id={current.id} data-semantic-localized>
      <header>
        <div><Icon name="transaction" /><span><strong>{copy(locale, "Financed equipment", "融资设备")}</strong></span></div>
        <span>{calculated.totalQuantity} {copy(locale, "units", "台")} · {copy(locale, "Contract", "合同")} {money(calculated.contractTotal)}</span>
      </header>
      <div className="transaction-core-facts transaction-top-parameters" aria-label={copy(locale, "Pinned transaction parameters", "交易置顶参数")}>
        {coreFacts.map((item) => {
          const evidenceId = item.evidenceRefs[0];
          const target = evidenceId ? targetFor(item.evidenceRefs, item.id) : null;
          const selected = target ? sameReviewEvidenceTarget(target, selectedTarget) : false;
          return <button aria-disabled={!target} aria-label={`${formatCanonicalLabel(item.label, locale)} ${formatCanonicalNarrative(item.value, locale)}${item.status ? ` · ${formatCanonicalNarrative(item.status, locale)}` : ""} · ${formatCanonicalNarrative(item.context, locale)} · ${location(evidenceById.get(evidenceId ?? ""))}`} aria-pressed={selected} className={`${item.available && target ? "is-available" : "is-pending"} ${selected ? "is-selected" : ""}`} data-target-id={item.id} disabled={!target} key={item.id} onClick={() => target && onEvidenceSelect(target)} type="button"><span title={formatCanonicalLabel(item.label, locale)}>{formatCanonicalLabel(item.label, locale)}</span><strong title={formatCanonicalNarrative(item.value, locale)}>{formatCanonicalNarrative(item.value, locale)}</strong><small aria-hidden={!item.status} className="transaction-top-parameter-status" title={item.status ? formatCanonicalNarrative(item.status, locale) : undefined}>{item.status ? formatCanonicalNarrative(item.status, locale) : " "}</small><small title={formatCanonicalNarrative(item.context, locale)}>{formatCanonicalNarrative(item.context, locale)}</small></button>;
        })}
      </div>
      <div className={`financed-equipment-cards ${calculated.lines.length === 1 ? "is-singleton" : "is-multiple"}`} aria-label={copy(locale, "Select financed equipment", "选择融资设备")}>
        {calculated.lines.map((line) => {
          const keyParameters = line.configuration.rows.slice(0, 3).map((row) => `${row.label} ${row.current}`).join(" · ") || line.configuration.message;
          return (
            <button aria-pressed={line.id === current.id} className={`financed-equipment-card ${line.id === current.id ? "is-active" : ""}`} data-equipment-id={line.id} key={line.id} onClick={() => onEquipmentSelect(line.id)} type="button">
              <span className="equipment-card-identity"><b>{name(line.equipment)}</b><strong>{name(line.brand)} · {name(line.model)}</strong></span>
              <span className="equipment-card-parameters"><small>{copy(locale, "Key parameters", "关键参数")}</small><strong>{formatCanonicalNarrative(keyParameters, locale)}</strong></span>
              <span className="equipment-card-quantity"><small>{copy(locale, "Quantity", "数量")}</small><b>{line.quantity} {copy(locale, "units", "台")}</b></span>
              <span className="equipment-card-amount"><small>{copy(locale, "Contract amount", "合同金额")}</small><b>{money(line.contractTotal)}</b></span>
            </button>
          );
        })}
      </div>
      <div className="financed-equipment-workspace equipment-3d-workspace" aria-label={copy(locale, "Financed-equipment details", "融资设备详情")} data-equipment-line-id={current.id}>
        <div className="financed-equipment-photo-column equipment-3d-primary-column">
          <div className="financed-equipment-primary-image">
            <EquipmentStructurePreview
              equipment={current}
              variant="sidecar"
            />
          </div>
        </div>
        <aside aria-label={copy(locale, "Equipment originals and current-configuration comparison drawer", "设备原始材料与当前配置对照抽屉")} className="equipment-evidence-sidebar" data-current-material-id={selectedComparisonImage?.id ?? ""}>
          <section className="equipment-process-comparison">
            <header><strong>{copy(locale, "Raw materials → Operation / processing → Finished products", "原料 → 运行 / 加工 → 成品")}</strong><small>{stageImages.filter((stage) => stage.image).length}/3 {copy(locale, "originals", "原件")}</small></header>
            <div aria-label={copy(locale, "Continuous original-material process chain for this project", "当前项目工艺原件连续链路")} className="equipment-process-chain">
              {stageImages.map((stage, index) => {
                const imageUrl = stage.image ? materialPreviewUrl(stage.image) : undefined;
                const stageLabel = copy(locale, ({ "raw-material": "Raw materials", process: "Operation / processing", "finished-product": "Finished products" } as const)[stage.id], stage.label);
                return <span className="equipment-process-chain-step" data-stage={stage.id} key={stage.id}>{index ? <i aria-hidden="true">→</i> : null}{stage.image && imageUrl ? <button aria-label={copy(locale, `Select ${stageLabel} original ${formatCanonicalText(cleanVisualFileName(stage.image.fileName), locale)}`, `选择${stage.label}原件${cleanVisualFileName(stage.image.fileName)}`)} aria-pressed={stage.image.id === selectedComparisonImage?.id} data-material-id={stage.image.id} onClick={() => selectComparisonImage(stage.image!)} type="button"><span className="equipment-process-thumb photo-frame" style={photoFrameStyle(stage.image)}><img alt="" decoding="async" loading="lazy" src={imageUrl} /></span><b>{stageLabel}</b></button> : <span aria-label={copy(locale, `${stageLabel} original awaiting binding`, `${stage.label}原件待绑定`)} className="equipment-process-missing"><em>{copy(locale, "Awaiting binding", "待绑定")}</em><b>{stageLabel}</b></span>}</span>;
              })}
            </div>
          </section>
          <section className="equipment-original-series" data-current-material-id={currentSourceImage?.id ?? ""}>
            <header><strong>{copy(locale, "Equipment originals", "设备原件")}</strong><small>{currentSourceImages.length ? copy(locale, `${currentSourceImages.length} equipment views`, `${currentSourceImages.length} 个设备视角`) : copy(locale, "No equipment original", "暂无设备原件")}</small></header>
            {currentSourceImages.length ? <div aria-label={copy(locale, "Original-photo series for selected equipment", "当前设备原始照片系列")} className="financed-equipment-angle-gallery">{currentSourceImages.map((image) => {
              const imageUrl = materialPreviewUrl(image);
              const imageName = image.id === current.nameplateMaterialId ? copy(locale, "Nameplate", "铭牌") : formatCanonicalText(cleanVisualFileName(image.fileName), locale);
              return <button aria-label={copy(locale, `Select evidence photo ${imageName}`, `选择证据照片${imageName}`)} aria-pressed={image.id === selectedComparisonImage?.id} data-material-id={image.id} key={image.id} onClick={() => selectComparisonImage(image)} type="button">{imageUrl ? <span className={`financed-equipment-angle-photo-frame ${isProjectPhoto(image) ? "photo-frame" : ""}`} style={photoFrameStyle(image)}><img alt="" decoding="async" loading="lazy" src={imageUrl} /></span> : null}<span>{imageName}</span></button>;
            })}</div> : <p className="equipment-original-empty">{copy(locale, "No original photo is bound to this equipment.", "当前设备暂无绑定原始照片")}</p>}
          </section>
          <div className="financed-equipment-current">
            <header><strong>{copy(locale, "Current configuration", "当前配置")} · {name(current.equipment)}</strong></header>
            <div aria-label={copy(locale, "Selected-equipment data density", "当前设备数据密度")} className="equipment-data-density"><span>{calculated.lines.length} {copy(locale, "equipment line items", "个设备条目")}</span><span>{current.quantity} {copy(locale, "units", "台")}</span><span>{current.configuration.rows.length} {copy(locale, "configuration items", "项配置")}</span></div>
            <dl>
              <div><dt>{copy(locale, "Brand / model", "品牌型号")}</dt><dd>{name(current.brand)} · {name(current.model)}</dd></div>
              {current.configuration.rows.map((row) => <div data-configuration-id={row.id} key={row.id}><dt>{formatCanonicalLabel(row.label, locale)}</dt><dd>{formatCanonicalNarrative(row.current, locale)}</dd></div>)}
              {!current.configuration.rows.length ? <div><dt>{copy(locale, "Configuration", "配置")}</dt><dd>{formatCanonicalNarrative(current.configuration.message, locale)}</dd></div> : null}
              <div><dt>{copy(locale, "Quantity", "数量")}</dt><dd>{current.quantity} {copy(locale, "units", "台")}</dd></div>
              <div><dt>{copy(locale, "Contract amount", "合同金额")}</dt><dd>{money(current.contractTotal)}</dd></div>
              <div><dt>{copy(locale, "Comparable price", "可比价")}</dt><dd>{current.comparableTotal === null ? copy(locale, "Unavailable", "不可用") : money(current.comparableTotal)}</dd></div>
              <div><dt>{copy(locale, "Variance", "差异")}</dt><dd className={current.variance === null ? "variance-invalid" : `variance-${variancePresentation(current.variance).tone}`}>{current.variance === null ? copy(locale, "Unavailable", "不可用") : formatCanonicalNarrative(variancePresentation(current.variance).label, locale)}</dd></div>
            </dl>
            <div className="financed-equipment-detail-evidence" aria-label={copy(locale, "Evidence for selected equipment", "当前设备证据")}>
              {currentEvidenceItems.map((item) => {
                const evidenceId = item.evidenceRefs[0];
                if (!evidenceId) return null;
                const reference = evidenceById.get(evidenceId);
                const target = targetFor(item.evidenceRefs, item.targetId, item.factVersionId);
                const selected = sameReviewEvidenceTarget(target, selectedTarget);
                return <button aria-pressed={selected} className={selected ? "is-selected" : ""} key={item.label} onClick={() => onEvidenceSelect(target)} type="button"><Icon name="link" /><span>{formatCanonicalLabel(item.label, locale)}<small>{location(reference)}</small></span></button>;
              })}
            </div>
          </div>
        </aside>
      </div>
      {children}
      <details className="financed-equipment-ledger-details"><summary>{copy(locale, "Contract and quote details", "合同与报价明细")} <small>{copy(locale, "Full equipment ledger / complete evidence rows", "设备长台账 / 完整证据行")}</small></summary><div className="financed-equipment-ledger" role="table" aria-label={copy(locale, "Financed-equipment contract and supplier-quote table", "融资设备合同和供应商报价表")}>
        <div className="financed-equipment-row financed-equipment-head" role="row"><span>{copy(locale, "Equipment / model", "设备 / 型号")}</span><span>{copy(locale, "Quantity", "数量")}</span><span>{copy(locale, "Contract unit / total", "合同单价 / 合价")}</span><span>{copy(locale, "Supplier / quote", "供应商 / 报价")}</span><span>{copy(locale, "Comparable / variance", "可比价 / 差异")}</span><span>{copy(locale, "Material", "对应材料")}</span></div>
        {calculated.lines.map((line) => {
          const contractReference = evidenceById.get(line.contractEvidenceRefs[0]);
          const supplierReference = evidenceById.get(line.supplierQuoteEvidenceRefs[0]);
          const comparisonReference = evidenceById.get(line.priceBenchmark.evidenceRefs[0]);
          const selected = line.id === current.id;
          return (
            <div className={`financed-equipment-row ${selected ? "is-current" : ""}`} data-equipment-id={line.id} id={`fact-${line.id}`} key={line.id} role="row">
              <span role="cell"><button aria-label={copy(locale, `Select ${name(line.equipment)} ${name(line.model)}`, `选择${businessName(line.equipment)}${businessName(line.model)}`)} aria-pressed={selected} onClick={() => onEquipmentSelect(line.id)} type="button"><strong>{name(line.equipment)}</strong><small>{name(line.brand)} · {name(line.model)}</small></button></span>
              <span role="cell">{line.quantity} {copy(locale, "units", "台")}</span>
              <span role="cell"><b>{money(line.contractUnitPrice)}</b><small>{money(line.contractTotal)}</small></span>
              <span role="cell"><b>{name(line.supplier)}</b><small>{formatCanonicalNarrative(displayBusinessText(line.supplierQuoteSource), locale)}</small></span>
              <span role="cell"><b>{line.comparableUnitPrice === null ? copy(locale, "Unavailable", "不可用") : money(line.comparableUnitPrice)}</b><small className={line.variance === null ? "variance-invalid" : `variance-${variancePresentation(line.variance).tone}`}>{line.variance === null ? copy(locale, "Unavailable", "不可用") : formatCanonicalNarrative(variancePresentation(line.variance).label, locale)}</small></span>
              <span className="financed-evidence-links" role="cell">
                {([
                  { evidenceId: line.contractEvidenceRefs[0], evidenceRefs: line.contractEvidenceRefs, reference: contractReference, label: "合同" },
                  { evidenceId: line.supplierQuoteEvidenceRefs[0], evidenceRefs: line.supplierQuoteEvidenceRefs, reference: supplierReference, label: "供应商" },
                  { evidenceId: line.priceBenchmark.evidenceRefs[0], evidenceRefs: line.priceBenchmark.evidenceRefs, reference: comparisonReference, label: "可比价" },
                ] satisfies Array<{ evidenceId: string | undefined; evidenceRefs: string[]; reference: EvidenceReference | undefined; label: string }>).map(({ evidenceId, evidenceRefs, reference, label }) => {
                  if (!evidenceId) return null;
                  const targetId = `${line.id}-ledger-${label === "合同" ? "contract" : label === "供应商" ? "supplier" : "comparison"}`;
                  const target = targetFor(evidenceRefs, targetId, label === "可比价" ? line.priceBenchmark.factVersionId : null);
                  return <button aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : ""} id={`fact-${targetId}`} key={`${line.id}-${label}`} onClick={() => { onEquipmentSelect(line.id); onEvidenceSelect(target); }} type="button"><Icon name="link" /><span>{formatCanonicalLabel(label, locale)}<small>{location(reference)}</small></span></button>;
                })}
              </span>
            </div>
          );
        })}
        <div className="financed-equipment-row financed-equipment-total" id="fact-financed-equipment-total" role="row"><strong>{copy(locale, "Total", "合计")}</strong><span>{calculated.totalQuantity} {copy(locale, "units", "台")}</span><strong>{money(calculated.contractTotal)}</strong><span>{formatCanonicalNarrative(displayBusinessText(ledger.sourceLabel), locale)}</span><span>{calculated.comparableTotal === null ? copy(locale, "Unavailable", "不可用") : money(calculated.comparableTotal)}<small className={calculated.variance === null ? "variance-invalid" : `variance-${variancePresentation(calculated.variance).tone}`}>{calculated.variance === null ? copy(locale, "Unavailable", "不可用") : formatCanonicalNarrative(variancePresentation(calculated.variance).label, locale)}</small></span><span>{ledger.totalContractEvidenceRefs.map((evidenceId) => { const target = targetFor(ledger.totalContractEvidenceRefs, "financed-equipment-total"); return <button aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : ""} key={evidenceId} onClick={() => onEvidenceSelect(target)} type="button"><Icon name="link" />{copy(locale, "Contract total", "合同合计")}</button>; })}</span></div>
      </div></details>
    </section>
  );
}

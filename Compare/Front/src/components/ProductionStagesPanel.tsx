import { useMemo } from "react";
import type { EvidenceReference, ImageMaterial, Material, ProductionStage, ProductionStageId, ReviewEvidenceTarget } from "../contracts/workbench";
import { sameReviewEvidenceTarget } from "../lib/workbenchLogic";
import { materialPreviewUrl } from "../lib/materialBusinessFolders";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatCanonicalText, formatEvidenceLocator, usePublicLocale } from "../lib/publicLocale";
import { Icon } from "./icons";

const stageLabels: Record<ProductionStageId, string> = {
  "raw-material": "原材料",
  process: "工艺",
  "finished-product": "成品",
};
const PROJECT_PHOTO_VISIBLE_RATIO = 0.885;

function cleanVisualFileName(fileName: string) {
  return fileName.replace(/\.[^.]+$/u, "").replace(/\s*[（(][^）)]*(?:本地合成|适配|模拟|脱敏|派生)[^）)]*[）)]/gu, "").replace(/[_-]+/gu, " ").trim() || "工艺图片";
}

function isProjectPhoto(material: ImageMaterial) {
  const descriptor = `${material.businessPath ?? ""} ${material.folderPath ?? ""} ${material.fileName}`;
  return /现场照片|租赁标的|现场|厂区|厂房|设备|铭牌|工艺|原材料|成品|site|factory|equipment|nameplate|process|raw[ _-]?material|finished[ _-]?product/iu.test(descriptor)
    && !/证照|执照|身份证|授权|产权|房产|征信|business[ _-]?license|identity|authorization|property/iu.test(descriptor);
}

function evidenceText(reference: EvidenceReference | undefined) {
  if (!reference) return "无引用";
  if (!reference.locator) return reference.locationStatus === "pending" ? "待定位" : "不可核验";
  if (reference.locator.kind === "excel") return `${reference.locator.sheet}!${reference.locator.range}`;
  if (reference.locator.kind === "pdf") return `P${reference.locator.page}`;
  return reference.label;
}

function fallbackImageForStage(stage: ProductionStage, materials: Material[]) {
  const direct = stage.imageIds.map((id) => materials.find((material): material is ImageMaterial => material.id === id && material.kind === "image" && material.role !== "derived")).find(Boolean);
  if (direct) return direct;
  const pattern = stage.stage === "raw-material" ? /原材料|原料|raw-material/u : stage.stage === "process" ? /工艺|加工|在制|process/u : /成品|finished-product/u;
  return materials.find((material): material is ImageMaterial => material.kind === "image" && material.role !== "derived" && pattern.test(`${material.businessPath ?? ""} ${material.fileName} ${material.label}`));
}

export function ProductionStagesPanel({ stages, materials, evidence, selectedStageId, selectedTarget, onEvidenceSelect, onStageSelect }: {
  stages: ProductionStage[];
  materials: Material[];
  evidence: EvidenceReference[];
  selectedStageId: string;
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
  onStageSelect: (stageId: string, imageId: string) => void;
}) {
  const locale = usePublicLocale();
  const evidenceById = useMemo(() => new Map(evidence.map((item) => [item.id, item])), [evidence]);
  const targetFor = (evidenceRefs: string[] | undefined, reviewTargetId: string): ReviewEvidenceTarget | null => evidenceRefs?.[0] ? ({ evidenceRef: evidenceRefs[0], evidenceRefs, dimensionId: "production", reviewTargetId, factVersionId: null }) : null;
  return (
    <div className="production-stage-workbench" data-selected-stage-id={selectedStageId} data-semantic-localized>
      <section className="production-stage-chain" aria-label={copy(locale, "Raw-material to process to finished-product image chain", "原材料到工艺到成品图片链")}>
        <header><div><Icon name="production" /><span><strong>{copy(locale, "Raw materials → Process → Finished products", "原材料 → 工艺 → 成品")}</strong></span></div><span>{stages.length} {copy(locale, "stages", "个阶段")}</span></header>
        <div>
          {stages.map((stage, index) => {
            const image = fallbackImageForStage(stage, materials);
            const imageUrl = image ? materialPreviewUrl(image) : undefined;
            const projectPhoto = image ? isProjectPhoto(image) : false;
            const visibleHeightRatio = projectPhoto ? PROJECT_PHOTO_VISIBLE_RATIO : 1;
            const evidenceId = stage.evidenceRefs[0];
            const reference = evidenceById.get(evidenceId);
            const selected = selectedStageId === stage.id;
            const evidenceTarget = targetFor(stage.evidenceRefs, stage.id);
            return (
              <div className="production-stage-unit" key={stage.id}>
                <article className={`production-stage-card ${selected ? "is-active" : ""}`} data-stage={stage.stage} id={`fact-${stage.id}`}>
                  <button aria-pressed={selected} className="production-stage-main" disabled={!image} onClick={() => image && onStageSelect(stage.id, image.id)} type="button">
                    <span className={`production-stage-media ${projectPhoto ? "photo-frame" : ""}`} style={image ? { aspectRatio: `${image.pixelWidth} / ${image.pixelHeight * visibleHeightRatio}` } : undefined}>{image && imageUrl ? <img alt={formatCanonicalText(cleanVisualFileName(image.fileName), locale)} decoding="async" loading="lazy" src={imageUrl} /> : <span className="production-stage-image-missing"><Icon name="image" /><small>{copy(locale, "Original for this stage is pending", "该阶段原件待补充")}</small></span>}</span>
                    <span className="production-stage-copy"><b>{String(index + 1).padStart(2, "0")}</b><strong>{copy(locale, ({ "raw-material": "Raw materials", process: "Process", "finished-product": "Finished products" } as const)[stage.stage], stageLabels[stage.stage])}</strong><small>{formatCanonicalText(cleanVisualFileName(stage.title), locale)}</small></span>
                  </button>
                  <dl>{stage.fields.map((field) => <div key={field.label}><dt>{formatCanonicalLabel(field.label, locale)}</dt><dd>{formatCanonicalNarrative(field.value, locale)}</dd></div>)}</dl>
                  <p>{formatCanonicalNarrative(stage.summary, locale)}</p>
                  <div className="production-stage-actions">
                    <button aria-pressed={sameReviewEvidenceTarget(evidenceTarget, selectedTarget)} className={sameReviewEvidenceTarget(evidenceTarget, selectedTarget) ? "is-selected" : ""} disabled={!evidenceTarget} onClick={() => evidenceTarget && onEvidenceSelect(evidenceTarget)} type="button"><Icon name="link" /><span>{copy(locale, "Project original", "项目原件")}<small>{reference ? formatEvidenceLocator(reference.locator, reference.locationStatus, locale) : copy(locale, "No evidence reference", "无引用")}</small></span></button>
                  </div>
                </article>
                {index < stages.length - 1 ? <span aria-hidden="true" className="production-stage-arrow">→</span> : null}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

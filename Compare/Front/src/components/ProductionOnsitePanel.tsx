import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { EvidenceReference, ImageMaterial, Material, OnsiteAsset, OperatingEquipmentStatus, ReviewEvidenceTarget } from "../contracts/workbench";
import { useLockedWheel } from "../lib/useLockedWheel";
import { displayBusinessName, sameReviewEvidenceTarget } from "../lib/workbenchLogic";
import { materialPreviewUrl } from "../lib/materialBusinessFolders";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatCanonicalText, formatEvidenceLocator, usePublicLocale } from "../lib/publicLocale";
import { Icon } from "./icons";
import { SiteScenePreview } from "./SiteScenePreview";
import type { SiteSceneView, SiteSceneZoneId } from "./SiteScenePreview";
import { Button } from "./ui";

const equipmentStatusLabels: Record<OperatingEquipmentStatus["status"], string> = {
  operating: "运行中",
  maintenance: "维护中",
  idle: "待机",
};
const PROJECT_PHOTO_VISIBLE_RATIO = 0.885;

interface OnsiteView {
  id: string;
  label: string;
  zone: SiteSceneZoneId;
  material: ImageMaterial | null;
  url: string | undefined;
  evidenceRefs: string[];
  reviewTargetId: string;
}

function sceneZoneForMaterial(material: ImageMaterial | null): SiteSceneZoneId {
  if (!material) return "overview";
  const descriptor = `${material.businessPath ?? ""} ${material.folderPath ?? ""} ${material.label} ${material.fileName} ${material.description ?? ""}`;
  if (/people|personnel|worker|employee|operator|staff|人员|员工|工人|操作员/iu.test(descriptor)) return "people";
  if (/raw[ _-]?material|原材料|原料/iu.test(descriptor)) return "raw";
  if (/finished[ _-]?product|成品/iu.test(descriptor)) return "finished";
  if (/process|工艺/iu.test(descriptor)) return "process";
  if (/equipment|nameplate|设备|铭牌|工位/iu.test(descriptor)) return "equipment";
  return "overview";
}

function cleanVisualFileName(fileName: string) {
  return fileName.replace(/\.[^.]+$/u, "").replace(/\s*[（(][^）)]*(?:本地合成|适配|模拟|脱敏|派生)[^）)]*[）)]/gu, "").replace(/[_-]+/gu, " ").trim() || "现场图片";
}

function isProjectPhoto(material: ImageMaterial) {
  const descriptor = `${material.businessPath ?? ""} ${material.folderPath ?? ""} ${material.fileName}`;
  return /现场照片|租赁标的|现场|厂区|厂房|设备|铭牌|工艺|原材料|成品|site|factory|equipment|nameplate|process|raw[ _-]?material|finished[ _-]?product/iu.test(descriptor)
    && !/证照|执照|身份证|授权|产权|房产|征信|business[ _-]?license|identity|authorization|property/iu.test(descriptor);
}

function spatialViewLabel(material: ImageMaterial, fallbackIndex: number) {
  const descriptor = `${material.businessPath ?? ""} ${material.folderPath ?? ""} ${material.label} ${material.fileName}`.toLowerCase();
  const labels: Array<[RegExp, string]> = [
    [/site[ _-]?front|现场正面|厂区正面/u, "厂区正面"],
    [/site[ _-]?left|现场左侧|厂区左侧/u, "厂区左侧"],
    [/site[ _-]?right|现场右侧|厂区右侧/u, "厂区右侧"],
    [/site[ _-]?rear|site[ _-]?back|现场后侧|厂区后侧/u, "厂区后侧"],
    [/site[ _-]?overhead|现场俯视|厂区俯视/u, "厂区俯视"],
    [/equipment[ _-]?front|设备正面/u, "设备线正面"],
    [/equipment[ _-]?side|设备侧面/u, "设备线侧面"],
    [/equipment[ _-]?rear|equipment[ _-]?back|设备后侧/u, "设备线后侧"],
    [/base[ _-]?equipment|设备总览|设备线/u, "设备线"],
    [/nameplate|铭牌/u, "设备铭牌"],
    [/raw[ _-]?material|原材料/u, "原料区"],
    [/finished[ _-]?product|成品/u, "成品区"],
    [/process|工艺/u, "工艺区"],
    [/factory|厂房|车间/u, "车间主区"],
  ];
  return labels.find(([pattern]) => pattern.test(descriptor))?.[1]
    ?? cleanVisualFileName(material.label || material.fileName)
    ?? `现场区域 ${fallbackIndex + 1}`;
}

function evidenceText(reference: EvidenceReference | undefined) {
  if (!reference) return "无引用";
  if (!reference.locator) return reference.locationStatus === "pending" ? "待定位" : "不可核验";
  if (reference.locator.kind === "excel") return `${reference.locator.sheet}!${reference.locator.range}`;
  if (reference.locator.kind === "image") return "图像区域";
  return reference.label;
}

function imageMaterialFor(asset: OnsiteAsset | undefined, materials: Material[]) {
  if (!asset?.materialId) return null;
  return materials.find((material): material is ImageMaterial => material.id === asset.materialId && material.kind === "image" && material.role !== "derived") ?? null;
}

export function ProductionOnsitePanel({ assets, materials, operatingEquipment, evidence, selectedTarget, onEvidenceSelect }: {
  assets: OnsiteAsset[];
  materials: Material[];
  operatingEquipment: OperatingEquipmentStatus[];
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const evidenceById = useMemo(() => new Map(evidence.map((item) => [item.id, item])), [evidence]);
  const imageAssets = useMemo(() => assets.filter((asset) => asset.kind === "image" || asset.kind === "supplement"), [assets]);
  const onsiteViews = useMemo<OnsiteView[]>(() => {
    const boundMaterialIds = new Set<string>();
    const boundViews = imageAssets.map((asset, index) => {
      const material = imageMaterialFor(asset, materials);
      if (material) boundMaterialIds.add(material.id);
      return {
        id: asset.id,
        label: asset.label || (material ? spatialViewLabel(material, index) : `现场区域 ${index + 1}`),
        zone: sceneZoneForMaterial(material),
        material,
        url: material ? materialPreviewUrl(material) : undefined,
        evidenceRefs: asset.evidenceRefs,
        reviewTargetId: asset.id,
      };
    });
    const materialViews = materials
      .filter((material): material is ImageMaterial => material.kind === "image" && material.role !== "derived" && isProjectPhoto(material) && !boundMaterialIds.has(material.id))
      .map((material, index) => ({
        id: `onsite-${material.id}`,
        label: spatialViewLabel(material, boundViews.length + index),
        zone: sceneZoneForMaterial(material),
        material,
        url: materialPreviewUrl(material),
        evidenceRefs: evidence.filter((item) => item.locator?.materialId === material.id).map((item) => item.id),
        reviewTargetId: `onsite-${material.id}`,
      }));
    return [...boundViews, ...materialViews];
  }, [evidence, imageAssets, materials]);
  const firstAvailableViewId = onsiteViews.find((view) => view.material && view.url)?.id ?? onsiteViews[0]?.id ?? "";
  const [selectedViewId, setSelectedViewId] = useState(firstAvailableViewId);
  const [viewMode, setViewMode] = useState<"space" | "image">("space");
  const selectedView = onsiteViews.find((view) => view.id === selectedViewId) ?? onsiteViews.find((view) => view.id === firstAvailableViewId) ?? onsiteViews[0];
  const selectedMaterial = selectedView?.material ?? null;
  const selectedMaterialUrl = selectedView?.url;
  const selectedProjectPhoto = selectedMaterial ? isProjectPhoto(selectedMaterial) : false;
  const selectedVisibleHeightRatio = selectedProjectPhoto ? PROJECT_PHOTO_VISIBLE_RATIO : 1;
  const selectedTargetMaterialId = useMemo(() => {
    const targetEvidenceRefs = selectedTarget?.evidenceRefs?.length
      ? selectedTarget.evidenceRefs
      : selectedTarget
        ? [selectedTarget.evidenceRef]
        : [];
    return targetEvidenceRefs.map((id) => evidenceById.get(id)?.locator?.materialId).find(Boolean);
  }, [evidenceById, selectedTarget]);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const viewportRef = useRef<HTMLDivElement>(null);
  const panRef = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);

  useEffect(() => {
    if (onsiteViews.some((item) => item.id === selectedViewId && item.material && item.url)) return;
    setSelectedViewId(firstAvailableViewId);
  }, [firstAvailableViewId, onsiteViews, selectedViewId]);

  useEffect(() => {
    if (!selectedTargetMaterialId) return;
    const matchingView = onsiteViews.find((item) => item.material?.id === selectedTargetMaterialId && item.url);
    if (matchingView) setSelectedViewId((current) => current === matchingView.id ? current : matchingView.id);
  }, [onsiteViews, selectedTargetMaterialId]);

  useEffect(() => setView({ scale: 1, x: 0, y: 0 }), [selectedView?.id, selectedMaterialUrl]);
  const zoom = (delta: number) => setView((current) => ({ ...current, scale: Math.max(1, Math.min(4, current.scale + delta)) }));
  useLockedWheel(viewportRef, (event) => zoom(event.deltaY < 0 ? 0.2 : -0.2));
  const reset = () => setView({ scale: 1, x: 0, y: 0 });
  const beginPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!selectedMaterialUrl) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    panRef.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, originX: view.x, originY: view.y };
  };
  const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const pan = panRef.current;
    if (!pan || pan.pointerId !== event.pointerId) return;
    setView((current) => ({ ...current, x: pan.originX + event.clientX - pan.startX, y: pan.originY + event.clientY - pan.startY }));
  };
  const endPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (panRef.current?.pointerId !== event.pointerId) return;
    panRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const assetEvidenceRefs = selectedView?.evidenceRefs.length
    ? selectedView.evidenceRefs
    : evidence.filter((item) => item.locator?.materialId === selectedMaterial?.id).map((item) => item.id);
  const assetTarget: ReviewEvidenceTarget | null = selectedMaterial && assetEvidenceRefs[0] ? {
    evidenceRef: assetEvidenceRefs[0],
    evidenceRefs: assetEvidenceRefs,
    dimensionId: "production",
    reviewTargetId: selectedView?.reviewTargetId ?? null,
    factVersionId: null,
  } : null;
  const availableImageCount = onsiteViews.filter((item) => item.material && item.url).length;
  const sceneEquipmentSummary = useMemo(() => operatingEquipment.reduce((summary, item) => ({
    total: summary.total + item.operatingQuantity,
    operating: summary.operating + (item.status === "operating" ? item.operatingQuantity : 0),
    maintenance: summary.maintenance + (item.status === "maintenance" ? item.operatingQuantity : 0),
    idle: summary.idle + (item.status === "idle" ? item.operatingQuantity : 0),
  }), { total: 0, operating: 0, maintenance: 0, idle: 0 }), [operatingEquipment]);
  const equipmentTarget = (item: OperatingEquipmentStatus): ReviewEvidenceTarget | null => item.evidenceRefs[0] ? ({ evidenceRef: item.evidenceRefs[0], evidenceRefs: item.evidenceRefs, dimensionId: "production", reviewTargetId: item.id, factVersionId: null }) : null;
  const sceneViews = useMemo<SiteSceneView[]>(() => onsiteViews.flatMap((item) => item.material && item.url ? [{
    id: item.id,
    label: item.label,
    url: item.url,
    alt: cleanVisualFileName(item.material.fileName),
    pixelWidth: item.material.pixelWidth,
    pixelHeight: item.material.pixelHeight,
    visibleHeightRatio: isProjectPhoto(item.material) ? PROJECT_PHOTO_VISIBLE_RATIO : 1,
    zone: item.zone,
  }] : []), [onsiteViews]);

  return (
    <section className="production-onsite-panel" aria-label={copy(locale, "3D site and equipment facts", "3D 现场与设备事实")} data-semantic-localized>
      <header><div><Icon name="production" /><strong>{copy(locale, "3D site", "3D 现场")}</strong></div><span>{copy(locale, "Areas", "区域")} {availableImageCount}/{onsiteViews.length}</span></header>
      <div className="production-onsite-layout">
        <div className="production-onsite-main" data-material-id={selectedMaterial?.id ?? ""} data-material-version-id={selectedMaterial?.versionId ?? ""}>
          <div className="production-onsite-navigation">
            <div className="production-onsite-tabs" role="group" aria-label={copy(locale, "Site areas", "现场区域")}>
              {onsiteViews.map((item) => {
                const material = item.material;
                const available = Boolean(material && item.url);
                return <button aria-pressed={item.id === selectedView?.id} className={item.id === selectedView?.id ? "is-active" : ""} disabled={!available} key={item.id} onClick={() => setSelectedViewId(item.id)} title={available ? formatCanonicalLabel(item.label, locale) : copy(locale, `${formatCanonicalLabel(item.label, locale)} pending`, `${item.label}待接入`)} type="button"><span>{formatCanonicalLabel(item.label, locale)}</span><small>{available ? `v${material?.versionId.match(/-v(\d+)$/)?.[1] ?? copy(locale, "current", "当前")}` : copy(locale, "Pending", "待接入")}</small></button>;
              })}
            </div>
            <div className="production-onsite-mode" role="group" aria-label={copy(locale, "Site display mode", "现场显示方式")}>
              <button aria-pressed={viewMode === "space"} onClick={() => setViewMode("space")} type="button">{copy(locale, "Spatial", "空间")}</button>
              <button aria-pressed={viewMode === "image"} onClick={() => setViewMode("image")} type="button">{copy(locale, "Source image", "原图")}</button>
            </div>
          </div>
          {viewMode === "space" ? (
            <SiteScenePreview
              activeViewId={selectedView?.id ?? sceneViews[0]?.id ?? ""}
              equipmentSummary={sceneEquipmentSummary}
              onViewSelect={setSelectedViewId}
              views={sceneViews}
            />
          ) : selectedMaterial && selectedMaterialUrl ? <>
            <div className="production-onsite-controls" role="group" aria-label={copy(locale, "Source-image zoom and reset controls", "现场原图缩放与重置")}><Button aria-label={copy(locale, "Zoom out source image", "缩小现场原图")} onClick={() => zoom(-0.25)} title={copy(locale, "Zoom out", "缩小")}>−</Button><span>{Math.round(view.scale * 100)}%</span><Button aria-label={copy(locale, "Zoom in source image", "放大现场原图")} onClick={() => zoom(0.25)} title={copy(locale, "Zoom in", "放大")}>＋</Button><Button aria-label={copy(locale, "Reset source-image view", "重置现场原图视图")} onClick={reset} title={copy(locale, "Reset view", "重置视图")}>{copy(locale, "Reset", "重置")}</Button></div>
            <div aria-label={copy(locale, "Source image; drag to pan and use the wheel to zoom", "现场原图；可拖动平移、滚轮缩放")} className="production-onsite-viewport" onPointerCancel={endPan} onPointerDown={beginPan} onPointerMove={movePan} onPointerUp={endPan} ref={viewportRef}>
              <figure className={`production-onsite-photo-frame ${selectedProjectPhoto ? "photo-frame" : ""}`} style={{ aspectRatio: `${selectedMaterial.pixelWidth} / ${selectedMaterial.pixelHeight * selectedVisibleHeightRatio}`, transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}>
                <img alt={cleanVisualFileName(selectedMaterial.fileName)} decoding="async" draggable={false} loading="lazy" src={selectedMaterialUrl} />
              </figure>
            </div>
          </> : <div className="production-onsite-empty" role="status"><Icon name="image" /><strong>{copy(locale, "Original for this angle has not been uploaded", "该角度原件尚未上传")}</strong><span>{formatCanonicalText(selectedMaterial?.fileName ?? selectedView?.label ?? "现场图片", locale)} · {copy(locale, "Remains pending; no public image is substituted.", "保持待补充，不使用公开图替代")}</span></div>}
          {selectedMaterial ? <button aria-label={copy(locale, `Open original material ${formatCanonicalText(selectedMaterial.fileName, locale)} and locate ${formatEvidenceLocator(evidenceById.get(assetEvidenceRefs[0])?.locator ?? null, evidenceById.get(assetEvidenceRefs[0])?.locationStatus ?? "pending", locale)}`, `打开${selectedMaterial.fileName}原始材料并定位${evidenceText(evidenceById.get(assetEvidenceRefs[0]))}`)} aria-pressed={sameReviewEvidenceTarget(assetTarget, selectedTarget)} className={`production-onsite-evidence ${sameReviewEvidenceTarget(assetTarget, selectedTarget) ? "is-selected" : ""}`} onClick={() => assetTarget && onEvidenceSelect(assetTarget)} type="button"><Icon name="link" /><span>{formatCanonicalText(selectedMaterial.fileName, locale)} · v{selectedMaterial.versionId.match(/-v(\d+)$/)?.[1] ?? copy(locale, "current", "当前")}</span></button> : <div />}
        </div>
        <aside className="production-onsite-equipment" aria-label={copy(locale, "Site equipment facts", "现场设备事实")}>
          <header><strong>{copy(locale, "Site equipment facts", "现场设备事实")}</strong><span>{operatingEquipment.reduce((sum, item) => sum + item.operatingQuantity, 0)} {copy(locale, "units", "台")}</span></header>
          <div className="operating-equipment-cards" role="list">
            {operatingEquipment.map((item) => {
              const target = equipmentTarget(item);
              const selected = sameReviewEvidenceTarget(target, selectedTarget);
              const reference = evidenceById.get(item.evidenceRefs[0]);
              return <article className={`operating-equipment-card ${selected ? "is-selected" : ""}`} id={`fact-${item.id}`} key={item.id} role="listitem"><header><span><strong>{formatCanonicalNarrative(displayBusinessName(item.equipment, "设备待核验"), locale)}</strong><small>{formatCanonicalNarrative(displayBusinessName(item.model, "型号待核验"), locale)}</small></span><b className={`operating-status status-${item.status}`}>{copy(locale, ({ operating: "Operating", maintenance: "Under maintenance", idle: "Idle" } as const)[item.status], equipmentStatusLabels[item.status])}</b></header><dl><div><dt>{copy(locale, "Operating quantity", "运营数量")}</dt><dd>{item.operatingQuantity} {copy(locale, "units", "台")}</dd></div><div><dt>{copy(locale, "Utilization", "利用率")}</dt><dd>{formatCanonicalNarrative(item.utilization, locale)}</dd></div><div><dt>{copy(locale, "Rated capacity", "额定产能")}</dt><dd>{formatCanonicalNarrative(item.ratedCapacity, locale)}</dd></div><div><dt>{copy(locale, "Process use", "工艺使用")}</dt><dd>{formatCanonicalNarrative(item.processUse, locale)}</dd></div></dl><button aria-pressed={selected} onClick={() => target && onEvidenceSelect(target)} type="button"><Icon name="link" /><span>{reference ? formatEvidenceLocator(reference.locator, reference.locationStatus, locale) : copy(locale, "No evidence reference", "无引用")}</span></button></article>;
            })}
          </div>
        </aside>
      </div>
    </section>
  );
}

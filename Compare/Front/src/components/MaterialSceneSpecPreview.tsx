import { useEffect, useMemo, useRef, useState } from "react";
import type { SceneHotspot, SceneObject, StoredSceneSpec } from "../contracts/materialIntelligence";
import { copy, formatCanonicalLabel, IMAGE_TO_3D_BOUNDARY, usePublicLocale } from "../lib/publicLocale";
import { Button } from "./ui";

type Projection = { x: number; y: number; scale: number; depth: number };

const REGION_LABELS: Record<string, string> = {
  factory: "厂区",
  equipment: "设备",
  process: "工艺",
};

function presetAngles(preset: StoredSceneSpec["spec"]["cameraPreset"]) {
  if (preset === "front") return { yaw: 0, pitch: 0 };
  if (preset === "side") return { yaw: Math.PI / 2, pitch: 0 };
  if (preset === "top") return { yaw: 0, pitch: -1.24 };
  return { yaw: -.55, pitch: .38 };
}

function project(object: SceneObject, width: number, height: number, yaw: number, pitch: number, zoom: number): Projection {
  const x = object.position.x;
  const y = object.position.y;
  const z = object.position.z;
  const rotatedX = x * Math.cos(yaw) - z * Math.sin(yaw);
  const yawDepth = x * Math.sin(yaw) + z * Math.cos(yaw);
  const rotatedY = y * Math.cos(pitch) - yawDepth * Math.sin(pitch);
  const depth = y * Math.sin(pitch) + yawDepth * Math.cos(pitch);
  const perspective = 1 / Math.max(5, 18 + depth);
  const scale = Math.min(width, height) * 3.6 * zoom * perspective;
  return { x: width / 2 + rotatedX * scale, y: height * .58 - rotatedY * scale, scale, depth };
}

function objectColor(kind: SceneObject["kind"], active: boolean) {
  if (active) return "#2563eb";
  if (kind === "marker") return "#d97706";
  if (kind === "plane") return "#8a8f98";
  if (kind === "label") return "#4f46e5";
  return "#3f4650";
}

export function MaterialSceneSpecPreview({ scene, activeAnchorId, onHotspotActivate }: {
  scene: StoredSceneSpec;
  activeAnchorId: string | null;
  onHotspotActivate: (sourceAnchorId: string) => void;
}) {
  const locale = usePublicLocale();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const initial = presetAngles(scene.spec.cameraPreset);
  const [yaw, setYaw] = useState(initial.yaw);
  const [pitch, setPitch] = useState(initial.pitch);
  const [zoom, setZoom] = useState(1);
  const [size, setSize] = useState({ width: 640, height: 300 });

  useEffect(() => {
    const next = presetAngles(scene.spec.cameraPreset);
    setYaw(next.yaw);
    setPitch(next.pitch);
    setZoom(1);
  }, [scene.sceneId, scene.spec.cameraPreset]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      setSize({ width: Math.max(320, Math.round(entry.contentRect.width)), height: Math.max(240, Math.round(entry.contentRect.height)) });
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  const objectById = useMemo(() => new Map(scene.spec.objects.map((item) => [item.id, item])), [scene.spec.objects]);
  const projections = useMemo(() => new Map(scene.spec.objects.map((item) => [item.id, project(item, size.width, size.height, yaw, pitch, zoom)])), [pitch, scene.spec.objects, size.height, size.width, yaw, zoom]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size.width * ratio;
    canvas.height = size.height * ratio;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const gradient = context.createLinearGradient(0, 0, 0, size.height);
    gradient.addColorStop(0, "#f5f6f7");
    gradient.addColorStop(1, "#d9dde1");
    context.fillStyle = gradient;
    context.fillRect(0, 0, size.width, size.height);
    context.strokeStyle = "rgba(71, 78, 88, .16)";
    for (let row = 0; row < 8; row += 1) {
      const y = size.height * .58 + row * 18;
      context.beginPath(); context.moveTo(0, y); context.lineTo(size.width, y); context.stroke();
    }
    const activeObjectIds = new Set(scene.spec.hotspots.filter((item) => item.sourceAnchorId === activeAnchorId).map((item) => item.objectId));
    const sorted = [...scene.spec.objects].sort((left, right) => (projections.get(right.id)?.depth ?? 0) - (projections.get(left.id)?.depth ?? 0));
    for (const object of sorted) {
      const point = projections.get(object.id);
      if (!point) continue;
      const width = Math.max(16, object.size.x * point.scale);
      const height = Math.max(12, object.size.y * point.scale);
      const color = objectColor(object.kind, activeObjectIds.has(object.id));
      context.save();
      context.translate(point.x, point.y);
      context.rotate((object.rotation.z * Math.PI) / 180);
      context.fillStyle = `${color}cc`;
      context.strokeStyle = activeObjectIds.has(object.id) ? "#ffffff" : "rgba(255,255,255,.75)";
      context.lineWidth = activeObjectIds.has(object.id) ? 3 : 1;
      if (object.kind === "marker") {
        context.beginPath(); context.arc(0, 0, Math.max(8, width / 2), 0, Math.PI * 2); context.fill(); context.stroke();
      } else {
        context.fillRect(-width / 2, -height, width, height);
        context.strokeRect(-width / 2, -height, width, height);
        context.fillStyle = `${color}66`;
        context.beginPath(); context.moveTo(-width / 2, -height); context.lineTo(-width / 2 + width * .22, -height - width * .12); context.lineTo(width / 2 + width * .22, -height - width * .12); context.lineTo(width / 2, -height); context.closePath(); context.fill();
      }
      context.restore();
      context.fillStyle = "#20242a";
      context.font = "600 12px system-ui";
      context.textAlign = "center";
      context.fillText(formatCanonicalLabel(REGION_LABELS[object.regionId] ?? object.regionId, locale), point.x, point.y + 18);
    }
  }, [activeAnchorId, locale, projections, scene.spec.hotspots, scene.spec.objects, size.height, size.width]);

  const hotspotStyle = (hotspot: SceneHotspot) => {
    const object = objectById.get(hotspot.objectId);
    const point = projections.get(hotspot.objectId);
    if (!object || !point) return { display: "none" };
    return { left: `${point.x}px`, top: `${point.y - Math.max(12, object.size.y * point.scale) - 10}px` };
  };

  return <section className="material-scene-spec" aria-label={copy(locale, "Controlled declarative spatial preview", "受控声明式空间示意")} data-semantic-localized>
    <header><div><strong>{copy(locale, "Controlled spatial preview", "受控空间示意")}</strong><span>{scene.spec.cameraPreset} · {scene.spec.objects.length} {copy(locale, "objects", "对象")} · {scene.spec.hotspots.length} {copy(locale, "hotspots", "热点")}</span></div><div><Button aria-label={copy(locale, "Rotate scene left", "场景左转")} onClick={() => setYaw((value) => value - .18)}>{copy(locale, "Left", "左转")}</Button><Button aria-label={copy(locale, "Rotate scene right", "场景右转")} onClick={() => setYaw((value) => value + .18)}>{copy(locale, "Right", "右转")}</Button><Button aria-label={copy(locale, "Zoom scene in", "场景放大")} onClick={() => setZoom((value) => Math.min(2, value + .15))}>＋</Button><Button aria-label={copy(locale, "Zoom scene out", "场景缩小")} onClick={() => setZoom((value) => Math.max(.55, value - .15))}>－</Button><Button onClick={() => { const next = presetAngles(scene.spec.cameraPreset); setYaw(next.yaw); setPitch(next.pitch); setZoom(1); }}>{copy(locale, "Reset", "重置")}</Button></div></header>
    <div className="material-scene-stage">
      <canvas aria-label={copy(locale, "Spatial preview drawn only from the SceneSpec allowlist and numeric values", "仅按 SceneSpec 枚举与数值绘制的空间示意")} ref={canvasRef} />
      {scene.spec.hotspots.map((hotspot) => <button aria-pressed={hotspot.sourceAnchorId === activeAnchorId} className={hotspot.sourceAnchorId === activeAnchorId ? "is-active" : ""} key={hotspot.id} onClick={() => onHotspotActivate(hotspot.sourceAnchorId)} style={hotspotStyle(hotspot)} type="button"><span />{formatCanonicalLabel(REGION_LABELS[hotspot.regionId] ?? hotspot.regionId, locale)}</button>)}
    </div>
    <footer><span>{copy(locale, "Declarative SceneSpec · model code is never executed", "声明式 SceneSpec · 不执行模型代码")}</span><b>{copy(locale, "Synthetic spatial preview, not a real 3D scan or 3DGS reconstruction", "合成空间示意，不是真实三维扫描 / 3DGS")}</b><small>{IMAGE_TO_3D_BOUNDARY[locale]}</small></footer>
  </section>;
}

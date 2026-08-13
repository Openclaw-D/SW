import { useEffect, useMemo, useRef, useState } from "react";
import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
} from "react";
import { useLockedWheel } from "../lib/useLockedWheel";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, IMAGE_TO_3D_BOUNDARY, usePublicLocale } from "../lib/publicLocale";
import { Button } from "./ui";
import "./SiteScenePreview.css";

type Vec3 = [number, number, number];
type Rgb = [number, number, number];
type CameraPreset = "orbit" | "top" | "eye";
type SceneStatus = "loading" | "ready" | "empty" | "error";
type SceneAreaId = "raw" | "equipment" | "finished";
type ProductionPhase = "raw" | "processing" | "finished";
export type SiteSceneLevelId = "L1" | "L2" | "L3" | "L4";

export type SiteSceneZoneId = "overview" | SceneAreaId | "process" | "people";

export interface SiteSceneView {
  id: string;
  label: string;
  url: string;
  alt: string;
  pixelWidth: number;
  pixelHeight: number;
  visibleHeightRatio: number;
  zone: SiteSceneZoneId;
}

interface CameraState {
  yaw: number;
  pitch: number;
  distance: number;
  preset: CameraPreset;
}

interface GeometryBuffers {
  positions: number[];
  normals: number[];
  colors: number[];
}

interface SceneGeometry {
  positions: Float32Array;
  normals: Float32Array;
  colors: Float32Array;
  vertexCount: number;
}

interface WebGlRenderer {
  gl: WebGLRenderingContext;
  program: WebGLProgram;
  positionBuffer: WebGLBuffer;
  normalBuffer: WebGLBuffer;
  colorBuffer: WebGLBuffer;
  positionLocation: number;
  normalLocation: number;
  colorLocation: number;
  viewProjectionLocation: WebGLUniformLocation;
}

interface ProjectedHotspot {
  id: SceneAreaId;
  label: string;
  x: number;
  y: number;
  visible: boolean;
}

interface EquipmentSummary {
  total: number;
  operating: number;
  maintenance: number;
  idle: number;
}

const DEFAULT_CAMERA: CameraState = { yaw: -0.72, pitch: 0.52, distance: 18, preset: "orbit" };
const TOP_CAMERA: CameraState = { yaw: -0.64, pitch: 1.26, distance: 19.5, preset: "top" };
const EYE_CAMERA: CameraState = { yaw: -0.82, pitch: 0.24, distance: 17.2, preset: "eye" };
const MIN_DISTANCE = 10.5;
const MAX_DISTANCE = 26;
const GROUND_Y = 0;
const MIN_CAMERA_CLEARANCE = 0.35;
const LEVEL_HEIGHT = 4.4;
const PRODUCTION_CYCLE_SECONDS = 18;

const SCENE_LEVELS: Array<{
  id: SiteSceneLevelId;
  label: string;
  available: boolean;
  renderOrigin: Vec3;
}> = [
  { id: "L1", label: "L1 地面层", available: true, renderOrigin: [0, 0, 0] },
  { id: "L2", label: "L2", available: false, renderOrigin: [0, LEVEL_HEIGHT, 0] },
  { id: "L3", label: "L3", available: false, renderOrigin: [0, LEVEL_HEIGHT * 2, 0] },
  { id: "L4", label: "L4", available: false, renderOrigin: [0, LEVEL_HEIGHT * 3, 0] },
];

const SCENE_AREAS: Array<{
  id: SceneAreaId;
  label: string;
  center: Vec3;
  hotspot: Vec3;
  color: Rgb;
}> = [
  { id: "raw", label: "材料", center: [-5.15, 0, 2.15], hotspot: [-5.15, 1.75, 2.15], color: [0.48, 0.36, 0.29] },
  { id: "equipment", label: "设备", center: [-0.55, 0, 0.75], hotspot: [-0.55, 2.25, 0.75], color: [0.25, 0.39, 0.46] },
  { id: "finished", label: "成品", center: [5.15, 0, -2.05], hotspot: [5.15, 2.05, -2.05], color: [0.35, 0.45, 0.39] },
];

const VERTEX_SHADER = `
  attribute vec3 aPosition;
  attribute vec3 aNormal;
  attribute vec3 aColor;
  uniform mat4 uViewProjection;
  varying vec3 vColor;
  varying float vLight;
  varying float vFog;

  void main() {
    vec4 clipPosition = uViewProjection * vec4(aPosition, 1.0);
    gl_Position = clipPosition;
    vec3 lightDirection = normalize(vec3(-0.45, 0.88, 0.52));
    vLight = 0.42 + 0.58 * max(dot(normalize(aNormal), lightDirection), 0.0);
    vColor = aColor;
    vFog = smoothstep(0.58, 1.0, clipPosition.z / clipPosition.w);
  }
`;

const FRAGMENT_SHADER = `
  precision mediump float;
  varying vec3 vColor;
  varying float vLight;
  varying float vFog;

  void main() {
    vec3 litColor = vColor * vLight;
    gl_FragColor = vec4(mix(litColor, vec3(0.88, 0.90, 0.89), vFog * 0.34), 1.0);
  }
`;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}

function add(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function interpolatePosition(from: Vec3, to: Vec3, progress: number): Vec3 {
  return [
    from[0] + (to[0] - from[0]) * progress,
    from[1] + (to[1] - from[1]) * progress,
    from[2] + (to[2] - from[2]) * progress,
  ];
}

function smoothStep(progress: number) {
  const value = clamp(progress, 0, 1);
  return value * value * (3 - 2 * value);
}

function sceneAreaForZone(zone: SiteSceneZoneId): SceneAreaId | null {
  if (zone === "overview") return null;
  return zone === "process" || zone === "people" ? "equipment" : zone;
}

function sceneArea(id: SceneAreaId) {
  return SCENE_AREAS.find((area) => area.id === id)!;
}

function displayAreas(views: SiteSceneView[]) {
  return views.length ? SCENE_AREAS.map((area) => area.id) : [];
}

function subtract(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function scale(vector: Vec3, amount: number): Vec3 {
  return [vector[0] * amount, vector[1] * amount, vector[2] * amount];
}

function dot(a: Vec3, b: Vec3) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalize(vector: Vec3): Vec3 {
  const length = Math.hypot(vector[0], vector[1], vector[2]) || 1;
  return scale(vector, 1 / length);
}

function multiplyMatrices(a: Float32Array, b: Float32Array) {
  const result = new Float32Array(16);
  for (let column = 0; column < 4; column += 1) {
    for (let row = 0; row < 4; row += 1) {
      result[column * 4 + row] =
        a[row] * b[column * 4]
        + a[4 + row] * b[column * 4 + 1]
        + a[8 + row] * b[column * 4 + 2]
        + a[12 + row] * b[column * 4 + 3];
    }
  }
  return result;
}

function perspectiveMatrix(fieldOfView: number, aspect: number, near: number, far: number) {
  const f = 1 / Math.tan(fieldOfView / 2);
  const rangeInverse = 1 / (near - far);
  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (near + far) * rangeInverse, -1,
    0, 0, near * far * 2 * rangeInverse, 0,
  ]);
}

function lookAtMatrix(eye: Vec3, target: Vec3, up: Vec3) {
  const zAxis = normalize(subtract(eye, target));
  const xAxis = normalize(cross(up, zAxis));
  const yAxis = cross(zAxis, xAxis);
  return new Float32Array([
    xAxis[0], yAxis[0], zAxis[0], 0,
    xAxis[1], yAxis[1], zAxis[1], 0,
    xAxis[2], yAxis[2], zAxis[2], 0,
    -dot(xAxis, eye), -dot(yAxis, eye), -dot(zAxis, eye), 1,
  ]);
}

function cameraEye(camera: CameraState): Vec3 {
  const target: Vec3 = [0, 0.65, 0];
  const horizontal = Math.cos(camera.pitch) * camera.distance;
  return [
    target[0] + Math.sin(camera.yaw) * horizontal,
    Math.max(GROUND_Y + MIN_CAMERA_CLEARANCE, target[1] + Math.sin(camera.pitch) * camera.distance),
    target[2] + Math.cos(camera.yaw) * horizontal,
  ];
}

function cameraViewProjection(camera: CameraState, aspect: number) {
  const target: Vec3 = [0, 0.65, 0];
  const eye = cameraEye(camera);
  return multiplyMatrices(
    perspectiveMatrix(Math.PI / 4.1, aspect, 0.1, 80),
    lookAtMatrix(eye, target, [0, 1, 0]),
  );
}

function transformPoint(matrix: Float32Array, point: Vec3) {
  const [x, y, z] = point;
  return [
    matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
    matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
    matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    matrix[3] * x + matrix[7] * y + matrix[11] * z + matrix[15],
  ] as const;
}

function rotateY(point: Vec3, radians: number): Vec3 {
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  return [point[0] * cosine - point[2] * sine, point[1], point[0] * sine + point[2] * cosine];
}

function shade(color: Rgb, amount: number): Rgb {
  return color.map((component) => clamp(component * amount, 0, 1)) as Rgb;
}

function pushVertex(buffers: GeometryBuffers, position: Vec3, normal: Vec3, color: Rgb) {
  buffers.positions.push(...position);
  buffers.normals.push(...normal);
  buffers.colors.push(...color);
}

function addBox(buffers: GeometryBuffers, center: Vec3, size: Vec3, color: Rgb, rotation = 0) {
  const half: Vec3 = [size[0] / 2, size[1] / 2, size[2] / 2];
  const local: Vec3[] = [
    [-half[0], -half[1], -half[2]], [half[0], -half[1], -half[2]],
    [half[0], half[1], -half[2]], [-half[0], half[1], -half[2]],
    [-half[0], -half[1], half[2]], [half[0], -half[1], half[2]],
    [half[0], half[1], half[2]], [-half[0], half[1], half[2]],
  ];
  const vertices = local.map((point) => add(rotateY(point, rotation), center));
  const faces: Array<{ indices: number[]; normal: Vec3; tint: number }> = [
    { indices: [4, 5, 6, 4, 6, 7], normal: [0, 0, 1], tint: 1.04 },
    { indices: [1, 0, 3, 1, 3, 2], normal: [0, 0, -1], tint: 0.78 },
    { indices: [0, 4, 7, 0, 7, 3], normal: [-1, 0, 0], tint: 0.86 },
    { indices: [5, 1, 2, 5, 2, 6], normal: [1, 0, 0], tint: 0.96 },
    { indices: [3, 7, 6, 3, 6, 2], normal: [0, 1, 0], tint: 1.16 },
    { indices: [0, 1, 5, 0, 5, 4], normal: [0, -1, 0], tint: 0.68 },
  ];
  for (const face of faces) {
    const normal = rotateY(face.normal, rotation);
    for (const index of face.indices) pushVertex(buffers, vertices[index], normal, shade(color, face.tint));
  }
}

function mixColor(from: Rgb, to: Rgb, progress: number): Rgb {
  return [
    from[0] + (to[0] - from[0]) * progress,
    from[1] + (to[1] - from[1]) * progress,
    from[2] + (to[2] - from[2]) * progress,
  ];
}

function addRouteSegment(buffers: GeometryBuffers, from: Vec3, to: Vec3) {
  const deltaX = to[0] - from[0];
  const deltaZ = to[2] - from[2];
  const length = Math.hypot(deltaX, deltaZ);
  addBox(
    buffers,
    [(from[0] + to[0]) / 2, 0.085, (from[2] + to[2]) / 2],
    [length, 0.055, 0.14],
    [0.56, 0.61, 0.59],
    Math.atan2(deltaZ, deltaX),
  );
}

function productionMaterialMotion(animationSeconds: number) {
  const cycle = ((animationSeconds % PRODUCTION_CYCLE_SECONDS) + PRODUCTION_CYCLE_SECONDS) % PRODUCTION_CYCLE_SECONDS;
  const raw = sceneArea("raw").center;
  const equipment = sceneArea("equipment").center;
  const finished = sceneArea("finished").center;
  const visibility = cycle < 0.55 ? smoothStep(cycle / 0.55) : cycle > 17.35 ? smoothStep((18 - cycle) / 0.65) : 1;
  if (cycle < 3) return { phase: "raw" as const, position: raw, color: [0.62, 0.39, 0.22] as Rgb, scale: visibility };
  if (cycle < 6) {
    const progress = smoothStep((cycle - 3) / 3);
    return { phase: "raw" as const, position: interpolatePosition(raw, equipment, progress), color: mixColor([0.62, 0.39, 0.22], [0.82, 0.59, 0.22], progress), scale: visibility };
  }
  if (cycle < 11) return { phase: "processing" as const, position: [equipment[0], 0.05 + Math.sin(cycle * 2.2) * 0.025, equipment[2]] as Vec3, color: [0.82, 0.59, 0.22] as Rgb, scale: visibility };
  if (cycle < 14) {
    const progress = smoothStep((cycle - 11) / 3);
    return { phase: "processing" as const, position: interpolatePosition(equipment, finished, progress), color: mixColor([0.82, 0.59, 0.22], [0.58, 0.67, 0.70], progress), scale: visibility };
  }
  return { phase: "finished" as const, position: finished, color: [0.58, 0.67, 0.70] as Rgb, scale: visibility };
}

function addMovingMaterial(buffers: GeometryBuffers, animationSeconds: number) {
  const material = productionMaterialMotion(animationSeconds);
  const scaleValue = Math.max(0.02, material.scale);
  const [x, y, z] = material.position;
  addBox(buffers, [x, 0.32 + y, z], [0.46 * scaleValue, 0.40 * scaleValue, 0.38 * scaleValue], material.color, animationSeconds * 0.35);
  addBox(buffers, [x, 0.59 + y, z], [0.24 * scaleValue, 0.14 * scaleValue, 0.24 * scaleValue], shade(material.color, 1.12), animationSeconds * 0.35);
  return material.phase;
}

function operatorMotion(animationSeconds: number) {
  const cycle = ((animationSeconds % 24) + 24) % 24;
  const equipment = sceneArea("equipment").center;
  const machineA: Vec3 = [equipment[0] - 1.18, 0, equipment[2] - 0.52];
  const machineB: Vec3 = [equipment[0], 0, equipment[2] - 0.52];
  const machineC: Vec3 = [equipment[0] + 1.18, 0, equipment[2] - 0.52];
  const stationA: Vec3 = [machineA[0], 0, equipment[2] - 1.34];
  const stationB: Vec3 = [machineB[0], 0, equipment[2] - 1.34];
  const stationC: Vec3 = [machineC[0], 0, equipment[2] - 1.34];
  if (cycle < 4) return { position: stationA, target: machineA, walking: false, phase: cycle / 4 };
  if (cycle < 6) return { position: interpolatePosition(stationA, stationB, smoothStep((cycle - 4) / 2)), target: stationB, walking: true, phase: (cycle - 4) / 2 };
  if (cycle < 10) return { position: stationB, target: machineB, walking: false, phase: (cycle - 6) / 4 };
  if (cycle < 12) return { position: interpolatePosition(stationB, stationC, smoothStep((cycle - 10) / 2)), target: stationC, walking: true, phase: (cycle - 10) / 2 };
  if (cycle < 16) return { position: stationC, target: machineC, walking: false, phase: (cycle - 12) / 4 };
  if (cycle < 20) return { position: interpolatePosition(stationC, stationA, smoothStep((cycle - 16) / 4)), target: stationA, walking: true, phase: (cycle - 16) / 4 };
  return { position: stationA, target: machineA, walking: false, phase: (cycle - 20) / 4 };
}

function addOperator(buffers: GeometryBuffers, animationSeconds: number) {
  const motion = operatorMotion(animationSeconds);
  const direction = Math.atan2(motion.target[2] - motion.position[2], motion.target[0] - motion.position[0]) || -Math.PI / 2;
  const step = motion.walking ? Math.sin(motion.phase * Math.PI * 6) : Math.sin(animationSeconds * 0.7) * 0.08;
  const armSwing = motion.walking ? step * 0.24 : Math.sin(motion.phase * Math.PI) * 0.08;
  const [x, , z] = motion.position;
  addBox(buffers, [x, 0.86, z], [0.38, 0.82, 0.26], [0.92, 0.55, 0.12], direction);
  addBox(buffers, [x, 1.42, z], [0.30, 0.30, 0.30], [0.68, 0.50, 0.38], direction);
  addBox(buffers, [x, 1.01, z + 0.135], [0.30, 0.09, 0.035], [0.92, 0.90, 0.62], direction);
  addBox(buffers, [x - 0.11, 0.28 + Math.max(0, step) * 0.025, z], [0.12, 0.54, 0.14], [0.15, 0.18, 0.20], direction + step * 0.18);
  addBox(buffers, [x + 0.11, 0.28 + Math.max(0, -step) * 0.025, z], [0.12, 0.54, 0.14], [0.15, 0.18, 0.20], direction - step * 0.18);
  addBox(buffers, [x - 0.24, 0.88, z], [0.11, 0.56, 0.12], [0.92, 0.55, 0.12], direction - armSwing);
  addBox(buffers, [x + 0.24, 0.88, z], [0.11, 0.56, 0.12], [0.92, 0.55, 0.12], direction + armSwing);
}

function emptySceneGeometry(): SceneGeometry {
  return { positions: new Float32Array(), normals: new Float32Array(), colors: new Float32Array(), vertexCount: 0 };
}

function createSceneGeometry(
  activeLevel: SiteSceneLevelId,
  activeZone: SiteSceneZoneId,
  equipmentSummary: EquipmentSummary,
  visibleAreas: SceneAreaId[],
  animationSeconds = 0,
): SceneGeometry {
  const level = SCENE_LEVELS.find((item) => item.id === activeLevel);
  if (!level?.available || activeLevel !== "L1") return emptySceneGeometry();
  const buffers: GeometryBuffers = { positions: [], normals: [], colors: [] };
  const observed = new Set(visibleAreas);
  const selectedArea = sceneAreaForZone(activeZone);
  addBox(buffers, [0, -0.18, 0], [15.2, 0.32, 10.2], [0.63, 0.66, 0.64]);

  for (let x = -6; x <= 6; x += 2) addBox(buffers, [x, 0.015, 0], [0.025, 0.03, 9.6], [0.45, 0.49, 0.47]);
  for (let z = -4; z <= 4; z += 2) addBox(buffers, [0, 0.018, z], [14.6, 0.032, 0.025], [0.45, 0.49, 0.47]);

  for (const x of [-7.1, 0, 7.1]) {
    for (const z of [-4.55, 4.55]) addBox(buffers, [x, 1.85, z], [0.18, 3.7, 0.18], [0.36, 0.40, 0.40]);
  }
  for (const z of [-4.55, 0, 4.55]) {
    for (const x of [-7.1, 7.1]) addBox(buffers, [x, 1.85, z], [0.18, 3.7, 0.18], [0.36, 0.40, 0.40]);
  }
  for (const z of [-4.55, 4.55]) addBox(buffers, [0, 3.62, z], [14.35, 0.18, 0.18], [0.30, 0.35, 0.35]);
  for (const x of [-7.1, -3.55, 0, 3.55, 7.1]) addBox(buffers, [x, 3.58, 0], [0.16, 0.16, 9.15], [0.34, 0.39, 0.39]);

  addBox(buffers, [0, 1.25, -4.48], [14.05, 2.5, 0.10], [0.51, 0.56, 0.54]);
  for (const x of [-7.02, 7.02]) {
    addBox(buffers, [x, 1.05, -1.55], [0.10, 2.1, 5.65], [0.53, 0.58, 0.56]);
  }
  for (const x of [-5.3, 5.3]) addBox(buffers, [x, 1.05, 4.48], [3.45, 2.1, 0.10], [0.53, 0.58, 0.56]);
  addBox(buffers, [0, 3.70, 0], [0.16, 0.12, 9.0], [0.30, 0.35, 0.35]);

  for (const area of SCENE_AREAS) {
    if (!observed.has(area.id)) continue;
    const selected = area.id === selectedArea;
    const padSize: Vec3 = area.id === "equipment" ? [3.8, 0.10, 3.15] : [2.55, 0.10, 2.25];
    addBox(buffers, [area.center[0], 0.025, area.center[2]], padSize, selected ? [0.18, 0.43, 0.59] : shade(area.color, 0.78));
  }

  if (observed.has("raw") && observed.has("equipment") && observed.has("finished")) {
    addRouteSegment(buffers, sceneArea("raw").center, sceneArea("equipment").center);
    addRouteSegment(buffers, sceneArea("equipment").center, sceneArea("finished").center);
  }

  if (observed.has("raw")) {
    const raw = sceneArea("raw").center;
    addBox(buffers, [raw[0], 0.18, raw[2]], [2.1, 0.28, 1.65], [0.39, 0.30, 0.24]);
    for (const row of [-0.5, 0, 0.5]) {
      for (const column of [-0.62, 0, 0.62]) {
        addBox(buffers, [raw[0] + column, 0.62, raw[2] + row], [0.48, 0.72 + (column === 0 ? 0.18 : 0), 0.38], [0.55, 0.41, 0.30]);
      }
    }
  }

  if (observed.has("equipment")) {
    const equipment = sceneArea("equipment").center;
    const machineCount = clamp(Math.round(equipmentSummary.total || 1), 1, 6);
    const pulse = 0.5 + Math.sin(animationSeconds * 2.8) * 0.5;
    const total = Math.max(1, equipmentSummary.total);
    const operatingRatio = equipmentSummary.operating / total;
    const maintenanceRatio = equipmentSummary.maintenance / total;
    for (let index = 0; index < machineCount; index += 1) {
      const column = index % 3;
      const row = Math.floor(index / 3);
      const x = equipment[0] - 1.18 + column * 1.18;
      const z = equipment[2] - 0.52 + row * 1.10;
      addBox(buffers, [x, 0.72, z], [0.88, 1.35, 0.82], [0.31, 0.44, 0.50]);
      addBox(buffers, [x, 1.47, z], [0.60, 0.18, 0.54], [0.51, 0.62, 0.66]);
      addBox(buffers, [x, 0.82, z + 0.43], [0.44, 0.48, 0.04], [0.14, 0.20, 0.22]);
      const statusPosition = (index + 0.5) / machineCount;
      const isOperating = statusPosition <= operatingRatio;
      const isMaintenance = !isOperating && statusPosition <= operatingRatio + maintenanceRatio;
      const indicatorColor: Rgb = isOperating
        ? [0.22 + pulse * 0.06, 0.78 + pulse * 0.08, 0.34]
        : isMaintenance ? [0.90, 0.58, 0.18] : [0.58, 0.62, 0.60];
      const indicatorSize = isOperating ? 0.075 + pulse * 0.012 : 0.078;
      addBox(buffers, [x + 0.28, 1.50, z + 0.31], [indicatorSize, indicatorSize, 0.07], indicatorColor);
      if (isOperating) {
        const spindleOffset = Math.sin(animationSeconds * 2.4 + index) * 0.018;
        addBox(buffers, [x, 0.88 + spindleOffset, z + 0.455], [0.27, 0.10, 0.035], [0.56, 0.74, 0.78]);
      }
    }
  }

  if (observed.has("equipment")) addOperator(buffers, animationSeconds);

  if (observed.has("finished")) {
    const finished = sceneArea("finished").center;
    for (const xOffset of [-0.68, 0.68]) {
      addBox(buffers, [finished[0] + xOffset, 1.02, finished[2]], [0.92, 1.92, 0.48], [0.32, 0.42, 0.36]);
      for (const y of [0.46, 1.02, 1.58]) addBox(buffers, [finished[0] + xOffset, y, finished[2] + 0.31], [0.78, 0.12, 0.16], [0.56, 0.64, 0.58]);
    }
    for (const xOffset of [-0.68, 0, 0.68]) addBox(buffers, [finished[0] + xOffset, 0.30, finished[2] + 0.72], [0.46, 0.50, 0.42], [0.45, 0.55, 0.47]);
  }

  if (observed.has("raw") && observed.has("equipment") && observed.has("finished")) addMovingMaterial(buffers, animationSeconds);

  const positions = new Float32Array(buffers.positions);
  for (let index = 0; index < positions.length; index += 3) {
    positions[index] += level.renderOrigin[0];
    positions[index + 1] += level.renderOrigin[1];
    positions[index + 2] += level.renderOrigin[2];
  }
  return {
    positions,
    normals: new Float32Array(buffers.normals),
    colors: new Float32Array(buffers.colors),
    vertexCount: buffers.positions.length / 3,
  };
}

function compileShader(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("WebGL shader unavailable");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const reason = gl.getShaderInfoLog(shader) ?? "shader compile failed";
    gl.deleteShader(shader);
    throw new Error(reason);
  }
  return shader;
}

function createRenderer(canvas: HTMLCanvasElement): WebGlRenderer {
  const gl = canvas.getContext("webgl", { antialias: true, alpha: false });
  if (!gl) throw new Error("WebGL unavailable");
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
  const program = gl.createProgram();
  if (!program) throw new Error("WebGL program unavailable");
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? "program link failed");
  const positionBuffer = gl.createBuffer();
  const normalBuffer = gl.createBuffer();
  const colorBuffer = gl.createBuffer();
  const viewProjectionLocation = gl.getUniformLocation(program, "uViewProjection");
  if (!positionBuffer || !normalBuffer || !colorBuffer || !viewProjectionLocation) throw new Error("WebGL buffer unavailable");
  gl.enable(gl.DEPTH_TEST);
  gl.enable(gl.CULL_FACE);
  gl.cullFace(gl.BACK);
  gl.clearColor(0.88, 0.90, 0.89, 1);
  return {
    gl,
    program,
    positionBuffer,
    normalBuffer,
    colorBuffer,
    positionLocation: gl.getAttribLocation(program, "aPosition"),
    normalLocation: gl.getAttribLocation(program, "aNormal"),
    colorLocation: gl.getAttribLocation(program, "aColor"),
    viewProjectionLocation,
  };
}

function bindAttribute(gl: WebGLRenderingContext, buffer: WebGLBuffer, location: number, data: Float32Array) {
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
  gl.enableVertexAttribArray(location);
  gl.vertexAttribPointer(location, 3, gl.FLOAT, false, 0, 0);
}

function renderScene(
  renderer: WebGlRenderer,
  camera: CameraState,
  activeLevel: SiteSceneLevelId,
  activeZone: SiteSceneZoneId,
  equipmentSummary: EquipmentSummary,
  visibleAreas: SceneAreaId[],
  width: number,
  height: number,
  animationSeconds = 0,
) {
  const { gl } = renderer;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.max(1, Math.round(width * ratio));
  const pixelHeight = Math.max(1, Math.round(height * ratio));
  if (gl.canvas.width !== pixelWidth || gl.canvas.height !== pixelHeight) {
    gl.canvas.width = pixelWidth;
    gl.canvas.height = pixelHeight;
  }
  gl.viewport(0, 0, pixelWidth, pixelHeight);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  gl.useProgram(renderer.program);
  const geometry = createSceneGeometry(activeLevel, activeZone, equipmentSummary, visibleAreas, animationSeconds);
  bindAttribute(gl, renderer.positionBuffer, renderer.positionLocation, geometry.positions);
  bindAttribute(gl, renderer.normalBuffer, renderer.normalLocation, geometry.normals);
  bindAttribute(gl, renderer.colorBuffer, renderer.colorLocation, geometry.colors);
  const viewProjection = cameraViewProjection(camera, width / Math.max(1, height));
  gl.uniformMatrix4fv(renderer.viewProjectionLocation, false, viewProjection);
  gl.drawArrays(gl.TRIANGLES, 0, geometry.vertexCount);
  return viewProjection;
}

function projectedHotspots(viewProjection: Float32Array, width: number, height: number, visibleAreas: SceneAreaId[]): ProjectedHotspot[] {
  const observed = new Set(visibleAreas);
  return SCENE_AREAS.filter((area) => observed.has(area.id)).map((area) => {
    const [clipX, clipY, clipZ, clipW] = transformPoint(viewProjection, area.hotspot);
    const visible = clipW > 0 && clipZ / clipW > -1 && clipZ / clipW < 1;
    return {
      id: area.id,
      label: area.label,
      x: (clipX / clipW * 0.5 + 0.5) * width,
      y: (1 - (clipY / clipW * 0.5 + 0.5)) * height,
      visible,
    };
  });
}

export function SiteScenePreview({ views, activeViewId, onViewSelect, equipmentSummary }: {
  views: SiteSceneView[];
  activeViewId: string;
  onViewSelect: (viewId: string) => void;
  equipmentSummary: EquipmentSummary;
}) {
  const locale = usePublicLocale();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<WebGlRenderer | null>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; yaw: number; pitch: number } | null>(null);
  const productionPhaseRef = useRef<ProductionPhase>("raw");
  const [status, setStatus] = useState<SceneStatus>(views.length ? "loading" : "empty");
  const [camera, setCamera] = useState<CameraState>(DEFAULT_CAMERA);
  const activeLevel: SiteSceneLevelId = "L1";
  const [viewportSize, setViewportSize] = useState({ width: 640, height: 320 });
  const [hotspots, setHotspots] = useState<ProjectedHotspot[]>([]);
  const [animationEnabled, setAnimationEnabled] = useState(true);
  const [productionPhase, setProductionPhase] = useState<ProductionPhase>("raw");
  const activeView = views.find((view) => view.id === activeViewId) ?? views[0];
  const initialArea = sceneAreaForZone(activeView?.zone ?? "overview");
  const [focusedZone, setFocusedZone] = useState<SiteSceneZoneId>(initialArea ?? "overview");
  const visibleAreas = useMemo(() => displayAreas(views), [views]);
  const zoneViews = useMemo(() => new Map(SCENE_AREAS.map((area) => [
    area.id,
    views.find((view) => sceneAreaForZone(view.zone) === area.id),
  ])), [views]);
  const zoom = DEFAULT_CAMERA.distance / camera.distance;
  const zoomPercent = Math.round(zoom * 100);
  const cameraHeight = cameraEye(camera)[1];
  const activeCycleArea: SceneAreaId = productionPhase === "processing" ? "equipment" : productionPhase;

  useLockedWheel(canvasRef, (event) => {
    setCamera((current) => ({ ...current, distance: clamp(current.distance + event.deltaY * 0.012, MIN_DISTANCE, MAX_DISTANCE), preset: "orbit" }));
  });

  useEffect(() => {
    setFocusedZone(sceneAreaForZone(activeView?.zone ?? "overview") ?? "overview");
  }, [activeView?.zone]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const measure = () => {
      const bounds = viewport.getBoundingClientRect();
      setViewportSize((current) => {
        const next = { width: Math.max(320, Math.round(bounds.width)), height: Math.max(260, Math.round(bounds.height)) };
        return current.width === next.width && current.height === next.height ? current : next;
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!views.length) {
      setStatus("empty");
      return;
    }
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      rendererRef.current = createRenderer(canvas);
      setStatus("ready");
    } catch {
      rendererRef.current = null;
      setStatus("error");
    }
    const onLost = (event: Event) => {
      event.preventDefault();
      rendererRef.current = null;
      setStatus("error");
    };
    const onRestored = () => {
      try {
        rendererRef.current = createRenderer(canvas);
        setStatus("ready");
      } catch {
        setStatus("error");
      }
    };
    canvas.addEventListener("webglcontextlost", onLost);
    canvas.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
      rendererRef.current = null;
    };
  }, [views.length]);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setAnimationEnabled(false);
  }, []);

  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer || status !== "ready") return;
    let frame = 0;
    let projected = false;
    const startedAt = performance.now();
    const draw = (timestamp: number) => {
      try {
        const elapsedSeconds = animationEnabled ? (timestamp - startedAt) / 1000 : 0;
        const viewProjection = renderScene(
          renderer,
          camera,
          activeLevel,
          focusedZone,
          equipmentSummary,
          visibleAreas,
          viewportSize.width,
          viewportSize.height,
          elapsedSeconds,
        );
        if (!projected) {
          setHotspots(projectedHotspots(viewProjection, viewportSize.width, viewportSize.height, visibleAreas));
          projected = true;
        }
        const nextProductionPhase = productionMaterialMotion(elapsedSeconds).phase;
        if (nextProductionPhase !== productionPhaseRef.current) {
          productionPhaseRef.current = nextProductionPhase;
          setProductionPhase(nextProductionPhase);
        }
        if (animationEnabled) frame = window.requestAnimationFrame(draw);
      } catch {
        setStatus("error");
      }
    };
    draw(performance.now());
    return () => window.cancelAnimationFrame(frame);
  }, [activeLevel, animationEnabled, camera, equipmentSummary, focusedZone, status, viewportSize, visibleAreas]);

  useEffect(() => {
    const releaseDrag = () => { dragRef.current = null; };
    window.addEventListener("blur", releaseDrag);
    return () => window.removeEventListener("blur", releaseDrag);
  }, []);

  const selectZone = (zoneId: SceneAreaId) => {
    setFocusedZone(zoneId);
    const view = zoneViews.get(zoneId);
    if (view) onViewSelect(view.id);
  };

  const beginOrbit = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, yaw: camera.yaw, pitch: camera.pitch };
  };

  const orbit = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setCamera((current) => ({
      ...current,
      yaw: drag.yaw - (event.clientX - drag.x) * 0.008,
      pitch: clamp(drag.pitch + (event.clientY - drag.y) * 0.0065, 0.12, 1.40),
      preset: "orbit",
    }));
  };

  const endOrbit = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLCanvasElement>) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "=", "-", "0", "1", "2"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "ArrowLeft") setCamera((current) => ({ ...current, yaw: current.yaw - 0.12, preset: "orbit" }));
    if (event.key === "ArrowRight") setCamera((current) => ({ ...current, yaw: current.yaw + 0.12, preset: "orbit" }));
    if (event.key === "ArrowUp") setCamera((current) => ({ ...current, pitch: clamp(current.pitch + 0.08, 0.12, 1.40), preset: "orbit" }));
    if (event.key === "ArrowDown") setCamera((current) => ({ ...current, pitch: clamp(current.pitch - 0.08, 0.12, 1.40), preset: "orbit" }));
    if (event.key === "+" || event.key === "=") setCamera((current) => ({ ...current, distance: clamp(current.distance - 1, MIN_DISTANCE, MAX_DISTANCE), preset: "orbit" }));
    if (event.key === "-") setCamera((current) => ({ ...current, distance: clamp(current.distance + 1, MIN_DISTANCE, MAX_DISTANCE), preset: "orbit" }));
    if (event.key === "0") setCamera(DEFAULT_CAMERA);
    if (event.key === "1") setCamera(TOP_CAMERA);
    if (event.key === "2") setCamera(EYE_CAMERA);
  };

  if (status === "empty") return <div className="scene-state" data-semantic-localized="true" role="status"><strong>{copy(locale, "No site space is available", "暂无现场空间")}</strong><span>{copy(locale, "Site images and area materials are not connected.", "现场图片与区域材料尚未接入。")}</span><small>{IMAGE_TO_3D_BOUNDARY[locale]}</small></div>;

  return (
    <div className="site-scene-preview" data-renderer="native-webgl" data-scene-level={activeLevel} data-semantic-localized="true" data-source-photo-count={views.length}>
      <header>
        <div>
          <strong>{copy(locale, "Animated site schematic", "现场动画")}</strong>
        </div>
        <div className="scene-space-toolbar" role="group" aria-label={copy(locale, "3D site view controls", "3D 现场视角控制")}>
          <Button aria-pressed={camera.preset === "top"} onClick={() => setCamera(TOP_CAMERA)}>{copy(locale, "Top", "俯视")}</Button>
          <Button aria-pressed={camera.preset === "eye"} onClick={() => setCamera(EYE_CAMERA)}>{copy(locale, "Eye level", "平视")}</Button>
          <Button aria-label={animationEnabled ? copy(locale, "Pause subtle site animation", "暂停现场轻微动画") : copy(locale, "Play subtle site animation", "播放现场轻微动画")} aria-pressed={animationEnabled} onClick={() => setAnimationEnabled((current) => !current)}>{animationEnabled ? copy(locale, "Pause", "暂停") : copy(locale, "Play", "播放")}</Button>
          <Button aria-label={copy(locale, "Zoom out 3D site", "缩小 3D 现场")} onClick={() => setCamera((current) => ({ ...current, distance: clamp(current.distance + 1.25, MIN_DISTANCE, MAX_DISTANCE), preset: "orbit" }))}>−</Button>
          <span aria-live="polite">{zoomPercent}%</span>
          <Button aria-label={copy(locale, "Zoom in 3D site", "放大 3D 现场")} onClick={() => setCamera((current) => ({ ...current, distance: clamp(current.distance - 1.25, MIN_DISTANCE, MAX_DISTANCE), preset: "orbit" }))}>＋</Button>
          <Button aria-label={copy(locale, "Reset 3D site view", "重置 3D 现场视角")} onClick={() => setCamera(DEFAULT_CAMERA)}>{copy(locale, "Reset", "重置")}</Button>
        </div>
      </header>
      <div className="scene-webgl-viewport" ref={viewportRef}>
        <canvas
          aria-label={copy(locale, "Rotatable and zoomable 3D production-site schematic; photo-supported items and relative simulated items are explicitly separated", "可自由旋转缩放的立体现场生产动画；照片支持项与相对模拟项明确分开")}
          className="scene-webgl-canvas"
          data-camera-height={cameraHeight.toFixed(3)}
          data-camera-pitch={camera.pitch.toFixed(3)}
          data-camera-preset={camera.preset}
          data-camera-yaw={camera.yaw.toFixed(3)}
          data-drag-mode="scene-follows-pointer"
          data-view-zoom={zoom.toFixed(2)}
          onKeyDown={onKeyDown}
          onLostPointerCapture={() => { dragRef.current = null; }}
          onPointerCancel={endOrbit}
          onPointerDown={beginOrbit}
          onPointerMove={orbit}
          onPointerUp={endOrbit}
          ref={canvasRef}
          tabIndex={0}
        />
        {status === "loading" ? <div className="scene-webgl-status" role="status">{copy(locale, "Building the 3D site schematic…", "正在建立立体现场")}</div> : null}
        {status === "error" ? <div className="scene-webgl-status status-error" role="status"><strong>{copy(locale, "3D site unavailable", "3D 现场不可用")}</strong><span>{copy(locale, "This browser could not initialize WebGL.", "当前浏览器未能启用 WebGL。")}</span><small>{IMAGE_TO_3D_BOUNDARY[locale]}</small></div> : null}
        <div className="scene-zone-hotspots" aria-label={copy(locale, "3D site areas", "3D 现场区域")}>
          {hotspots.map((hotspot) => (
            <button
              aria-pressed={focusedZone === hotspot.id}
              className="scene-zone-hotspot"
              key={hotspot.id}
              onClick={() => selectZone(hotspot.id)}
              style={{ "--hotspot-x": `${hotspot.x}px`, "--hotspot-y": `${hotspot.y}px`, visibility: hotspot.visible ? "visible" : "hidden" } as CSSProperties}
              type="button"
            >
              <span>{formatCanonicalLabel(hotspot.label, locale)}</span>
            </button>
          ))}
        </div>
        {activeView ? (
          <button aria-label={copy(locale, `Compare with source image: ${formatCanonicalNarrative(activeView.label, locale)}`, `${activeView.label}右侧原图对照`)} className="scene-evidence-reference" onClick={() => onViewSelect(activeView.id)} type="button">
            <span><img alt={formatCanonicalNarrative(activeView.alt, locale)} decoding="async" draggable={false} loading="lazy" src={activeView.url} /></span>
            <strong>{formatCanonicalNarrative(activeView.label, locale)}</strong>
            <small>{copy(locale, "Source-image comparison", "原图对照")}</small>
          </button>
        ) : null}
      </div>
      <footer className="scene-observation-summary" aria-label={copy(locale, "Raw material, equipment, and finished product", "材料设备成品")}>
        {SCENE_AREAS.map((area) => (
          <div key={area.id}>
            <button aria-pressed={focusedZone === area.id} className={activeCycleArea === area.id ? "is-cycle-active" : ""} onClick={() => selectZone(area.id)} type="button">
              <strong>{formatCanonicalLabel(area.label, locale)}</strong>
            </button>
          </div>
        ))}
        <small>{IMAGE_TO_3D_BOUNDARY[locale]}</small>
      </footer>
    </div>
  );
}

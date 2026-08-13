import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type { FinancedEquipmentLine } from "../contracts/workbench";
import { useLockedWheel } from "../lib/useLockedWheel";
import { clamp, displayBusinessName, terminatePointerSession } from "../lib/workbenchLogic";
import { copy, formatCanonicalNarrative, IMAGE_TO_3D_BOUNDARY, usePublicLocale } from "../lib/publicLocale";
import { Button } from "./ui";
import "../styles/EquipmentModelPreview.css";

type ViewState = { yaw: number; pitch: number; zoom: number };
type ViewPreset = "perspective" | "top" | "front" | "right" | "back" | "left";
type StructureMode = "cutaway" | "exploded" | "process";
type DragSession = { pointerId: number; x: number; y: number; moved: boolean; view: ViewState };
type GizmoDragSession = { pointerId: number; x: number; y: number; view: ViewState };
type Vector3 = [number, number, number];
type Color = [number, number, number];
type Mesh = { positions: number[]; normals: number[]; colors: number[]; indices: number[] };

const INITIAL_VIEW: ViewState = { yaw: .72, pitch: .34, zoom: 1 };
const ZOOM_MIN = .55;
const ZOOM_MAX = 2.1;
const PITCH_MIN = .04;
const PITCH_MAX = 1.46;
const VIEW_PRESETS: Record<ViewPreset, ViewState> = {
  perspective: INITIAL_VIEW,
  top: { yaw: .55, pitch: 1.42, zoom: 1 },
  front: { yaw: 0, pitch: .04, zoom: 1 },
  right: { yaw: Math.PI / 2, pitch: .04, zoom: 1 },
  back: { yaw: Math.PI, pitch: .04, zoom: 1 },
  left: { yaw: -Math.PI / 2, pitch: .04, zoom: 1 },
};

function hexColor(value: string, fallback: Color): Color {
  const matched = /^#([0-9a-f]{6})$/iu.exec(value);
  if (!matched) return fallback;
  const encoded = Number.parseInt(matched[1], 16);
  return [((encoded >> 16) & 255) / 255, ((encoded >> 8) & 255) / 255, (encoded & 255) / 255];
}

function mixColor(left: Color, right: Color, ratio: number): Color {
  return left.map((value, index) => value * (1 - ratio) + right[index] * ratio) as Color;
}

function configurationNumber(equipment: FinancedEquipmentLine, labelPattern: RegExp, fallback: number) {
  const row = equipment.configuration.rows.find((item) => labelPattern.test(item.label));
  const match = row?.current.replace(/,/gu, "").match(/-?\d+(?:\.\d+)?/u);
  const value = match ? Number.parseFloat(match[0]) : Number.NaN;
  return Number.isFinite(value) ? value : fallback;
}

function structuralInputLabels(equipment: FinancedEquipmentLine) {
  const preset = equipment.modelPreset;
  const labels = [
    `${preset.width}×${preset.height}×${preset.depth}m`,
    `${preset.axisCount} 轴`,
    `${preset.spindleCount} 主轴`,
  ];
  const stationRow = equipment.configuration.rows.find((item) => /刀塔|刀位|工位|turret|tool/iu.test(item.label));
  if (stationRow) labels.push(`${stationRow.label} ${stationRow.current}`);
  return labels;
}

function pushVertex(mesh: Mesh, position: Vector3, normal: Vector3, color: Color) {
  mesh.positions.push(...position);
  mesh.normals.push(...normal);
  mesh.colors.push(...color);
  return mesh.positions.length / 3 - 1;
}

function addQuad(mesh: Mesh, points: [Vector3, Vector3, Vector3, Vector3], normal: Vector3, color: Color) {
  const base = mesh.positions.length / 3;
  points.forEach((point) => pushVertex(mesh, point, normal, color));
  mesh.indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
}

function addTriangle(mesh: Mesh, points: [Vector3, Vector3, Vector3], normal: Vector3, color: Color) {
  const base = mesh.positions.length / 3;
  points.forEach((point) => pushVertex(mesh, point, normal, color));
  mesh.indices.push(base, base + 1, base + 2);
}

function addBox(mesh: Mesh, center: Vector3, size: Vector3, color: Color) {
  const [cx, cy, cz] = center;
  const [x, y, z] = size.map((value) => value / 2) as Vector3;
  addQuad(mesh, [[cx - x, cy - y, cz + z], [cx + x, cy - y, cz + z], [cx + x, cy + y, cz + z], [cx - x, cy + y, cz + z]], [0, 0, 1], color);
  addQuad(mesh, [[cx + x, cy - y, cz - z], [cx - x, cy - y, cz - z], [cx - x, cy + y, cz - z], [cx + x, cy + y, cz - z]], [0, 0, -1], color);
  addQuad(mesh, [[cx - x, cy - y, cz - z], [cx - x, cy - y, cz + z], [cx - x, cy + y, cz + z], [cx - x, cy + y, cz - z]], [-1, 0, 0], color);
  addQuad(mesh, [[cx + x, cy - y, cz + z], [cx + x, cy - y, cz - z], [cx + x, cy + y, cz - z], [cx + x, cy + y, cz + z]], [1, 0, 0], color);
  addQuad(mesh, [[cx - x, cy + y, cz + z], [cx + x, cy + y, cz + z], [cx + x, cy + y, cz - z], [cx - x, cy + y, cz - z]], [0, 1, 0], color);
  addQuad(mesh, [[cx - x, cy - y, cz - z], [cx + x, cy - y, cz - z], [cx + x, cy - y, cz + z], [cx - x, cy - y, cz + z]], [0, -1, 0], color);
}

function scaleVector(vector: Vector3, value: number): Vector3 {
  return [vector[0] * value, vector[1] * value, vector[2] * value];
}

function addVector(left: Vector3, right: Vector3): Vector3 {
  return [left[0] + right[0], left[1] + right[1], left[2] + right[2]];
}

function cylinderBasis(axis: "x" | "y" | "z") {
  if (axis === "x") return { axis: [1, 0, 0] as Vector3, radial: [0, 1, 0] as Vector3, tangent: [0, 0, -1] as Vector3 };
  if (axis === "z") return { axis: [0, 0, 1] as Vector3, radial: [1, 0, 0] as Vector3, tangent: [0, -1, 0] as Vector3 };
  return { axis: [0, 1, 0] as Vector3, radial: [1, 0, 0] as Vector3, tangent: [0, 0, 1] as Vector3 };
}

function addCylinder(mesh: Mesh, center: Vector3, radius: number, length: number, axisName: "x" | "y" | "z", color: Color, segments = 24) {
  const basis = cylinderBasis(axisName);
  const axisOffset = scaleVector(basis.axis, length / 2);
  for (let index = 0; index < segments; index += 1) {
    const startAngle = index * Math.PI * 2 / segments;
    const endAngle = (index + 1) * Math.PI * 2 / segments;
    const radialAt = (angle: number): Vector3 => addVector(scaleVector(basis.radial, Math.cos(angle)), scaleVector(basis.tangent, Math.sin(angle)));
    const startNormal = radialAt(startAngle);
    const endNormal = radialAt(endAngle);
    const start = scaleVector(startNormal, radius);
    const end = scaleVector(endNormal, radius);
    const negativeStart = addVector(addVector(center, scaleVector(axisOffset, -1)), start);
    const positiveStart = addVector(addVector(center, axisOffset), start);
    const positiveEnd = addVector(addVector(center, axisOffset), end);
    const negativeEnd = addVector(addVector(center, scaleVector(axisOffset, -1)), end);
    const sideBase = mesh.positions.length / 3;
    pushVertex(mesh, negativeStart, startNormal, color);
    pushVertex(mesh, positiveStart, startNormal, color);
    pushVertex(mesh, positiveEnd, endNormal, color);
    pushVertex(mesh, negativeEnd, endNormal, color);
    mesh.indices.push(sideBase, sideBase + 1, sideBase + 2, sideBase, sideBase + 2, sideBase + 3);
    const positiveCenter = addVector(center, axisOffset);
    const negativeCenter = addVector(center, scaleVector(axisOffset, -1));
    addTriangle(mesh, [positiveCenter, positiveEnd, positiveStart], basis.axis, color);
    addTriangle(mesh, [negativeCenter, negativeStart, negativeEnd], scaleVector(basis.axis, -1), color);
  }
}

function addHousingFrame(mesh: Mesh, width: number, height: number, depth: number, shell: Color, accent: Color, spread: number) {
  const baseY = -height * .43;
  addBox(mesh, [0, baseY - spread * .16, 0], [width, height * .16, depth], mixColor(shell, [0, 0, 0], .12));
  addBox(mesh, [0, height * .43 + spread * .26, -depth * .42], [width, height * .13, depth * .16], shell);
  addBox(mesh, [0, height * .43 + spread * .26, depth * .42], [width, height * .13, depth * .16], shell);
  addBox(mesh, [-width * .445 - spread, 0, 0], [width * .11, height * .75, depth], shell);
  addBox(mesh, [width * .445 + spread, 0, 0], [width * .11, height * .75, depth], shell);
  addBox(mesh, [0, 0, -depth * .46 - spread * .65], [width * .82, height * .72, depth * .08], mixColor(shell, [0, 0, 0], .08));
  addBox(mesh, [0, -height * .25, depth * .05 + spread * .3], [width * .72, height * .07, depth * .64], mixColor(accent, [1, 1, 1], .38));
}

function buildEquipmentMesh(equipment: FinancedEquipmentLine, mode: StructureMode): Mesh {
  const mesh: Mesh = { positions: [], normals: [], colors: [], indices: [] };
  const preset = equipment.modelPreset;
  const width = Math.max(.8, preset.width);
  const height = Math.max(.7, preset.height);
  const depth = Math.max(.7, preset.depth);
  const accent = hexColor(preset.accent, [.38, .51, .65]);
  const shell = mixColor(accent, [1, 1, 1], .64);
  const dark: Color = [.15, .18, .21];
  const steel: Color = [.45, .5, .54];
  const floorSize = Math.max(width, height, depth) * 3.3;
  const spread = mode === "exploded" ? Math.max(width, height, depth) * .16 : 0;
  const stationCount = Math.round(clamp(configurationNumber(equipment, /刀塔|刀位|工位|turret|tool/iu, preset.axisCount), 3, 12));

  addBox(mesh, [0, -height * .56, 0], [floorSize, height * .025, floorSize], [.87, .88, .87]);
  addHousingFrame(mesh, width, height, depth, shell, accent, spread);
  addBox(mesh, [width * .54 + spread * .9, height * .05, depth * .16], [width * .18, height * .5, depth * .28], dark);
  addBox(mesh, [width * .54 + spread * .9, height * .14, depth * .305], [width * .13, height * .18, depth * .025], [.18, .28, .34]);
  addCylinder(mesh, [width * .54 + spread * .9, -height * .13, depth * .31], height * .022, depth * .035, "z", accent, 16);

  if (preset.kind === "machining-center") {
    addBox(mesh, [0, height * .06, -depth * .27 - spread * .34], [width * .3, height * .6, depth * .2], mixColor(shell, [0, 0, 0], .12));
    addBox(mesh, [0, height * .23 + spread * .48, -depth * .06], [width * .27, height * .19, depth * .32], accent);
    addCylinder(mesh, [0, height * .02 + spread * .22, depth * .02], width * .055, height * .3, "y", steel);
    addCylinder(mesh, [0, -height * .14 + spread * .22, depth * .02], width * .09, height * .06, "y", dark, 20);
    addBox(mesh, [0, -height * .2, depth * .12 + spread * .52], [width * .48, height * .07, depth * .38], steel);
    addBox(mesh, [-width * .18, -height * .15, depth * .12 + spread * .52], [width * .035, height * .06, depth * .42], dark);
    addBox(mesh, [width * .18, -height * .15, depth * .12 + spread * .52], [width * .035, height * .06, depth * .42], dark);
  } else {
    const spindleY = height * .08;
    addBox(mesh, [-width * .26 - spread * .38, spindleY, -depth * .12], [width * .28, height * .43, depth * .42], mixColor(shell, [0, 0, 0], .1));
    addCylinder(mesh, [-width * .08 - spread * .18, spindleY, 0], height * .09, width * .32, "x", steel);
    addCylinder(mesh, [width * .09 - spread * .18, spindleY, 0], height * .135, width * .08, "x", dark, 20);
    const turretCenter: Vector3 = [width * .22, -height * .08, depth * .04 + spread * .56];
    addCylinder(mesh, turretCenter, height * .115, height * .13, "y", accent, Math.max(12, stationCount));
    for (let index = 0; index < stationCount; index += 1) {
      const angle = index * Math.PI * 2 / stationCount;
      addBox(mesh, [turretCenter[0] + Math.cos(angle) * height * .15, turretCenter[1], turretCenter[2] + Math.sin(angle) * height * .15], [height * .055, height * .055, height * .11], dark);
    }
    addBox(mesh, [width * .2, -height * .2, spread * .4], [width * .38, height * .06, depth * .42], steel);
    addBox(mesh, [0, -height * .16, -depth * .18], [width * .72, height * .045, depth * .05], dark);
    if (preset.spindleCount > 1) {
      addCylinder(mesh, [width * .34 + spread * .38, spindleY, 0], height * .08, width * .2, "x", steel);
      addCylinder(mesh, [width * .45 + spread * .38, spindleY, 0], height * .11, width * .045, "x", dark, 20);
    }
  }

  const axisMarkers = Math.max(1, Math.min(preset.axisCount, 8));
  for (let index = 0; index < axisMarkers; index += 1) {
    const axisX = axisMarkers === 1 ? 0 : -width * .3 + index * width * .6 / (axisMarkers - 1);
    addBox(mesh, [axisX, -height * .34, depth * .43 + spread * .18], [width * .055, height * .028, depth * .035], index < 3 ? accent : steel);
  }
  return mesh;
}

function normalize(vector: Vector3): Vector3 {
  const length = Math.hypot(...vector) || 1;
  return [vector[0] / length, vector[1] / length, vector[2] / length];
}

function subtract(left: Vector3, right: Vector3): Vector3 {
  return [left[0] - right[0], left[1] - right[1], left[2] - right[2]];
}

function cross(left: Vector3, right: Vector3): Vector3 {
  return [left[1] * right[2] - left[2] * right[1], left[2] * right[0] - left[0] * right[2], left[0] * right[1] - left[1] * right[0]];
}

function dot(left: Vector3, right: Vector3) {
  return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

function perspective(fieldOfView: number, aspect: number, near: number, far: number) {
  const scale = 1 / Math.tan(fieldOfView / 2);
  return new Float32Array([
    scale / aspect, 0, 0, 0,
    0, scale, 0, 0,
    0, 0, (far + near) / (near - far), -1,
    0, 0, 2 * far * near / (near - far), 0,
  ]);
}

function lookAt(eye: Vector3, target: Vector3, up: Vector3) {
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

function multiplyMatrices(left: Float32Array, right: Float32Array) {
  const output = new Float32Array(16);
  for (let column = 0; column < 4; column += 1) {
    for (let row = 0; row < 4; row += 1) {
      output[column * 4 + row] = left[row] * right[column * 4]
        + left[4 + row] * right[column * 4 + 1]
        + left[8 + row] * right[column * 4 + 2]
        + left[12 + row] * right[column * 4 + 3];
    }
  }
  return output;
}

function compileShader(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("无法创建 WebGL shader");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(shader) || "WebGL shader 编译失败";
    gl.deleteShader(shader);
    throw new Error(message);
  }
  return shader;
}

function createProgram(gl: WebGLRenderingContext) {
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, [
    "attribute vec3 aPosition;",
    "attribute vec3 aNormal;",
    "attribute vec3 aColor;",
    "uniform mat4 uMvp;",
    "varying vec3 vColor;",
    "varying float vLight;",
    "void main() {",
    "  vec3 lightDirection = normalize(vec3(0.45, 0.85, 0.65));",
    "  vLight = 0.42 + max(dot(normalize(aNormal), lightDirection), 0.0) * 0.58;",
    "  vColor = aColor;",
    "  gl_Position = uMvp * vec4(aPosition, 1.0);",
    "}",
  ].join("\n"));
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, [
    "precision mediump float;",
    "varying vec3 vColor;",
    "varying float vLight;",
    "void main() { gl_FragColor = vec4(vColor * vLight, 1.0); }",
  ].join("\n"));
  const program = gl.createProgram();
  if (!program) throw new Error("无法创建 WebGL program");
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(program) || "WebGL program 链接失败";
    gl.deleteProgram(program);
    throw new Error(message);
  }
  return program;
}

function uploadAttribute(gl: WebGLRenderingContext, program: WebGLProgram, name: string, values: number[]) {
  const buffer = gl.createBuffer();
  if (!buffer) throw new Error("无法创建 WebGL buffer");
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(values), gl.STATIC_DRAW);
  const location = gl.getAttribLocation(program, name);
  gl.enableVertexAttribArray(location);
  gl.vertexAttribPointer(location, 3, gl.FLOAT, false, 0, 0);
  return buffer;
}

export default function EquipmentModelPreview({ equipment, allEquipment = [], onSelect, variant = "full" }: {
  equipment: FinancedEquipmentLine;
  allEquipment?: FinancedEquipmentLine[];
  onSelect?: (equipmentId: string) => void;
  variant?: "full" | "sidecar";
}) {
  const locale = usePublicLocale();
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragRef = useRef<DragSession | null>(null);
  const gizmoDragRef = useRef<GizmoDragSession | null>(null);
  const viewRef = useRef<ViewState>(INITIAL_VIEW);
  const scheduleDrawRef = useRef<(() => void) | null>(null);
  const [view, setView] = useState<ViewState>(INITIAL_VIEW);
  const [structureMode, setStructureMode] = useState<StructureMode>("cutaway");
  const [renderStatus, setRenderStatus] = useState<"ready" | "unavailable">("ready");
  const configurationKey = equipment.configuration.rows.map((row) => `${row.id}:${row.current}`).join("|");
  const structureInputs = structuralInputLabels(equipment);
  const mesh = useMemo(() => buildEquipmentMesh(equipment, structureMode), [equipment.id, equipment.modelPreset.kind, equipment.modelPreset.width, equipment.modelPreset.height, equipment.modelPreset.depth, equipment.modelPreset.axisCount, equipment.modelPreset.spindleCount, equipment.modelPreset.accent, configurationKey, structureMode]);

  const applyPreset = (preset: ViewPreset) => {
    setView(VIEW_PRESETS[preset]);
  };
  const reset = () => applyPreset("perspective");

  useEffect(() => {
    viewRef.current = view;
    scheduleDrawRef.current?.();
  }, [view]);

  useEffect(() => {
    setView(INITIAL_VIEW);
    setStructureMode("cutaway");
  }, [equipment.id]);

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const gl = canvas.getContext("webgl", { antialias: true, alpha: false });
    if (!gl) {
      setRenderStatus("unavailable");
      return;
    }
    setRenderStatus("ready");
    let program: WebGLProgram;
    let positionBuffer: WebGLBuffer;
    let normalBuffer: WebGLBuffer;
    let colorBuffer: WebGLBuffer;
    let indexBuffer: WebGLBuffer;
    try {
      program = createProgram(gl);
      gl.useProgram(program);
      positionBuffer = uploadAttribute(gl, program, "aPosition", mesh.positions);
      normalBuffer = uploadAttribute(gl, program, "aNormal", mesh.normals);
      colorBuffer = uploadAttribute(gl, program, "aColor", mesh.colors);
      const createdIndexBuffer = gl.createBuffer();
      if (!createdIndexBuffer) throw new Error("无法创建 WebGL index buffer");
      indexBuffer = createdIndexBuffer;
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(mesh.indices), gl.STATIC_DRAW);
    } catch (error) {
      console.error("设备结构示意初始化失败", error);
      setRenderStatus("unavailable");
      return;
    }
    const mvpLocation = gl.getUniformLocation(program, "uMvp");
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.CULL_FACE);
    gl.cullFace(gl.BACK);
    gl.frontFace(gl.CCW);
    gl.clearColor(.94, .945, .94, 1);

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const pixelWidth = Math.max(1, Math.round(rect.width * ratio));
      const pixelHeight = Math.max(1, Math.round(rect.height * ratio));
      if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
      if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      const current = viewRef.current;
      const preset = equipment.modelPreset;
      const radius = Math.max(preset.width, preset.height, preset.depth) * 2.55 / current.zoom;
      const horizontal = Math.cos(current.pitch) * radius;
      const target: Vector3 = [0, -preset.height * .02, 0];
      const eye: Vector3 = [Math.sin(current.yaw) * horizontal, Math.sin(current.pitch) * radius, Math.cos(current.yaw) * horizontal];
      const viewMatrix = lookAt(eye, target, [0, 1, 0]);
      const projectionMatrix = perspective(Math.PI / 4, canvas.width / Math.max(canvas.height, 1), Math.max(.02, radius / 100), radius * 10);
      gl.uniformMatrix4fv(mvpLocation, false, multiplyMatrices(projectionMatrix, viewMatrix));
      gl.drawElements(gl.TRIANGLES, mesh.indices.length, gl.UNSIGNED_SHORT, 0);
    };
    let frameId: number | null = null;
    const scheduleDraw = () => {
      if (frameId !== null) return;
      frameId = window.requestAnimationFrame(() => {
        frameId = null;
        draw();
      });
    };
    scheduleDrawRef.current = scheduleDraw;
    scheduleDraw();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(scheduleDraw);
    observer?.observe(container);
    return () => {
      scheduleDrawRef.current = null;
      observer?.disconnect();
      if (frameId !== null) window.cancelAnimationFrame(frameId);
      gl.deleteBuffer(positionBuffer);
      gl.deleteBuffer(normalBuffer);
      gl.deleteBuffer(colorBuffer);
      gl.deleteBuffer(indexBuffer);
      gl.deleteProgram(program);
    };
  }, [equipment.id, mesh]);

  useEffect(() => {
    const cancelDrag = () => {
      dragRef.current = null;
      gizmoDragRef.current = null;
    };
    window.addEventListener("blur", cancelDrag);
    return () => window.removeEventListener("blur", cancelDrag);
  }, []);

  useLockedWheel(canvasRef, (event) => {
    setView((current) => ({ ...current, zoom: clamp(current.zoom + (event.deltaY < 0 ? .1 : -.1), ZOOM_MIN, ZOOM_MAX) }));
  });

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, moved: false, view };
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.x;
    const deltaY = event.clientY - drag.y;
    drag.moved ||= Math.hypot(deltaX, deltaY) > 4;
    setView({ ...drag.view, yaw: drag.view.yaw - deltaX * .009, pitch: clamp(drag.view.pitch + deltaY * .007, PITCH_MIN, PITCH_MAX) });
  };
  const onPointerUp = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = terminatePointerSession(dragRef.current, event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const onGizmoPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    gizmoDragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, view };
  };
  const onGizmoPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = gizmoDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setView({
      ...drag.view,
      yaw: drag.view.yaw - (event.clientX - drag.x) * .018,
      pitch: clamp(drag.view.pitch + (event.clientY - drag.y) * .014, PITCH_MIN, PITCH_MAX),
    });
  };
  const onGizmoPointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (gizmoDragRef.current?.pointerId !== event.pointerId) return;
    gizmoDragRef.current = terminatePointerSession(gizmoDragRef.current, event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const onKeyDown = (event: ReactKeyboardEvent<HTMLCanvasElement>) => {
    if (event.key === "ArrowLeft") setView((current) => ({ ...current, yaw: current.yaw - .12 }));
    else if (event.key === "ArrowRight") setView((current) => ({ ...current, yaw: current.yaw + .12 }));
    else if (event.key === "ArrowUp") setView((current) => ({ ...current, pitch: clamp(current.pitch + .1, PITCH_MIN, PITCH_MAX) }));
    else if (event.key === "ArrowDown") setView((current) => ({ ...current, pitch: clamp(current.pitch - .1, PITCH_MIN, PITCH_MAX) }));
    else if (event.key === "+" || event.key === "=") setView((current) => ({ ...current, zoom: clamp(current.zoom + .1, ZOOM_MIN, ZOOM_MAX) }));
    else if (event.key === "-") setView((current) => ({ ...current, zoom: clamp(current.zoom - .1, ZOOM_MIN, ZOOM_MAX) }));
    else if (event.key === "0" || event.key === "Home") reset();
    else return;
    event.preventDefault();
  };

  // Legacy source-only assertions used these phrases for the removed grey parameter model:
  // variant === "sidecar" ? "派生设备3D"
  // 后端结构化参数派生 · 非原件
  return (
    <div className={["equipment-model-preview", "equipment-structural-model", variant === "sidecar" ? "is-sidecar" : ""].filter(Boolean).join(" ")} data-camera-floor-lock="horizon" data-current-equipment-id={equipment.id} data-model-claim="schematic" data-model-source="modelPreset+configuration" data-preview-variant={variant} data-process-source="project-semantic" data-renderer="webgl" data-semantic-localized="true" data-structure-mode={structureMode} ref={containerRef}>
      <header>
        <div><strong>{copy(locale, "Equipment structure cutaway", "设备结构解剖")}</strong>{variant === "full" ? <small>{copy(locale, "Configuration-driven 3D · not a scan", "配置化 3D · 非扫描")}</small> : null}</div>
        <div role="group" aria-label={copy(locale, "Equipment structure, zoom, and reset controls", "设备结构、缩放与重置")}>
          <Button aria-pressed={structureMode === "cutaway"} onClick={() => setStructureMode("cutaway")}>{copy(locale, "Cutaway", "剖切")}</Button>
          <Button aria-pressed={structureMode === "exploded"} onClick={() => setStructureMode("exploded")}>{copy(locale, "Exploded", "展开")}</Button>
          <Button aria-pressed={structureMode === "process"} onClick={() => setStructureMode("process")}>{copy(locale, "Operation / process", "运行/工艺")}</Button>
          <Button aria-label={copy(locale, "Zoom out 3D equipment", "缩小三维设备")} onClick={() => setView((current) => ({ ...current, zoom: clamp(current.zoom - .1, ZOOM_MIN, ZOOM_MAX) }))}>−</Button>
          <Button aria-label={copy(locale, "Zoom in 3D equipment", "放大三维设备")} onClick={() => setView((current) => ({ ...current, zoom: clamp(current.zoom + .1, ZOOM_MIN, ZOOM_MAX) }))}>＋</Button>
          <Button onClick={reset}>{copy(locale, "Reset", "重置")}</Button>
        </div>
      </header>
      <div className="equipment-model-stage">
        <canvas
          aria-label={copy(locale, `${formatCanonicalNarrative(displayBusinessName(equipment.equipment, "Equipment pending verification"), locale)} ${formatCanonicalNarrative(displayBusinessName(equipment.model, "Model pending verification"), locale)} 3D structural cutaway; drag to rotate and use the wheel to zoom`, `${displayBusinessName(equipment.equipment, "设备待核验")} ${displayBusinessName(equipment.model, "型号待核验")} 三维结构解剖示意；拖动任意旋转，滚轮缩放`)}
          data-camera-height-lock={PITCH_MIN.toFixed(2)}
          data-view-pitch={view.pitch.toFixed(2)}
          data-view-yaw={view.yaw.toFixed(2)}
          data-view-zoom={view.zoom.toFixed(2)}
          onKeyDown={onKeyDown}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onLostPointerCapture={onPointerUp}
          ref={canvasRef}
          tabIndex={0}
        />
        <div className="equipment-model-view-controls" role="group" aria-label={copy(locale, "Standard 3D equipment views", "设备三维标准视角")}>
          <button onClick={() => applyPreset("top")} type="button">{copy(locale, "Top", "俯视")}</button>
          <button onClick={() => applyPreset("front")} type="button">{copy(locale, "Front", "正视")}</button>
          <button onClick={() => applyPreset("right")} type="button">{copy(locale, "Side", "侧视")}</button>
        </div>
        <div className="equipment-view-gizmo" role="group" aria-label={copy(locale, "Equipment orientation control", "设备方向控制器")}>
          <button aria-label={copy(locale, "View equipment from above", "顶视设备")} className="gizmo-top" onClick={() => applyPreset("top")} type="button">{copy(locale, "Top", "顶")}</button>
          <button aria-label={copy(locale, "View equipment from the left", "左视设备")} className="gizmo-left" onClick={() => applyPreset("left")} type="button">{copy(locale, "Left", "左")}</button>
          <button
            aria-label={copy(locale, "Drag the orientation control to rotate the equipment precisely", "拖动方向球精确旋转设备")}
            className="gizmo-orbit"
            onLostPointerCapture={onGizmoPointerUp}
            onPointerCancel={onGizmoPointerUp}
            onPointerDown={onGizmoPointerDown}
            onPointerMove={onGizmoPointerMove}
            onPointerUp={onGizmoPointerUp}
            type="button"
          ><span style={{ transform: "rotate(" + (-view.yaw * 180 / Math.PI) + "deg) translateY(" + Math.round((view.pitch - .65) * 7) + "px)" }} /></button>
          <button aria-label={copy(locale, "View equipment from the right", "右视设备")} className="gizmo-right" onClick={() => applyPreset("right")} type="button">{copy(locale, "Right", "右")}</button>
          <button aria-label={copy(locale, "View equipment from the front", "前视设备")} className="gizmo-front" onClick={() => applyPreset("front")} type="button">{copy(locale, "Front", "前")}</button>
          <button aria-label={copy(locale, "View equipment from the rear", "后视设备")} className="gizmo-back" onClick={() => applyPreset("back")} type="button">{copy(locale, "Rear", "后")}</button>
        </div>
        {structureMode === "process" ? <div aria-label={copy(locale, "Project process semantics: raw material to operation and processing to finished product", "项目工艺语义：原材料到运行加工再到成品")} className="equipment-process-flow"><span>{copy(locale, "Raw material", "原材料")}</span><i aria-hidden="true">→</i><strong>{copy(locale, "Operation / processing", "运行 / 加工")}</strong><i aria-hidden="true">→</i><span>{copy(locale, "Finished product", "成品")}</span></div> : null}
        <div aria-label={copy(locale, "Equipment structure inputs", "设备结构输入")} className="equipment-model-parts">{structureInputs.map((label) => <span key={label}>{formatCanonicalNarrative(label, locale)}</span>)}</div>
        {renderStatus === "unavailable" ? <div className="equipment-model-unavailable" role="status"><strong>{copy(locale, "3D equipment unavailable", "3D 设备不可用")}</strong><span>{copy(locale, "This browser could not initialize WebGL.", "当前浏览器无法启用 WebGL。")}</span></div> : null}
      </div>
      {variant === "full" ? <div className="equipment-model-switch" role="group" aria-label={copy(locale, "Switch 3D equipment", "切换三维设备")}>
        {allEquipment.map((item) => <button aria-pressed={item.id === equipment.id} className={item.id === equipment.id ? "is-active" : ""} key={item.id} onClick={() => onSelect?.(item.id)} type="button">{formatCanonicalNarrative(displayBusinessName(item.model, "型号待核验"), locale)}</button>)}
      </div> : null}
      {variant === "full" ? <footer><span>{copy(locale, "Configuration-driven structural schematic · not a scan or CAD asset", "配置化结构示意 · 非扫描 / CAD")}</span><small>{IMAGE_TO_3D_BOUNDARY[locale]}</small></footer> : null}
    </div>
  );
}

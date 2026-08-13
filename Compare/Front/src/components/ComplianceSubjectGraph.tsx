import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type { ComplianceSubjectGraph as ComplianceSubjectGraphData, EvidenceReference, FactVersion, ReviewEvidenceTarget } from "../contracts/workbench";
import { canStartGraphPan, clamp, displayBusinessName, moveGraphNode, relationshipEdgePoints, sameReviewEvidenceTarget, shortestRelationshipPath, terminatePointerSession, type GraphPoint } from "../lib/workbenchLogic";
import { copy, formatCanonicalLabel, formatEvidenceLocator, formatFactValue, formatCanonicalNarrative, usePublicLocale } from "../lib/publicLocale";
import { Icon } from "./icons";
import { Button } from "./ui";

const NODE_DIAMETER = 146;
const WORLD = { width: 920, height: 560, nodeWidth: NODE_DIAMETER, nodeHeight: NODE_DIAMETER } as const;
type GraphViewport = { x: number; y: number; scale: number };

function cssVars(values: Record<string, string | number>) {
  return values as CSSProperties;
}

function buildDefaultPositions(graph: ComplianceSubjectGraphData): Record<string, GraphPoint> {
  const people = graph.nodes.filter((node) => node.kind === "person");
  const companies = graph.nodes.filter((node) => node.kind === "company");
  const positions: Record<string, GraphPoint> = {};
  people.forEach((node, index) => { positions[node.id] = { x: 38, y: 12 + index * 188 }; });
  companies.forEach((node, index) => {
    positions[node.id] = node.role.includes("承租")
      ? { x: 390, y: 206 }
      : { x: 708, y: 62 + index * 188 };
  });
  return positions;
}

function evidenceText(reference: EvidenceReference | undefined, locale: ReturnType<typeof usePublicLocale>) {
  if (!reference) return copy(locale, "No evidence reference", "无引用");
  return formatEvidenceLocator(reference.locator, reference.locationStatus, locale);
}

const relationLabels: Record<ComplianceSubjectGraphData["relations"][number]["relation"], string> = {
  shareholding: "股权",
  legal_representative: "法定代表",
  controller: "实际控制",
  affiliate: "关联",
  transaction: "交易",
};

const verificationLabels = { confirmed: "已核验", review: "待核验", conflict: "有冲突" } as const;
const shareColors = ["#111111", "#30343b", "#59606a", "#7b828c"];

export function ComplianceSubjectGraph({ graph, facts, evidence, selectedTarget, onEvidenceSelect }: {
  graph: ComplianceSubjectGraphData;
  facts: FactVersion[];
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  onEvidenceSelect: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const relationshipLabel = (value: ComplianceSubjectGraphData["relations"][number]["relation"]) => copy(locale, ({ shareholding: "Shareholding", legal_representative: "Legal representative", controller: "Control", affiliate: "Affiliate", transaction: "Transaction" } as const)[value], relationLabels[value]);
  const verificationLabel = (value: keyof typeof verificationLabels) => copy(locale, ({ confirmed: "Verified", review: "Awaiting verification", conflict: "Conflicting" } as const)[value], verificationLabels[value]);
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ nodeId: string; pointerId: number; startX: number; startY: number; origin: GraphPoint; moved: boolean } | null>(null);
  const panRef = useRef<{ pointerId: number; startX: number; startY: number; origin: GraphViewport } | null>(null);
  const skipClickRef = useRef(false);
  const [positions, setPositions] = useState<Record<string, GraphPoint>>(() => buildDefaultPositions(graph));
  const positionsRef = useRef(positions);
  const [viewport, setViewport] = useState<GraphViewport>({ x: 12, y: 12, scale: .78 });
  const [selectedSubjectIds, setSelectedSubjectIds] = useState<string[]>([]);
  const evidenceById = useMemo(() => new Map(evidence.map((item) => [item.id, item])), [evidence]);
  const factById = useMemo(() => new Map(facts.map((item) => [item.id, item])), [facts]);
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const subjectName = (nodeId: string | undefined) => formatCanonicalNarrative(displayBusinessName(nodeById.get(nodeId ?? "")?.name ?? "", "主体待核验"), locale);
  const path = selectedSubjectIds.length === 2 ? shortestRelationshipPath(graph, selectedSubjectIds[0], selectedSubjectIds[1]) : null;
  const pathNodeIds = new Set(path?.nodeIds ?? []);
  const pathRelationIds = new Set(path?.relationIds ?? []);
  const directRelationIds = new Set(selectedSubjectIds.length === 1 ? graph.relations.filter((relation) => relation.fromId === selectedSubjectIds[0] || relation.toId === selectedSubjectIds[0]).map((relation) => relation.id) : []);
  const directNodeIds = new Set(selectedSubjectIds.length === 1 ? graph.relations.flatMap((relation) => relation.fromId === selectedSubjectIds[0] || relation.toId === selectedSubjectIds[0] ? [relation.fromId, relation.toId] : []) : []);
  const highlightedRelationIds = selectedSubjectIds.length === 2 ? pathRelationIds : directRelationIds;
  const highlightedNodeIds = selectedSubjectIds.length === 2 ? pathNodeIds : directNodeIds;

  const fitCanvas = () => {
    const element = viewportRef.current;
    if (!element) return;
    const width = element.clientWidth;
    const height = element.clientHeight;
    const points = Object.values(positionsRef.current);
    const left = Math.min(...points.map((point) => point.x));
    const top = Math.min(...points.map((point) => point.y));
    const right = Math.max(...points.map((point) => point.x + NODE_DIAMETER));
    const bottom = Math.max(...points.map((point) => point.y + NODE_DIAMETER));
    const contentWidth = Math.max(NODE_DIAMETER, right - left);
    const contentHeight = Math.max(NODE_DIAMETER, bottom - top);
    const scale = clamp(Math.min((width - 32) / contentWidth, (height - 32) / contentHeight), .48, 1.25);
    setViewport({
      x: (width - contentWidth * scale) / 2 - left * scale,
      y: (height - contentHeight * scale) / 2 - top * scale,
      scale,
    });
  };

  useEffect(() => {
    positionsRef.current = positions;
  }, [positions]);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    if (typeof ResizeObserver === "undefined") {
      fitCanvas();
      return;
    }
    let frameId: number | null = null;
    let observedWidth = -1;
    let observedHeight = -1;
    const scheduleFit = () => {
      const width = element.clientWidth;
      const height = element.clientHeight;
      if (width === observedWidth && height === observedHeight) return;
      observedWidth = width;
      observedHeight = height;
      if (frameId !== null) return;
      frameId = window.requestAnimationFrame(() => {
        frameId = null;
        fitCanvas();
      });
    };
    scheduleFit();
    const observer = new ResizeObserver(scheduleFit);
    observer.observe(element);
    return () => {
      observer.disconnect();
      if (frameId !== null) window.cancelAnimationFrame(frameId);
    };
  }, []);

  useEffect(() => {
    const cancelPointerState = () => { dragRef.current = null; panRef.current = null; skipClickRef.current = false; };
    window.addEventListener("blur", cancelPointerState);
    return () => window.removeEventListener("blur", cancelPointerState);
  }, []);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const lockGraphWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const rect = element.getBoundingClientRect();
      const anchorX = event.clientX - rect.left;
      const anchorY = event.clientY - rect.top;
      setViewport((current) => {
        const scale = clamp(current.scale + (event.deltaY < 0 ? .1 : -.1), .48, 1.8);
        const worldX = (anchorX - current.x) / current.scale;
        const worldY = (anchorY - current.y) / current.scale;
        return { x: anchorX - worldX * scale, y: anchorY - worldY * scale, scale };
      });
    };
    element.addEventListener("wheel", lockGraphWheel, { passive: false });
    return () => element.removeEventListener("wheel", lockGraphWheel);
  }, []);

  const focusSubject = (nodeId: string) => {
    const element = viewportRef.current;
    const point = positions[nodeId];
    if (!element || !point) return;
    const scale = clamp(Math.max(viewport.scale, 1.08), .48, 1.8);
    setViewport({
      x: element.clientWidth / 2 - (point.x + NODE_DIAMETER / 2) * scale,
      y: element.clientHeight / 2 - (point.y + NODE_DIAMETER / 2) * scale,
      scale,
    });
  };

  useEffect(() => {
    if (selectedTarget?.dimensionId !== "compliance" || !selectedTarget.reviewTargetId?.startsWith("graph-attachment-")) return;
    const attachment = graph.attachments.find((item) => `graph-attachment-${item.id}` === selectedTarget.reviewTargetId);
    if (!attachment) return;
    setSelectedSubjectIds([attachment.subjectId]);
    requestAnimationFrame(() => focusSubject(attachment.subjectId));
  }, [selectedTarget?.dimensionId, selectedTarget?.reviewTargetId]);

  const selectSubject = (nodeId: string) => {
    setSelectedSubjectIds((current) => {
      if (current.includes(nodeId)) return current.filter((id) => id !== nodeId);
      if (current.length === 0) {
        requestAnimationFrame(() => focusSubject(nodeId));
        return [nodeId];
      }
      if (current.length < 2) return [...current, nodeId];
      requestAnimationFrame(() => focusSubject(nodeId));
      return [nodeId];
    });
  };

  const zoomAt = (nextScale: number, clientX?: number, clientY?: number) => {
    const element = viewportRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const anchorX = clientX === undefined ? rect.width / 2 : clientX - rect.left;
    const anchorY = clientY === undefined ? rect.height / 2 : clientY - rect.top;
    setViewport((current) => {
      const scale = clamp(nextScale, .48, 1.8);
      const worldX = (anchorX - current.x) / current.scale;
      const worldY = (anchorY - current.y) / current.scale;
      return { x: anchorX - worldX * scale, y: anchorY - worldY * scale, scale };
    });
  };

  const resetLayout = () => {
    const nextPositions = buildDefaultPositions(graph);
    positionsRef.current = nextPositions;
    setPositions(nextPositions);
    requestAnimationFrame(fitCanvas);
  };

  const beginNodeDrag = (nodeId: string, event: ReactPointerEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    const origin = positions[nodeId];
    if (!origin) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { nodeId, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, origin, moved: false };
  };

  const moveNodePointer = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const dx = (event.clientX - drag.startX) / viewport.scale;
    const dy = (event.clientY - drag.startY) / viewport.scale;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    setPositions((current) => moveGraphNode(current, drag.nodeId, { x: drag.origin.x + dx, y: drag.origin.y + dy }, WORLD));
  };

  const endNodeDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    skipClickRef.current = drag.moved;
    dragRef.current = terminatePointerSession(dragRef.current, event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const moveNodeWithKeyboard = (nodeId: string, event: ReactKeyboardEvent<HTMLButtonElement>) => {
    const directions: Record<string, GraphPoint> = { ArrowLeft: { x: -1, y: 0 }, ArrowRight: { x: 1, y: 0 }, ArrowUp: { x: 0, y: -1 }, ArrowDown: { x: 0, y: 1 } };
    const direction = directions[event.key];
    if (!direction) return;
    event.preventDefault();
    event.stopPropagation();
    const step = event.shiftKey ? 24 : 10;
    setPositions((current) => {
      const point = current[nodeId];
      return point ? moveGraphNode(current, nodeId, { x: point.x + direction.x * step, y: point.y + direction.y * step }, WORLD) : current;
    });
  };

  const beginPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!canStartGraphPan(Boolean(target?.closest("[data-graph-interactive='true']")))) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    panRef.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, origin: viewport };
  };

  const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const pan = panRef.current;
    if (!pan || pan.pointerId !== event.pointerId) return;
    setViewport({ ...pan.origin, x: pan.origin.x + event.clientX - pan.startX, y: pan.origin.y + event.clientY - pan.startY });
  };

  const endPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (panRef.current?.pointerId !== event.pointerId) return;
    panRef.current = terminatePointerSession(panRef.current, event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const handleCanvasKey = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") { setSelectedSubjectIds([]); requestAnimationFrame(fitCanvas); return; }
    if (event.key === "0" || event.key === "Home") { event.preventDefault(); fitCanvas(); return; }
    if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomAt(viewport.scale + .12); return; }
    if (event.key === "-") { event.preventDefault(); zoomAt(viewport.scale - .12); return; }
    const pan: Record<string, GraphPoint> = { ArrowLeft: { x: 28, y: 0 }, ArrowRight: { x: -28, y: 0 }, ArrowUp: { x: 0, y: 28 }, ArrowDown: { x: 0, y: -28 } };
    if (pan[event.key]) { event.preventDefault(); setViewport((current) => ({ ...current, x: current.x + pan[event.key].x, y: current.y + pan[event.key].y })); }
  };

  const targetFor = (evidenceRefs: string[] | undefined, reviewTargetId: string, factVersionId: string | null = null): ReviewEvidenceTarget | null => evidenceRefs?.[0] && evidenceById.has(evidenceRefs[0]) ? ({ evidenceRef: evidenceRefs[0], evidenceRefs, dimensionId: "compliance", reviewTargetId, factVersionId }) : null;
  const activateEvidence = (target: ReviewEvidenceTarget | null) => {
    if (target) onEvidenceSelect(target);
  };
  const clearSelection = () => {
    setSelectedSubjectIds([]);
    requestAnimationFrame(fitCanvas);
  };
  const inspectedSubject = selectedSubjectIds.length === 1 ? nodeById.get(selectedSubjectIds[0]) : null;
  const inspectedAttachments = inspectedSubject ? graph.attachments.filter((attachment) => attachment.subjectId === inspectedSubject.id) : [];
  const inspectedRelations = inspectedSubject ? graph.relations.filter((relation) => relation.fromId === inspectedSubject.id || relation.toId === inspectedSubject.id) : [];
  const inspectedShares = inspectedSubject ? graph.relations.filter((relation) => relation.relation === "shareholding" && relation.toId === inspectedSubject.id && typeof relation.sharePercent === "number") : [];

  return (
    <div className="compliance-plane interactive-subject-graph" aria-label={copy(locale, "Draggable relationship graph for two companies and three individuals", "可拖动的 2 家公司与 3 名自然人主体关系图谱")} data-semantic-localized>
      <header className="subject-graph-heading">
        <div><Icon name="compliance" /><span><strong>{copy(locale, "Entity relationships", "主体关系")}</strong></span></div>
        <div className="graph-toolbar" role="group" aria-label={copy(locale, "Relationship graph controls", "图谱视图操作")}>
          <Button aria-label={copy(locale, "Zoom out relationship graph", "缩小图谱")} onClick={() => zoomAt(viewport.scale - .12)}>−</Button>
          <span>{Math.round(viewport.scale * 100)}%</span>
          <Button aria-label={copy(locale, "Zoom in relationship graph", "放大图谱")} onClick={() => zoomAt(viewport.scale + .12)}>＋</Button>
          <Button aria-label={copy(locale, "Fit entity relationships to canvas", "适配主体关系画布")} onClick={fitCanvas} title={copy(locale, "Fit canvas", "适配画布")}>{copy(locale, "Fit", "适配")}</Button>
          <Button aria-label={copy(locale, "Restore default entity-relationship layout", "恢复主体关系默认布局")} onClick={resetLayout} title={copy(locale, "Restore default layout", "恢复默认布局")}>{copy(locale, "Reset", "重置")}</Button>
        </div>
      </header>
      <div className={`interactive-graph-layout ${selectedSubjectIds.length ? "is-inspector-open" : ""}`}>
        <div
          aria-label={copy(locale, "Interactive entity-relationship canvas; arrow keys pan, plus and minus zoom, 0 fits, and Escape clears selection", "主体关系可操作画布；方向键平移，加减键缩放，0 适配，Escape 清除选择")}
          className="subject-graph-viewport"
          onKeyDown={handleCanvasKey}
          onPointerDown={beginPan}
          onPointerMove={movePan}
          onPointerUp={endPan}
          onPointerCancel={endPan}
          onLostPointerCapture={endPan}
          ref={viewportRef}
          tabIndex={0}
        >
          <div className="subject-graph-world" style={{ width: WORLD.width, height: WORLD.height, transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})` }}>
            <svg aria-label={copy(locale, "Entity relationship edges", "主体关系边")} className="subject-graph-edges" height={WORLD.height} viewBox={`0 0 ${WORLD.width} ${WORLD.height}`} width={WORLD.width}>
              <defs><marker id="subject-arrow" markerHeight="6" markerWidth="6" orient="auto" refX="5" refY="3"><path d="M0,0 L6,3 L0,6 Z" /></marker></defs>
              {graph.relations.map((relation) => {
                const from = positions[relation.fromId];
                const to = positions[relation.toId];
                if (!from || !to) return null;
                const siblings = graph.relations.filter((item) => [item.fromId, item.toId].sort().join("|") === [relation.fromId, relation.toId].sort().join("|"));
                const offset = (siblings.findIndex((item) => item.id === relation.id) - (siblings.length - 1) / 2) * 10;
                const reference = evidenceById.get(relation.evidenceRefs[0]);
                const inPath = highlightedRelationIds.has(relation.id);
                const dimmed = selectedSubjectIds.length > 0 && !inPath;
                const evidenceTarget = targetFor(relation.evidenceRefs, relation.id);
                const edge = relationshipEdgePoints(from, to, NODE_DIAMETER, offset);
                return (
                  <g aria-label={copy(locale, `${subjectName(relation.fromId)} to ${subjectName(relation.toId)}: ${formatCanonicalLabel(relation.label, locale)} · ${evidenceText(reference, locale)}`, `${subjectName(relation.fromId)}到${subjectName(relation.toId)}：${relation.label}，${evidenceText(reference, locale)}`)} aria-pressed={sameReviewEvidenceTarget(evidenceTarget, selectedTarget)} className={`subject-graph-edge state-${reference?.locationStatus ?? "missing"} ${inPath ? "is-path" : ""} ${dimmed ? "is-dimmed" : ""} ${sameReviewEvidenceTarget(evidenceTarget, selectedTarget) ? "is-selected" : ""}`} data-graph-interactive="true" id={`fact-${relation.id}`} key={relation.id} onClick={() => activateEvidence(evidenceTarget)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); activateEvidence(evidenceTarget); } }} role="button" tabIndex={0}>
                    <line className="edge-hit" {...edge} />
                    <line className="edge-line" markerEnd="url(#subject-arrow)" {...edge} />
                    <text textAnchor="middle" x={(edge.x1 + edge.x2) / 2} y={(edge.y1 + edge.y2) / 2 - 6}>{formatCanonicalLabel(relation.label, locale)}</text>
                  </g>
                );
              })}
            </svg>
            {graph.nodes.map((node) => {
              const name = formatCanonicalNarrative(displayBusinessName(node.name, "主体待核验"), locale);
              const position = positions[node.id];
              if (!position) return null;
              const selectionIndex = selectedSubjectIds.indexOf(node.id);
              const inPath = highlightedNodeIds.has(node.id);
              const dimmed = selectedSubjectIds.length > 0 && !inPath;
              const shareholdings = graph.relations.filter((relation) => relation.relation === "shareholding" && relation.toId === node.id && typeof relation.sharePercent === "number");
              let shareOffset = 0;
              const shareSegments = shareholdings.map((relation, index) => {
                const start = shareOffset;
                shareOffset += clamp(relation.sharePercent ?? 0, 0, 100);
                return `${shareColors[index % shareColors.length]} ${start}% ${shareOffset}%`;
              });
              if (shareOffset < 100) shareSegments.push(`var(--color-border) ${shareOffset}% 100%`);
              const shareLabel = shareholdings.length ? shareholdings.map((relation) => `${subjectName(relation.fromId)} ${relation.sharePercent}%`).join(copy(locale, ", ", "，")) : copy(locale, "Shareholding pending / not provided", "股权待补 / 未提供");
              return (
                <article className={`graph-subject-node subject-kind-${node.kind} ${selectionIndex >= 0 ? "is-selected" : ""} ${inPath ? "is-path" : ""} ${dimmed ? "is-dimmed" : ""} ${shareholdings.length ? "has-share-ring" : "has-no-share-data"}`} data-graph-interactive="true" data-node-id={node.id} data-node-x={Math.round(position.x)} data-node-y={Math.round(position.y)} id={`fact-${node.id}`} key={node.id} style={cssVars({ left: `${position.x}px`, top: `${position.y}px`, "--share-ring": `conic-gradient(${shareSegments.join(", ")})` })} title={node.kind === "company" ? shareLabel : `${formatCanonicalLabel(node.role, locale)} · ${verificationLabel(node.verificationStatus)}`}>
                  <button
                    aria-label={copy(locale, `${selectionIndex === 0 ? "Start" : selectionIndex === 1 ? "End" : "Select"} ${name}; ${formatCanonicalLabel(node.role, locale)}; ${verificationLabel(node.verificationStatus)}${node.kind === "company" ? `; ${shareLabel}` : ""}; use arrow keys to move the node`, `${selectionIndex === 0 ? "起点" : selectionIndex === 1 ? "终点" : "选择"}${name}，${node.role}，${verificationLabels[node.verificationStatus]}${node.kind === "company" ? `，${shareLabel}` : ""}；方向键可移动节点`)}
                    aria-pressed={selectionIndex >= 0}
                    className="graph-node-handle"
                    onClick={() => { if (skipClickRef.current) { skipClickRef.current = false; return; } selectSubject(node.id); }}
                    onKeyDown={(event) => moveNodeWithKeyboard(node.id, event)}
                    onPointerDown={(event) => beginNodeDrag(node.id, event)}
                    onPointerMove={moveNodePointer}
                    onPointerUp={endNodeDrag}
                    onPointerCancel={endNodeDrag}
                    onLostPointerCapture={endNodeDrag}
                    type="button"
                  >
                    <span className="subject-node-icon"><Icon name={node.kind === "company" ? "compliance" : "business"} /></span>
                    <span><strong>{name}</strong><small>{formatCanonicalLabel(node.role, locale)}</small><em>{verificationLabel(node.verificationStatus)}</em>{node.kind === "company" && !shareholdings.length ? <i>{copy(locale, "Shareholding pending", "股权待补")}</i> : null}</span>
                    {selectionIndex >= 0 ? <b>{selectionIndex === 0 ? copy(locale, "Start", "起点") : copy(locale, "End", "终点")}</b> : null}
                  </button>
                </article>
              );
            })}
          </div>
        </div>
        {selectedSubjectIds.length ? <aside className="relationship-inspector" aria-live="polite">
          <header><div><strong>{inspectedSubject ? copy(locale, "Entity details", "主体详情") : copy(locale, "Relationship path", "关系路径")}</strong>{inspectedSubject ? <small>{copy(locale, "Shareholding · relationships · materials", "股权 · 关系 · 材料")}</small> : null}</div><Button onClick={clearSelection}>{copy(locale, "Clear", "清除")}</Button></header>
          {inspectedSubject ? <div className="subject-inspector-detail">
            <div className="subject-inspector-summary"><strong>{formatCanonicalNarrative(displayBusinessName(inspectedSubject.name, "主体待核验"), locale)}</strong><span>{formatCanonicalLabel(inspectedSubject.role, locale)} · {verificationLabel(inspectedSubject.verificationStatus)}</span></div>
            <div className="shareholding-legend" aria-label={copy(locale, `Shareholding percentages for ${formatCanonicalNarrative(displayBusinessName(inspectedSubject.name, "主体待核验"), locale)}`, `${displayBusinessName(inspectedSubject.name, "主体待核验")}股权比例`)}>
              {inspectedShares.length ? inspectedShares.map((relation, index) => <span key={relation.id}><i style={{ background: shareColors[index % shareColors.length] }} /><b>{subjectName(relation.fromId)}</b><strong>{relation.sharePercent}%</strong></span>) : <span className="is-missing"><b>{copy(locale, "Shareholding pending / not provided", "股权待补 / 未提供")}</b></span>}
            </div>
            <div className="subject-inspector-relations" aria-label={copy(locale, `Direct relationships for ${formatCanonicalNarrative(displayBusinessName(inspectedSubject.name, "主体待核验"), locale)}`, `${displayBusinessName(inspectedSubject.name, "主体待核验")}直接关系`)}>
              {inspectedRelations.map((relation) => { const reference = evidenceById.get(relation.evidenceRefs[0]); const target = targetFor(relation.evidenceRefs, relation.id); return <button aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : ""} key={relation.id} onClick={() => activateEvidence(target)} type="button"><span><b>{relationshipLabel(relation.relation)}</b><small>{subjectName(relation.fromId)} → {subjectName(relation.toId)}</small></span><strong>{formatCanonicalLabel(relation.label, locale)}</strong></button>; })}
            </div>
            <div className="subject-inspector-materials" aria-label={copy(locale, `Materials for ${formatCanonicalNarrative(displayBusinessName(inspectedSubject.name, "主体待核验"), locale)}`, `${displayBusinessName(inspectedSubject.name, "主体待核验")}材料`)}>
              {inspectedAttachments.map((attachment) => { const reference = evidenceById.get(attachment.evidenceRefs[0]); const fact = factById.get(attachment.factVersionId); const targetId = `graph-attachment-${attachment.id}`; const target = targetFor(attachment.evidenceRefs, targetId, attachment.factVersionId); return <button aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={`state-${reference?.locationStatus ?? "missing"} ${sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : ""}`} id={`fact-${targetId}`} key={attachment.id} onClick={() => activateEvidence(target)} type="button"><span><b>{formatCanonicalLabel(attachment.label, locale)}</b><small>{fact ? formatFactValue(fact.value, fact.unit, locale) : copy(locale, "Fact pending", "事实待补")}</small></span><small><Icon name="link" />{evidenceText(reference, locale)}</small></button>; })}
            </div>
          </div> : path ? <>
            <div className="relationship-summary"><strong>{path.nodeIds.length === 2 ? copy(locale, "Direct relationship", "直接关系") : copy(locale, `Shortest path · ${path.nodeIds.length - 1} hops`, `最短路径 · ${path.nodeIds.length - 1} 跳`)}</strong><span>{path.nodeIds.map(subjectName).join(" → ")}</span></div>
            <div className="relationship-path-list">
              {path.relationIds.map((relationId) => {
                const relation = graph.relations.find((item) => item.id === relationId)!;
                const reference = evidenceById.get(relation.evidenceRefs[0]);
                const relationTarget = targetFor(relation.evidenceRefs, relation.id);
                return <button aria-pressed={sameReviewEvidenceTarget(relationTarget, selectedTarget)} className={sameReviewEvidenceTarget(relationTarget, selectedTarget) ? "is-selected" : ""} data-relation-id={relation.id} key={relation.id} onClick={() => activateEvidence(relationTarget)} type="button"><span><b>{relationshipLabel(relation.relation)}</b><small>{subjectName(relation.fromId)} → {subjectName(relation.toId)}</small></span><strong>{formatCanonicalLabel(relation.label, locale)}</strong><small><Icon name="link" />{evidenceText(reference, locale)}</small></button>;
              })}
            </div>
          </> : <div className="relationship-empty is-unconnected"><strong>{copy(locale, "No relationship path found", "未发现关系路径")}</strong><span>{copy(locale, "The current relationship data contains no connecting record.", "当前关系中没有连接记录。")}</span></div>}
        </aside> : null}
      </div>
    </div>
  );
}

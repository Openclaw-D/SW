import { useEffect, useMemo, useRef, useState } from "react";
import {
  DIMENSION_IDS,
  type DimensionId,
  type DimensionSeriesRequest,
  type DimensionSeriesResponse,
  type DimensionViewMode,
  type EvidenceReference,
  type FactVersion,
  type GlobalRiskSummary,
  type ReviewEvidenceTarget,
  type RiskLevel,
  type WorkbenchProject,
} from "../contracts/workbench";
import { DimensionDetailView, ReviewSectionSummary } from "./DimensionDetailView";
import { ComplianceSubjectGraph } from "./ComplianceSubjectGraph";
import { Icon, dimensionColorVar } from "./icons";
import { displayBusinessName, groupRiskItems, sameReviewEvidenceTarget, scoreToGrade, selectedRiskItemId as deriveSelectedRiskItemId, toggledRiskLevel, type RiskDisplayItem } from "../lib/workbenchLogic";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatDimensionName, formatEvidenceLocationStatus, formatEvidenceLocator, formatFactValue, formatMaterialStatus, formatRiskLevel, formatServiceMessage, usePublicLocale } from "../lib/publicLocale";
import { Button, StatusMark, Tag } from "./ui";

export type ReviewSectionId = "risk" | DimensionId;

export const REVIEW_SECTION_IDS: readonly ReviewSectionId[] = ["risk", ...DIMENSION_IDS];

function FormalBusinessCorrection({ facts, pending, resultMessage, onSubmit }: { facts: FactVersion[]; pending: boolean; resultMessage: string | null; onSubmit: (factId: string, value: string, reason: string) => Promise<void> }) {
  const locale = usePublicLocale();
  const [factId, setFactId] = useState(facts[0]?.id ?? "");
  const selected = facts.find((fact) => fact.id === factId) ?? facts[0];
  const [value, setValue] = useState(selected ? String(selected.value) : "");
  const [reason, setReason] = useState(copy(locale, "Manually checked against supplemental material", "依据补充材料人工核对"));
  return (
    <details className="approval-correction review-formal-correction">
      <summary><Icon name="business" /><span>{copy(locale, "Formal business correction", "正式业务修正")}</span><small>{copy(locale, "Human Gate · creates a new fact version", "人工 Gate · 生成新事实版本")}</small></summary>
      <div className="correction-form">
        <label>{copy(locale, "Field", "字段")}<select aria-label={copy(locale, "Choose field to correct", "选择修正字段")} disabled={pending} onChange={(event) => { const next = facts.find((fact) => fact.id === event.target.value); setFactId(event.target.value); setValue(next ? String(next.value) : ""); }} value={selected?.id ?? ""}>{facts.map((fact) => <option key={fact.id} value={fact.id}>{formatCanonicalLabel(fact.label, locale)} · {formatFactValue(fact.value, fact.unit, locale)}</option>)}</select></label>
        <label>{copy(locale, "Proposed value", "建议值")}<input disabled={pending} onChange={(event) => setValue(event.target.value)} value={value} /></label>
        <label>{copy(locale, "Reason", "原因")}<input disabled={pending} onChange={(event) => setReason(event.target.value)} value={reason} /></label>
        <Button disabled={pending || !selected || !value.trim() || !reason.trim()} onClick={() => selected && void onSubmit(selected.id, value, reason)} variant="primary">{pending ? copy(locale, "Submitting…", "提交中…") : copy(locale, "Submit correction", "提交修正")}</Button>
      </div>
      {resultMessage ? <p className="form-status" role="status">{formatServiceMessage(resultMessage, locale)}</p> : null}
    </details>
  );
}

function evidenceLabel(evidence: EvidenceReference | undefined, locale: ReturnType<typeof usePublicLocale>) {
  if (!evidence) return copy(locale, "Evidence reference missing", "引用缺失");
  return `${formatCanonicalLabel(evidence.label, locale)} · ${formatEvidenceLocator(evidence.locator, evidence.locationStatus, locale)}`;
}

function ViewSwitch({ value, onChange }: { value: DimensionViewMode; onChange: (value: DimensionViewMode) => void }) {
  const locale = usePublicLocale();
  return (
    <div className="view-switch" aria-label={copy(locale, "Switch between visual and table views", "切换平面或表格视图")} role="group">
      {(["visual", "table"] as const).map((mode) => (
        <button aria-pressed={value === mode} className={value === mode ? "is-active" : ""} key={mode} onClick={() => onChange(mode)} type="button">
          {mode === "visual" ? copy(locale, "Visual", "平面") : copy(locale, "Table", "表格")}
        </button>
      ))}
    </div>
  );
}

function EvidenceState({ reference }: { reference: EvidenceReference | undefined }) {
  const locale = usePublicLocale();
  const label = !reference ? copy(locale, "No reference", "无引用") : formatEvidenceLocationStatus(reference.locationStatus, locale);
  return <small className={`evidence-state state-${reference?.locationStatus ?? "missing"}`}>{label}</small>;
}

function FactTable({ facts, evidence, selectedTarget, onEvidenceSelect }: { facts: FactVersion[]; evidence: EvidenceReference[]; selectedTarget: ReviewEvidenceTarget | null; onEvidenceSelect: (target: ReviewEvidenceTarget) => void }) {
  const locale = usePublicLocale();
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  if (!facts.length) return <div className="inline-empty"><strong>{copy(locale, "No fields", "暂无字段")}</strong><span>{copy(locale, "This section has no simulated facts to display.", "当前栏目没有可展示的模拟事实。")}</span></div>;
  return (
    <div className="fact-table" role="table" aria-label={copy(locale, "Key compliance facts", "合规关键信息")} data-semantic-localized>
      {facts.map((fact) => {
        const references = fact.evidenceRefs.map((id) => evidenceById.get(id)).filter(Boolean) as EvidenceReference[];
        const displayValue = formatFactValue(fact.value, fact.unit, locale);
        return (
          <div className={`fact-row ${selectedTarget?.reviewTargetId === fact.id && selectedTarget.factVersionId === fact.id ? "is-selected" : ""}`} data-fact-id={fact.id} id={`fact-${fact.id}`} key={fact.id} role="row">
            <span role="cell">{formatCanonicalLabel(fact.label, locale)}<small>{copy(locale, `Fact version ${fact.version}`, `事实版本 ${fact.version}`)}</small></span>
            <strong role="cell">{displayValue}</strong>
            <div className="evidence-group" role="cell">
              {references.length ? references.map((reference, index) => {
                const target: ReviewEvidenceTarget = { evidenceRef: reference.id, evidenceRefs: fact.evidenceRefs, dimensionId: fact.dimensionId, reviewTargetId: fact.id, factVersionId: fact.id };
                return (
                <button aria-label={copy(locale, `Locate evidence ${formatCanonicalLabel(reference.label, locale)} for ${formatCanonicalLabel(fact.label, locale)}`, `定位${fact.label}的${reference.label}`)} aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={`evidence-chip state-${reference.locationStatus} ${sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : ""}`} data-evidence-id={reference.id} key={reference.id} onClick={() => onEvidenceSelect(target)} type="button">
                  <Icon name="link" /><span>{evidenceLabel(reference, locale)}</span><EvidenceState reference={reference} />{references.length > 1 ? <b>{index + 1}/{references.length}</b> : null}
                </button>
              ); }) : <span className="evidence-missing">{copy(locale, "No evidence reference", "无证据引用")}</span>}
            </div>
            <StatusMark label={copy(locale, `Material recognition status for ${formatCanonicalLabel(fact.label, locale)}: ${formatMaterialStatus(references[0]?.materialStatus ?? "review", locale)}`, `${fact.label}材料识别状态`)} status={references[0]?.materialStatus ?? "review"} />
          </div>
        );
      })}
    </div>
  );
}

const riskLevelMeta: Array<{ id: RiskLevel; label: string }> = [
  { id: "forbid", label: "禁止" },
  { id: "risk", label: "风险" },
  { id: "confirm", label: "核实" },
  { id: "attention", label: "关注" },
  { id: "support", label: "支持" },
];

function RiskSection({ summary, evidence, selectedTarget, expanded: sectionExpanded, onEvidenceSelect, onToggleExpanded }: { summary: GlobalRiskSummary; evidence: EvidenceReference[]; selectedTarget: ReviewEvidenceTarget | null; expanded: boolean; onEvidenceSelect: (target: ReviewEvidenceTarget) => void; onToggleExpanded: () => void }) {
  const locale = usePublicLocale();
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const partyLabels = { business: copy(locale, "Business", "业务"), risk: copy(locale, "Risk", "风控"), joint: copy(locale, "Joint", "共同") };
  const groups = useMemo(() => groupRiskItems(summary), [summary]);
  const orderedGroups = useMemo(() => riskLevelMeta.flatMap((meta) => {
    const group = groups.find((candidate) => candidate.level === meta.id);
    return group ? [group] : [];
  }), [groups]);
  const [activeRiskLevel, setActiveRiskLevel] = useState<RiskLevel | null>(null);
  const [expandedRiskLevel, setExpandedRiskLevel] = useState<RiskLevel | null>(null);
  const [selectedRiskItemId, setSelectedRiskItemId] = useState<string | null>(null);
  const riskItems = useMemo(() => orderedGroups.flatMap((group) => group.items), [orderedGroups]);
  const selectedRiskItem = riskItems.find((item) => item.id === selectedRiskItemId);
  useEffect(() => {
    setSelectedRiskItemId((currentId) => deriveSelectedRiskItemId(groups, selectedTarget, currentId));
  }, [groups, selectedTarget]);
  useEffect(() => {
    if (!selectedTarget) return;
    const matchedItemId = deriveSelectedRiskItemId(groups, selectedTarget, selectedRiskItemId);
    const matchedItem = riskItems.find((item) => item.id === matchedItemId);
    if (matchedItem) setExpandedRiskLevel(matchedItem.level);
  }, [groups, riskItems, selectedRiskItemId, selectedTarget]);
  const highlightedRiskLevel = activeRiskLevel ?? selectedRiskItem?.level ?? expandedRiskLevel;
  const expandedGroup = orderedGroups.find((group) => group.level === expandedRiskLevel && group.items.length > 0) ?? null;
  const activateItem = (item: RiskDisplayItem, target: ReviewEvidenceTarget | null) => {
    if (target?.evidenceRef && target.reviewTargetId && evidenceById.has(target.evidenceRef)) {
      setSelectedRiskItemId(item.id);
      const evidenceRefs = item.evidenceTargets
        .filter((candidate) => candidate.reviewTargetId === target.reviewTargetId && candidate.factVersionId === target.factVersionId)
        .map((candidate) => candidate.evidenceRef);
      onEvidenceSelect({ ...target, evidenceRefs: evidenceRefs.length ? evidenceRefs : [target.evidenceRef] });
    }
  };
  const evidenceLinks = (item: RiskDisplayItem) => (
    <span className="risk-evidence-links">
      {item.evidenceTargets.map((target) => {
        const reference = evidenceById.get(target.evidenceRef);
        return reference && target.reviewTargetId
          ? <button aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : ""} data-evidence-id={target.evidenceRef} data-fact-version-id={target.factVersionId ?? ""} data-review-target-id={target.reviewTargetId} key={`${target.evidenceRef}-${target.reviewTargetId}`} onClick={() => activateItem(item, target)} title={target.unavailableReason ? formatCanonicalNarrative(target.unavailableReason, locale) : undefined} type="button"><Icon name="link" /><span>{evidenceLabel(reference, locale)}</span><EvidenceState reference={reference} /></button>
          : <span className="risk-evidence-unavailable" key={`${target.evidenceRef}-${target.reviewTargetId ?? "unavailable"}`} title={target.unavailableReason ? formatCanonicalNarrative(target.unavailableReason, locale) : copy(locale, "Evidence reference does not exist", "证据引用不存在")}><Icon name="link" />{copy(locale, "Reference missing", "引用缺失")}<small>{copy(locale, "Unavailable", "不可用")}</small></span>;
      })}
    </span>
  );
  return (
    <section className={`dimension-section global-risk-section risk-level-${summary.level} ${sectionExpanded ? "is-section-expanded" : "is-section-collapsed"}`} data-semantic-localized id="review-risk">
      <h1 className="visually-hidden" id="six-dimension-overview">{copy(locale, "Risk", "风险")}</h1>
      <ReviewSectionSummary expanded={sectionExpanded} headingAriaHidden onToggle={onToggleExpanded} sectionId="risk" summary={copy(locale, `${riskItems.length} items across five levels · ${summary.pendingHumanDeterminations.length} review threads awaiting human determination`, `五级共 ${riskItems.length} 项 · 待核主线 ${summary.pendingHumanDeterminations.length} 项`)} title={copy(locale, "Risk", "风险")} />
      <div className="review-section-body" hidden={!sectionExpanded} id="review-section-body-risk">
        <div className="risk-groups" aria-label={copy(locale, "Five horizontal risk levels—Prohibited, Risk, Verify, Monitor, Support—with shared detail", "禁止、风险、核实、关注、支持五级横向风险卡与共享详情")}>
          <div className="risk-level-cards">
          {orderedGroups.map((group) => {
            const meta = riskLevelMeta.find((item) => item.id === group.level)!;
            const expandable = group.items.length > 0;
            const expanded = expandable && expandedRiskLevel === group.level;
            const panelId = `risk-group-panel-${group.level}`;
            return (
              <button
                aria-controls={panelId}
                aria-expanded={expanded}
                aria-label={copy(locale, `${formatRiskLevel(group.level, locale)} · ${group.items.length} items${expandable ? " · select for details" : ""}`, `${meta.label}，${group.items.length} 项${expandable ? "，点击查看详情" : ""}`)}
                className={`risk-level-card risk-level-${group.level} ${expanded ? "is-expanded" : ""} ${highlightedRiskLevel === group.level ? "is-highlighted" : ""} ${highlightedRiskLevel && highlightedRiskLevel !== group.level ? "is-dimmed" : ""}`}
                data-risk-level={group.level}
                key={group.level}
                onClick={() => setExpandedRiskLevel((current) => toggledRiskLevel(current, group.level, group.items.length))}
                onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setActiveRiskLevel(null); }}
                onFocusCapture={() => setActiveRiskLevel(group.level)}
                onPointerEnter={() => setActiveRiskLevel(group.level)}
                onPointerLeave={() => setActiveRiskLevel(null)}
                type="button"
              >
                <span className="risk-group-marker" aria-hidden="true" />
                <strong>{formatRiskLevel(group.level, locale)}</strong>
                <b aria-label={copy(locale, `${group.items.length} items`, `${group.items.length} 项`)}>{group.items.length}</b>
                {expandable ? <Icon name="chevron" /> : null}
              </button>
            );
          })}
          </div>
          {expandedGroup ? <section className={`risk-group risk-level-detail risk-level-${expandedGroup.level} is-expanded`} data-risk-level={expandedGroup.level} id={`risk-group-panel-${expandedGroup.level}`}>
            <div className="risk-group-items">
              {expandedGroup.items.map((item) => (
                <article className={`risk-row risk-level-${item.level} ${selectedRiskItem?.id === item.id ? "is-selected" : ""} ${selectedRiskItem && selectedRiskItem.id !== item.id ? "is-dimmed" : ""}`} id={`fact-${item.id}`} key={item.id}>
                  <span><small>{formatCanonicalNarrative(item.sourceLabel, locale)}</small></span>
                  {item.primaryTarget?.reviewTargetId
                    ? <button aria-pressed={selectedRiskItem?.id === item.id} className="risk-row-title" onClick={() => activateItem(item, item.primaryTarget)} type="button"><strong>{formatCanonicalNarrative(item.title, locale)}</strong></button>
                    : <span className="risk-row-title is-unavailable"><strong>{formatCanonicalNarrative(item.title, locale)}</strong><small>{copy(locale, "Awaiting location", "待定位")}</small></span>}
                  <span>{formatCanonicalNarrative(item.detail, locale)}</span>
                  {evidenceLinks(item)}
                  <span><b>{partyLabels[item.responsibleParty]}</b><small>{formatCanonicalNarrative(item.nextAction, locale)}</small></span>
                </article>
              ))}
            </div>
          </section> : null}
        </div>
      </div>
    </section>
  );
}

function ComplianceSection({ dimension, graph, facts, evidence, selectedTarget, expanded, onEvidenceSelect, onToggleExpanded }: { dimension: WorkbenchProject["dimensions"][number]; graph: WorkbenchProject["complianceGraph"]; facts: FactVersion[]; evidence: EvidenceReference[]; selectedTarget: ReviewEvidenceTarget | null; expanded: boolean; onEvidenceSelect: (target: ReviewEvidenceTarget) => void; onToggleExpanded: () => void }) {
  const locale = usePublicLocale();
  const [view, setView] = useState<DimensionViewMode>("visual");
  return (
    <section className={`dimension-section compliance-section ${expanded ? "is-section-expanded" : "is-section-collapsed"}`} data-dimension-id="compliance" data-semantic-localized id="dimension-compliance" style={{ "--dimension-color": dimensionColorVar.compliance } as React.CSSProperties}>
      <ReviewSectionSummary controls={<><Tag tone="neutral">{scoreToGrade(dimension.score)} · {dimension.score}{copy(locale, " points", "分")}</Tag><ViewSwitch onChange={setView} value={view} /></>} expanded={expanded} onToggle={onToggleExpanded} sectionId="compliance" summary={copy(locale, "Business license · identity document · articles of association · external registry · entity litigation · individual litigation", "营业执照 · 身份证 · 章程 · 外部工商 · 主体涉诉 · 个人涉诉")} title={formatDimensionName("compliance", locale, dimension.name)} />
      <div className="review-section-body" hidden={!expanded} id="review-section-body-compliance">
        <div className="dimension-context"><span>{copy(locale, "Business license · identity document · articles of association · external registry · entity litigation · individual litigation", "营业执照 · 身份证 · 章程 · 外部工商 · 主体涉诉 · 个人涉诉")}</span></div>
        <div hidden={view !== "visual"}><ComplianceSubjectGraph evidence={evidence} facts={facts} graph={graph} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} /></div>
        <div hidden={view !== "table"}><FactTable evidence={evidence} facts={facts} onEvidenceSelect={onEvidenceSelect} selectedTarget={selectedTarget} /></div>
      </div>
    </section>
  );
}

export function ReviewCanvas({ data, facts, activeReviewId, selectedTarget, selectedProductionStageId, collapsed, canCorrect, correctionPending, correctionMessage, onActiveReviewChange, onCorrection, onEvidenceSelect, onProductionStageSelect, onTimeSeriesRequest, onToggleCollapsed }: { data: WorkbenchProject; facts: FactVersion[]; activeReviewId: ReviewSectionId; selectedTarget: ReviewEvidenceTarget | null; selectedProductionStageId: string; collapsed: boolean; canCorrect: boolean; correctionPending: boolean; correctionMessage: string | null; onActiveReviewChange: (id: ReviewSectionId) => void; onCorrection: (factId: string, value: string, reason: string) => Promise<void>; onEvidenceSelect: (target: ReviewEvidenceTarget) => void; onProductionStageSelect: (stageId: string, imageId: string) => void; onTimeSeriesRequest: (request: DimensionSeriesRequest) => Promise<DimensionSeriesResponse>; onToggleCollapsed: () => void }) {
  const locale = usePublicLocale();
  const canvasRef = useRef<HTMLElement>(null);
  const [expandedSectionIds, setExpandedSectionIds] = useState<Set<ReviewSectionId>>(() => new Set(REVIEW_SECTION_IDS));
  const compliance = data.dimensions.find((item) => item.id === "compliance");
  const borrower = displayBusinessName(data.complianceGraph.nodes.find((node) => node.kind === "company" && node.role.includes("承租"))?.name ?? data.project.name, "承租主体待核验");
  const details = useMemo(() => new Map(data.dimensionDetails.map((detail) => [detail.dimensionId, detail])), [data.dimensionDetails]);
  const toggleSection = (id: ReviewSectionId) => {
    setExpandedSectionIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  useEffect(() => {
    const dimensionId = selectedTarget?.dimensionId;
    if (!dimensionId) return;
    setExpandedSectionIds((current) => {
      if (current.has(dimensionId)) return current;
      const next = new Set(current);
      next.add(dimensionId);
      return next;
    });
  }, [selectedTarget]);
  if (!compliance) return null;
  const handleScroll = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const canvasTop = canvas.getBoundingClientRect().top;
    const ids: ReviewSectionId[] = ["risk", ...data.dimensions.map((item) => item.id)];
    let next: ReviewSectionId = "risk";
    for (const id of ids) {
      const element = canvas.querySelector<HTMLElement>(id === "risk" ? "#review-risk" : `#dimension-${id}`);
      if (element && element.getBoundingClientRect().top - canvasTop <= 150) next = id;
    }
    if (next !== activeReviewId) onActiveReviewChange(next);
  };
  return (
    <main className={`review-canvas ${collapsed ? "is-collapsed" : ""}`} aria-label={copy(locale, "Risk and six-dimension vertical review", "风险与六维纵向审查页面")} data-semantic-localized id="review-pane" onScroll={handleScroll} ref={canvasRef}>
      {collapsed ? (
        <button aria-controls="review-pane" aria-expanded={false} aria-label={copy(locale, "Expand review canvas from the upper-left corner", "从左上角展开审查画布")} className="pane-corner-anchor review-corner-anchor" onClick={onToggleCollapsed} title={copy(locale, "Expand review canvas from the upper-left corner", "从左上角展开审查画布")} type="button"><span aria-hidden="true" className="pane-corner-glyph">↘</span></button>
      ) : (
        <>
          <header className="review-pane-heading"><button aria-controls="review-pane" aria-expanded aria-label={copy(locale, "Collapse review canvas to the upper-left corner", "收起审查画布至左上角")} className="pane-corner-anchor review-corner-anchor" onClick={onToggleCollapsed} title={copy(locale, "Collapse review canvas to the upper-left corner", "收起审查画布至左上角")} type="button"><span aria-hidden="true" className="pane-corner-glyph">↖</span></button><span className="review-pane-title"><strong>{copy(locale, "Review canvas", "审查画布")}</strong><small>{copy(locale, "Risk first · continuous six-dimension review", "风险置顶 · 六维连续审查")}</small></span></header>
          {canCorrect && facts.some((fact) => fact.dimensionId === "compliance") ? <FormalBusinessCorrection facts={facts.filter((fact) => fact.dimensionId === "compliance")} onSubmit={onCorrection} pending={correctionPending} resultMessage={correctionMessage} /> : null}
          <RiskSection evidence={data.evidence} expanded={expandedSectionIds.has("risk")} onEvidenceSelect={onEvidenceSelect} onToggleExpanded={() => toggleSection("risk")} selectedTarget={selectedTarget} summary={data.riskSummary} />
          <ComplianceSection dimension={compliance} evidence={data.evidence} expanded={expandedSectionIds.has("compliance")} facts={facts.filter((fact) => fact.dimensionId === "compliance")} graph={data.complianceGraph} onEvidenceSelect={onEvidenceSelect} onToggleExpanded={() => toggleSection("compliance")} selectedTarget={selectedTarget} />
          {data.dimensions.filter((item) => item.id !== "compliance").map((dimension) => {
            const detail = details.get(dimension.id);
            return detail ? <DimensionDetailView
              borrower={borrower}
              detail={detail}
              dimension={dimension}
              evidence={data.evidence}
              expanded={expandedSectionIds.has(dimension.id)}
              financedEquipment={dimension.id === "transaction" || dimension.id === "revenue" ? data.financedEquipment : undefined}
              key={dimension.id}
              materials={data.materials}
              onEvidenceSelect={(target) => onEvidenceSelect({ ...target, dimensionId: dimension.id })}
              onProductionStageSelect={dimension.id === "production" ? onProductionStageSelect : undefined}
              onTimeSeriesRequest={onTimeSeriesRequest}
              onToggleExpanded={() => toggleSection(dimension.id)}
              onsiteAssets={dimension.id === "production" ? data.onsiteAssets : undefined}
              operatingEquipment={dimension.id === "production" ? data.operatingEquipment : undefined}
              productionEnergy={dimension.id === "production" ? data.productionEnergy : undefined}
              productionStages={dimension.id === "production" ? data.productionStages : undefined}
              projectId={data.project.id}
              referenceImages={data.referenceImages}
              selectedTarget={selectedTarget}
              selectedProductionStageId={selectedProductionStageId}
            /> : null;
          })}
        </>
      )}
    </main>
  );
}

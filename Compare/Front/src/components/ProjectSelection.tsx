import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, DragEvent as ReactDragEvent, KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent } from "react";
import { displayBusinessName, displayIndustryName, INDUSTRY_DISPLAY_ORDER } from "../lib/workbenchLogic";
import {
  GROUP_BASES,
  GROUP_BASIS_LABELS,
  PROJECT_VIEW_LABELS,
  PROJECT_VIEWS,
  type GroupBasis,
  type ProjectCatalogItem,
  type ProjectMaterialStatus,
  type ProjectView,
} from "../contracts/projectSelection";
import { groupProjectValue } from "../mock/projectCatalog";
import { CompactDimensionDial } from "./CompactDimensionDial";
import { IndustryProcessIcon } from "./icons";
import {
  copy,
  formatProjectFinancingType,
  formatProjectIndustry,
  formatProjectMaterialStatus,
  formatProjectRegion,
  formatProjectSalesperson,
  formatProjectStore,
  formatProjectTimeBucket,
  formatRiskLevel,
  formatSyntheticProjectCompany,
  quotedSourceText,
  type PublicLocale,
} from "../lib/publicLocale";

const PREFERENCES_KEY = "compare-project-selection-preferences-v1";
const GROUP_OVERRIDES_KEY = "compare-project-group-overrides-v1";
const ENTRY_PREVIEW_COUNT = 6;
const MATERIAL_PREVIEW_LABELS: Record<ProjectMaterialStatus, string> = {
  材料齐备: "齐备",
  待补材料: "待补",
  人工复核: "复核",
};

const SORT_METRICS = ["decisionGrade", "amountWan", "durationDays", "createdAt"] as const;
type SortMetric = (typeof SORT_METRICS)[number];
type SortDirection = "asc" | "desc";
type GroupOverride = { group: string; reason: string };
type GroupOverrides = Record<string, GroupOverride>;

interface SelectionPreferences {
  view: ProjectView;
  groupBasis: GroupBasis;
  sortMetric: SortMetric;
  sortDirection: SortDirection;
  search: string;
}

const defaultPreferences: SelectionPreferences = {
  view: "list",
  groupBasis: "industry",
  sortMetric: "createdAt",
  sortDirection: "desc",
  search: "",
};

const SORT_METRIC_LABELS: Record<SortMetric, string> = {
  decisionGrade: "评级",
  amountWan: "金额",
  durationDays: "时效",
  createdAt: "进入时间",
};

const SORT_METRIC_DEFAULT_DIRECTION: Record<SortMetric, SortDirection> = {
  decisionGrade: "asc",
  amountWan: "desc",
  durationDays: "desc",
  createdAt: "desc",
};

const PROJECT_VIEW_ENGLISH: Record<ProjectView, string> = { list: "List", group: "Groups", cards: "Cards" };
const GROUP_BASIS_ENGLISH: Record<GroupBasis, string> = { industry: "Industry", risk: "Risk", time: "Time", region: "Region", store: "Team" };

function projectViewLabel(view: ProjectView, locale: PublicLocale) {
  return copy(locale, PROJECT_VIEW_ENGLISH[view], PROJECT_VIEW_LABELS[view]);
}

function groupBasisLabel(basis: GroupBasis, locale: PublicLocale) {
  return copy(locale, GROUP_BASIS_ENGLISH[basis], GROUP_BASIS_LABELS[basis]);
}

function projectCompany(project: ProjectCatalogItem, locale: PublicLocale) {
  return formatSyntheticProjectCompany(displayBusinessName(project.companyShortName, "客户主体待核验"), project.projectNo, locale);
}

function projectGroupLabel(value: string, basis: GroupBasis, locale: PublicLocale) {
  if (basis === "industry") return formatProjectIndustry(value, locale);
  if (basis === "risk") return formatRiskLevel(PROJECT_RISK_LEVEL_BY_BAND[value] ?? "confirm", locale);
  if (basis === "time") return formatProjectTimeBucket(value, locale);
  if (basis === "region") return formatProjectRegion(value, locale);
  return formatProjectStore(value, locale);
}

const PROJECT_RISK_LEVEL_BY_BAND: Record<string, ProjectCatalogItem["riskLevel"]> = {
  禁止: "forbid",
  风险: "risk",
  核实: "confirm",
  关注: "attention",
  支持: "support",
};

const DECISION_GRADE_ORDER = ["A", "B", "C", "D", "E"] as const;

export function DemoEntrance({ onEnter, locale = "en" }: { onEnter: () => void; locale?: PublicLocale }) {
  return (
    <main className="demo-entrance">
      <button
        aria-describedby="demo-entrance-truth"
        aria-label={copy(locale, "Enter the de-identified public demonstration", "进入脱敏公开演示系统")}
        className="demo-entrance-action"
        onClick={onEnter}
        type="button"
      >
        <img alt={copy(locale, "Abstract iris demo background", "深色彩色虹膜演示入口背景")} src="/demo-eye.png" />
        <span aria-hidden="true" className="demo-entrance-shade" />
        <span className="demo-entrance-content">
          <small>signal-council</small>
          <strong>{copy(locale, "See facts. Return to evidence.", "看见事实，回到证据")}</strong>
          <span>{copy(locale, "Enter public demo", "进入公开演示")}</span>
        </span>
      </button>
      <p id="demo-entrance-truth">
        <b>{copy(locale, "Authenticated intranet Demo entry.", "已认证的内网 Demo 入口。")}</b>
        <span>{copy(locale, "24 isolated projects share a complete de-identified standard fact template. Scores, evidence, and decisions remain advisory and subject to human gates.", "24 个隔离项目共用完整脱敏标准事实模板；评分、证据和建议仍须经过人工 Gate。")}</span>
      </p>
    </main>
  );
}

function readJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    return JSON.parse(localStorage.getItem(key) ?? "null") ?? fallback;
  } catch {
    return fallback;
  }
}

function ViewGlyph({ view }: { view: ProjectView }) {
  return <span aria-hidden="true" className={`view-glyph view-glyph-${view}`}><i /><i /><i /><i /></span>;
}

function ProjectIdentity({ locale, project }: { locale: PublicLocale; project: ProjectCatalogItem }) {
  return (
    <div className="project-identity">
      <b>{project.projectNo}</b>
      <span>{projectCompany(project, locale)}</span>
      <small title={`${copy(locale, "Industry", "行业")}：${formatProjectIndustry(project.industry, locale)}`}>{formatProjectRegion(project.region, locale)}</small>
    </div>
  );
}

function MetaPair({ label, value }: { label: string; value: string }) {
  return <span className="project-meta-pair"><small>{label}</small><b>{value}</b></span>;
}

function toggleProject(selected: Set<string>, projectId: string) {
  const next = new Set(selected);
  if (next.has(projectId)) next.delete(projectId);
  else next.add(projectId);
  return next;
}

function chunks<T>(items: T[], size: number) {
  return Array.from({ length: Math.ceil(items.length / size) }, (_, index) => items.slice(index * size, index * size + size));
}

function previewProjects(projects: ProjectCatalogItem[], count: number) {
  if (projects.length <= count) return projects;
  return Array.from({ length: count }, (_, index) => projects[Math.floor(index * projects.length / count)]);
}

function amountBarStyle(amountWan: number) {
  const percent = Math.min(100, Math.max(0, amountWan / 5000 * 100));
  return { "--entry-amount-progress": `${percent}%` } as CSSProperties;
}

function durationRingStyle(durationDays: number) {
  const percent = durationDays <= 7 ? 25 : durationDays <= 15 ? 50 : durationDays <= 30 ? 75 : 100;
  return { "--entry-duration-progress": `${percent}%` } as CSSProperties;
}

function compactDate(value: string) {
  const [, month = "--", day = "--"] = value.slice(0, 10).split("-");
  return `${month}/${day}`;
}

function ProjectCardIndicators({ compact = false, locale, project }: { compact?: boolean; locale: PublicLocale; project: ProjectCatalogItem }) {
  const materialStatus = copy(locale, formatProjectMaterialStatus(project.materialStatus, locale), MATERIAL_PREVIEW_LABELS[project.materialStatus]);
  return (
    <div
      aria-label={copy(locale, `Amount CNY ${project.amountWan} 10k; industry ${formatProjectIndustry(project.industry, locale)}; elapsed ${project.durationDays} days; status ${materialStatus}`, `金额 ${project.amountWan} 万元；行业 ${project.industry}；时效 ${project.durationDays} 天；状态 ${materialStatus}`)}
      className={`project-card-indicators${compact ? " is-compact" : ""}`}
      role="group"
    >
      <span className="project-card-amount-indicator" title={copy(locale, `CNY ${project.amountWan} 10k; CNY 50m equals 100%`, `${project.amountWan} 万元，5000 万元为 100%`)}>
        <i aria-hidden="true" className="entry-preview-amount" style={amountBarStyle(project.amountWan)} />
        <b>{project.amountWan}{copy(locale, " ×10k", "万")}</b>
      </span>
      <span aria-label={`${copy(locale, "Industry", "行业")} ${formatProjectIndustry(project.industry, locale)}`} className="project-card-industry-indicator" role="img" title={`${copy(locale, "Industry", "行业")}：${formatProjectIndustry(project.industry, locale)}`}>
        <IndustryProcessIcon industry={project.industry} />
      </span>
      <span className="project-card-duration-indicator" title={copy(locale, `Elapsed: ${project.durationDays} days`, `时效：${project.durationDays} 天`)}>
        <i aria-hidden="true" className="entry-preview-duration" style={durationRingStyle(project.durationDays)}><b>{project.durationDays}</b></i>
      </span>
      <span className="project-card-status-indicator" title={`${copy(locale, "Status", "状态")}：${formatProjectMaterialStatus(project.materialStatus, locale)}`}>
        <small>{copy(locale, "Status", "状态")}</small><b className={`material-state material-state-${project.materialStatus}`}>{materialStatus}</b>
      </span>
    </div>
  );
}

function EntryPreview({ locale, projects, view }: { locale: PublicLocale; projects: ProjectCatalogItem[]; view: ProjectView }) {
  if (view === "list") {
    return (
      <div aria-hidden="true" className="entry-preview entry-preview-list">
        <div className="entry-preview-list-head"><span>{copy(locale, "No.", "序号")}</span><span>{copy(locale, "Grade", "评级")}</span><span>{copy(locale, "Company", "企业名称")}</span><span>{copy(locale, "Amount", "金额")}</span><span>{copy(locale, "Industry", "行业")}</span></div>
        {previewProjects(projects, ENTRY_PREVIEW_COUNT).map((project, index) => (
          <div className="entry-preview-list-row" key={project.projectId}>
            <span className="entry-preview-sequence">{index + 1}</span>
            <CompactDimensionDial decisionGrade={project.decisionGrade} dimensions={project.dimensions} size={50} variant="thumbnail" />
            <span className="entry-preview-company">
              <span><b>{projectCompany(project, locale)}</b><small>{formatProjectRegion(project.region, locale)}</small></span>
              <span className="entry-preview-duration" style={durationRingStyle(project.durationDays)} title={copy(locale, `Elapsed ${project.durationDays} days`, `时效 ${project.durationDays} 天`)}><b>{project.durationDays}</b></span>
            </span>
            <span className="entry-preview-amount" style={amountBarStyle(project.amountWan)} title={copy(locale, `CNY ${project.amountWan} 10k; CNY 50m equals 100%`, `${project.amountWan} 万元，5000 万元为 100%`)} />
            <span className="entry-preview-industry" title={formatProjectIndustry(project.industry, locale)}><IndustryProcessIcon industry={project.industry} /></span>
          </div>
        ))}
      </div>
    );
  }

  if (view === "group") {
    const byIndustry = new Map<string, ProjectCatalogItem[]>();
    projects.forEach((project) => byIndustry.set(project.industry, [...(byIndustry.get(project.industry) ?? []), project]));
    const orderedIndustries = [
      ...INDUSTRY_DISPLAY_ORDER.flatMap((industry) => byIndustry.has(industry) ? [[industry, byIndustry.get(industry)!] as const] : []),
      ...[...byIndustry.entries()].filter(([industry]) => !INDUSTRY_DISPLAY_ORDER.includes(industry as (typeof INDUSTRY_DISPLAY_ORDER)[number])),
    ];
    return (
      <div aria-hidden="true" className="entry-preview entry-preview-groups">
        {orderedIndustries.slice(0, ENTRY_PREVIEW_COUNT).map(([industry, items]) => {
          const groupItems = items.slice(0, ENTRY_PREVIEW_COUNT);
          const dialSize = groupItems.length >= 5 ? 32 : groupItems.length === 3 ? 48 : 50;
          return (
            <div className={`entry-preview-group count-${groupItems.length}`} key={industry}>
              <span>{groupItems.map((project) => <CompactDimensionDial decisionGrade={project.decisionGrade} dimensions={project.dimensions} key={project.projectId} size={dialSize} variant="thumbnail" />)}</span>
              <b>{copy(locale, formatProjectIndustry(industry, locale), displayIndustryName(industry))}</b>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div aria-hidden="true" className="entry-preview entry-preview-cards">
      {previewProjects(projects, ENTRY_PREVIEW_COUNT).map((project) => (
        <div className="entry-preview-card" key={project.projectId}>
          <div className="entry-preview-card-main">
            <CompactDimensionDial decisionGrade={project.decisionGrade} dimensions={project.dimensions} size={56} variant="thumbnail" />
            <span><b>{projectCompany(project, locale)}</b><small title={`${copy(locale, "Industry", "行业")}：${formatProjectIndustry(project.industry, locale)}`}>{formatProjectRegion(project.region, locale)}</small></span>
          </div>
          <ProjectCardIndicators compact locale={locale} project={project} />
        </div>
      ))}
    </div>
  );
}

export function ProjectSelectionEntry({ projects, onChoose, locale = "en" }: { projects: ProjectCatalogItem[]; onChoose: (view: ProjectView) => void; locale?: PublicLocale }) {
  const gridRef = useRef<HTMLElement>(null);
  const [dockingView, setDockingView] = useState<ProjectView | null>(null);

  const dockToBrowser = (view: ProjectView) => {
    if (dockingView) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || typeof Element.prototype.animate !== "function") {
      onChoose(view);
      return;
    }

    setDockingView(view);
    const targetWidth = window.innerWidth <= 980 ? 92 : 112;
    const targetHeight = 64;
    const targetLeft = window.innerWidth / 2 - targetWidth * 1.5;
    const headings = Array.from(gridRef.current?.querySelectorAll<HTMLElement>(".entry-option-heading") ?? []);

    headings.forEach((heading, index) => {
      const rect = heading.getBoundingClientRect();
      const scale = targetWidth / rect.width;
      const x = targetLeft + targetWidth * index - rect.left;
      const y = (targetHeight - rect.height * scale) / 2 - rect.top;
      heading.animate([
        { opacity: 1, transform: "translate(0, 0) scale(1)", transformOrigin: "top left" },
        { opacity: 1, transform: `translate(${x}px, ${y}px) scale(${scale})`, transformOrigin: "top left" },
      ], {
        duration: 420,
        easing: "cubic-bezier(.2, .72, .18, 1)",
        fill: "forwards",
      });
    });

    window.setTimeout(() => onChoose(view), 420);
  };

  return (
    <main className={`selection-entry${dockingView ? " is-docking" : ""}`}>
      <header className="selection-entry-header"><b className="selection-brand">signal-council</b><div><p>{copy(locale, "Choose a project view", "选择项目查看方式")}</p><small>{copy(locale, "24 fixed, de-identified public demo projects", "固定 24 项脱敏公开演示项目")}</small></div></header>
      <section aria-busy={dockingView ? "true" : undefined} className="selection-entry-grid" aria-label={copy(locale, "Project view choices", "项目查看方式")} ref={gridRef}>
        {PROJECT_VIEWS.map((view) => (
          <button className="selection-entry-option" key={view} onClick={() => dockToBrowser(view)} type="button">
            <span className="entry-option-heading">
              <ViewGlyph view={view} />
              <strong>{projectViewLabel(view, locale)}</strong>
            </span>
            <EntryPreview locale={locale} projects={projects} view={view} />
          </button>
        ))}
      </section>
      <footer className="selection-entry-footer"><span>{copy(locale, "Each project has isolated materials, facts, scores, evidence, and state.", "项目、材料包、事实、评分与证据固定一一绑定")}</span><span>{copy(locale, "All content is de-identified and synthetic.", "均为脱敏模拟演示数据")}</span></footer>
    </main>
  );
}

export function ProjectSelectionBrowser({
  projects,
  initialView,
  onEntry,
  onOpenProject,
  onViewChange,
  locale = "en",
}: {
  projects: ProjectCatalogItem[];
  initialView: ProjectView;
  onEntry: () => void;
  onOpenProject: (projectId: string, view: ProjectView) => void;
  onViewChange: (view: ProjectView) => void;
  locale?: PublicLocale;
}) {
  const stored = readJson<Partial<SelectionPreferences>>(PREFERENCES_KEY, defaultPreferences);
  const [view, setView] = useState<ProjectView>(initialView);
  const [search, setSearch] = useState(stored.search ?? "");
  const [sortMetric, setSortMetric] = useState<SortMetric>(stored.sortMetric ?? "createdAt");
  const [sortDirection, setSortDirection] = useState<SortDirection>(stored.sortDirection ?? "desc");
  const [groupBasis, setGroupBasis] = useState<GroupBasis>(stored.groupBasis ?? "industry");
  const [customMode, setCustomMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [overrides, setOverrides] = useState<GroupOverrides>(() => readJson<GroupOverrides>(GROUP_OVERRIDES_KEY, {}));
  const [pendingMove, setPendingMove] = useState<{ projectId: string; target: string } | null>(null);
  const [moveReason, setMoveReason] = useState("");

  useEffect(() => {
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ view, search, sortMetric, sortDirection, groupBasis } satisfies SelectionPreferences));
  }, [groupBasis, search, sortDirection, sortMetric, view]);

  const visibleProjects = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    const filtered = keyword ? projects.filter((project) => [
      project.projectNo,
      project.companyShortName,
      project.region,
      project.industry,
      project.store,
      project.salesperson,
      project.riskBand,
    ].some((value) => value.toLowerCase().includes(keyword))) : [...projects];

    return filtered.sort((left, right) => {
      let comparison = 0;
      if (sortMetric === "decisionGrade") comparison = DECISION_GRADE_ORDER.indexOf(left.decisionGrade) - DECISION_GRADE_ORDER.indexOf(right.decisionGrade);
      if (sortMetric === "amountWan") comparison = left.amountWan - right.amountWan;
      if (sortMetric === "durationDays") comparison = left.durationDays - right.durationDays;
      if (sortMetric === "createdAt") comparison = left.createdAt.localeCompare(right.createdAt);
      const directed = sortDirection === "asc" ? comparison : -comparison;
      return directed || left.projectNo.localeCompare(right.projectNo);
    });
  }, [projects, search, sortDirection, sortMetric]);

  const currentGroup = (project: ProjectCatalogItem) => overrides[`${groupBasis}:${project.projectId}`]?.group ?? groupProjectValue(project, groupBasis);
  const groupedProjects = useMemo(() => {
    const groups = new Map<string, ProjectCatalogItem[]>();
    visibleProjects.forEach((project) => {
      const label = overrides[`${groupBasis}:${project.projectId}`]?.group ?? groupProjectValue(project, groupBasis);
      groups.set(label, [...(groups.get(label) ?? []), project]);
    });
    return [...groups.entries()].flatMap(([label, items]) => chunks(items, 6).map((chunk, index, all) => ({
      id: `${label}-${index}`,
      label,
      suffix: all.length > 1 ? `${index + 1}/${all.length}` : "",
      projects: chunk,
    })));
  }, [groupBasis, overrides, visibleProjects]);

  const chooseView = (nextView: ProjectView) => {
    setView(nextView);
    onViewChange(nextView);
  };

  const chooseSortMetric = (nextMetric: SortMetric) => {
    if (nextMetric === sortMetric) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
      return;
    }
    setSortMetric(nextMetric);
    setSortDirection(SORT_METRIC_DEFAULT_DIRECTION[nextMetric]);
  };

  const sortMetricControl = (metric: SortMetric, className = "") => {
    const active = sortMetric === metric;
    const directionLabel = active ? copy(locale, sortDirection === "asc" ? "ascending" : "descending", sortDirection === "asc" ? "正序" : "倒序") : copy(locale, "select this metric", "选择此指标");
    return (
      <button
        aria-label={`${copy(locale, ({ decisionGrade: "Decision grade", amountWan: "Amount", durationDays: "Elapsed time", createdAt: "Entry time" } as const)[metric], SORT_METRIC_LABELS[metric])}，${directionLabel}`}
        aria-pressed={active}
        className={`selection-metric ${className}`}
        onClick={() => chooseSortMetric(metric)}
        type="button"
      >
        <span>{copy(locale, ({ decisionGrade: "Decision grade", amountWan: "Amount", durationDays: "Elapsed time", createdAt: "Entry time" } as const)[metric], SORT_METRIC_LABELS[metric])}</span>
        <b aria-hidden="true">{active ? (sortDirection === "asc" ? "↑" : "↓") : "↕"}</b>
      </button>
    );
  };

  const activateProject = (project: ProjectCatalogItem, event: ReactMouseEvent | ReactKeyboardEvent) => {
    if ("ctrlKey" in event && (event.ctrlKey || event.metaKey)) {
      setSelected((current) => toggleProject(current, project.projectId));
      return;
    }
    onOpenProject(project.projectId, view);
  };

  const requestMove = (event: ReactDragEvent, target: string) => {
    event.preventDefault();
    if (!customMode) return;
    const projectId = event.dataTransfer.getData("text/project-id");
    const project = projects.find((item) => item.projectId === projectId);
    if (!project || currentGroup(project) === target) return;
    setPendingMove({ projectId, target });
    setMoveReason("");
  };

  const confirmMove = () => {
    if (!pendingMove || !moveReason.trim()) return;
    const next = { ...overrides, [`${groupBasis}:${pendingMove.projectId}`]: { group: pendingMove.target, reason: moveReason.trim() } };
    setOverrides(next);
    localStorage.setItem(GROUP_OVERRIDES_KEY, JSON.stringify(next));
    setPendingMove(null);
    setMoveReason("");
  };

  const checkbox = (project: ProjectCatalogItem) => (
    <input
      aria-label={copy(locale, `Select ${project.projectNo}`, `选择 ${project.projectNo}`)}
      checked={selected.has(project.projectId)}
      onChange={() => setSelected((current) => toggleProject(current, project.projectId))}
      onClick={(event) => event.stopPropagation()}
      type="checkbox"
    />
  );

  return (
    <main className="selection-browser selection-browser-entering">
      <header className="selection-browser-header">
        <button className="selection-back" onClick={onEntry} type="button">← {copy(locale, "Entry", "入口")}</button>
        <nav aria-label={copy(locale, "Project view choices", "项目查看方式")} className="selection-view-switcher">
          {PROJECT_VIEWS.map((item) => (
            <button aria-current={view === item ? "page" : undefined} key={item} onClick={() => chooseView(item)} type="button">
              <ViewGlyph view={item} /><span>{projectViewLabel(item, locale)}</span>
            </button>
          ))}
        </nav>
        <p className="selection-fixed-note"><b>{copy(locale, "24 fixed projects", "固定 24 项目")}</b><span>{copy(locale, "Materials, facts, scores, and evidence are bound one-to-one.", "材料包、事实、评分、证据一一绑定")}</span></p>
      </header>

      <section className="selection-toolbar">
        <div className="selection-toolbar-summary"><b>{projectViewLabel(view, locale)}</b><span>{copy(locale, `${visibleProjects.length} projects${selected.size ? ` · ${selected.size} selected` : ""}`, `${visibleProjects.length} 项${selected.size ? ` · 已选 ${selected.size}` : ""}`)}</span></div>
        {view === "list" ? null : (
          <div aria-label={copy(locale, "Project metrics", "项目指标")} className="selection-metrics" role="group">
            {SORT_METRICS.map((metric) => <span key={metric}>{sortMetricControl(metric)}</span>)}
          </div>
        )}
        <label className="selection-search"><span>{copy(locale, "Search", "搜索")}</span><input onChange={(event) => setSearch(event.target.value)} placeholder={copy(locale, "Project no., company, region, industry, or team", "编号、公司、区域、行业、门店")} value={search} /></label>
        {view === "group" ? <div aria-label={copy(locale, "Grouping dimensions", "分组指标")} className="selection-group-metrics" role="group">{GROUP_BASES.map((basis) => <button aria-pressed={groupBasis === basis} key={basis} onClick={() => setGroupBasis(basis)} type="button">{groupBasisLabel(basis, locale)}</button>)}<button aria-pressed={customMode} className="custom-group-toggle" onClick={() => setCustomMode((current) => !current)} type="button">{copy(locale, customMode ? "Custom grouping on" : "Custom grouping", customMode ? "自定义中" : "自定义")}</button></div> : null}
      </section>

      <section className={`selection-content selection-content-${view}`}>
        {visibleProjects.length === 0 ? <div className="selection-empty"><b>{copy(locale, "No matching projects", "没有匹配项目")}</b><span>{copy(locale, "Shorten the keyword or change the filters.", "请缩短关键词或更换筛选条件。")}</span></div> : null}

        {view === "list" && visibleProjects.length ? (
          <div className="project-list" role="table" aria-label={copy(locale, "Project list", "项目清单")}>
            <div className="project-list-head" role="row"><span>{copy(locale, "Select", "选择")}</span>{sortMetricControl("decisionGrade", "is-list-head")}<span>{copy(locale, "Company", "企业名称")}</span>{sortMetricControl("amountWan", "is-list-head")}{sortMetricControl("durationDays", "is-list-head")}<span>{copy(locale, "Industry", "行业")}</span><span>{copy(locale, "Region", "区域")}</span><span>{copy(locale, "Salesperson", "业务员")}</span><span>{copy(locale, "Status", "状态")}</span>{sortMetricControl("createdAt", "is-list-head")}</div>
            {visibleProjects.map((project, index) => (
              <div className={`project-list-row ${selected.has(project.projectId) ? "is-selected" : ""}`} key={project.projectId} onClick={(event) => activateProject(project, event)} onKeyDown={(event) => { if (event.key === "Enter") activateProject(project, event); }} role="row" tabIndex={0}>
                <span className="project-list-select"><small>{index + 1}</small>{checkbox(project)}</span>
                <CompactDimensionDial decisionGrade={project.decisionGrade} dimensions={project.dimensions} size={64} variant="thumbnail" />
                <span className="project-list-company"><b>{projectCompany(project, locale)}</b><small>{project.projectNo}</small></span>
                <span className="project-list-amount"><b>{project.amountWan} {copy(locale, "×10k", "万")}</b><i className="entry-preview-amount" style={amountBarStyle(project.amountWan)} title={copy(locale, `CNY ${project.amountWan} 10k; CNY 50m equals 100%`, `${project.amountWan} 万元，5000 万元为 100%`)} /></span>
                <span className="project-list-duration" title={copy(locale, `Elapsed: ${project.durationDays} days`, `时效：${project.durationDays} 天`)}><i className="entry-preview-duration" style={durationRingStyle(project.durationDays)}><b>{project.durationDays}</b></i></span>
                <span className="project-list-industry"><i><IndustryProcessIcon industry={project.industry} /></i><b>{formatProjectIndustry(project.industry, locale)}</b><small>{formatProjectFinancingType(project.financingType, locale)}</small></span>
                <span className="project-list-region"><b>{formatProjectRegion(project.region, locale)}</b><small>{formatProjectStore(project.store, locale)}</small></span>
                <span className="project-list-salesperson"><b>{formatProjectSalesperson(project.salesperson, locale)}</b></span>
                <span className="project-list-status"><b className={`material-state material-state-${project.materialStatus}`}>{formatProjectMaterialStatus(project.materialStatus, locale)}</b><small>{copy(locale, "Risk", "风险")}：{formatRiskLevel(project.riskLevel, locale)}</small></span>
                <span><b>{compactDate(project.createdAt)}</b><small>{formatProjectTimeBucket(project.timeBucket, locale)}</small></span>
              </div>
            ))}
          </div>
        ) : null}

        {view === "cards" && visibleProjects.length ? (
          <div className="project-card-grid">
            {visibleProjects.map((project) => (
              <article className={`project-card ${selected.has(project.projectId) ? "is-selected" : ""}`} key={project.projectId} onClick={(event) => activateProject(project, event)} onKeyDown={(event) => { if (event.key === "Enter") activateProject(project, event); }} tabIndex={0}>
                <div className="project-card-top">{checkbox(project)}<span>{formatProjectFinancingType(project.financingType, locale)}</span></div>
                <div className="project-card-main"><CompactDimensionDial decisionGrade={project.decisionGrade} dimensions={project.dimensions} size={86} variant="thumbnail" /><ProjectIdentity locale={locale} project={project} /></div>
                <div className="project-card-body">
                  <ProjectCardIndicators locale={locale} project={project} />
                  <div className="project-card-secondary"><MetaPair label={copy(locale, "Team", "门店")} value={formatProjectStore(project.store, locale)} /><MetaPair label={copy(locale, "Salesperson", "业务员")} value={formatProjectSalesperson(project.salesperson, locale)} /><MetaPair label={copy(locale, "Risk", "风险")} value={formatRiskLevel(project.riskLevel, locale)} /></div>
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {view === "group" && visibleProjects.length ? (
          <div className={`project-group-grid ${customMode ? "is-custom" : ""}`}>
            {groupedProjects.map((group) => (
              <section className={`project-group-circle count-${group.projects.length}`} key={group.id} onDragOver={(event) => { if (customMode) event.preventDefault(); }} onDrop={(event) => requestMove(event, group.label)}>
                <header><b>{projectGroupLabel(group.label, groupBasis, locale)}</b>{group.suffix ? <small>{group.suffix}</small> : null}<span>{copy(locale, `${group.projects.length} projects`, `${group.projects.length} 项`)}</span></header>
                <div className="project-group-items">
                  {group.projects.map((project) => (
                    <button draggable={customMode} key={project.projectId} onClick={() => onOpenProject(project.projectId, view)} onDragStart={(event) => { event.dataTransfer.setData("text/project-id", project.projectId); event.dataTransfer.effectAllowed = "move"; }} title={overrides[`${groupBasis}:${project.projectId}`]?.reason ? copy(locale, `Custom reason: ${quotedSourceText(overrides[`${groupBasis}:${project.projectId}`].reason, locale)}`, `自定义原因：${overrides[`${groupBasis}:${project.projectId}`].reason}`) : `${projectCompany(project, locale)} · ${project.projectNo}`} type="button">
                      <CompactDimensionDial decisionGrade={project.decisionGrade} dimensions={project.dimensions} size={64} variant="thumbnail" />
                      <span>{projectCompany(project, locale)}</span><small>{project.projectNo.slice(-3)}</small>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : null}
      </section>

      <footer className="selection-browser-footer">{copy(locale, "Click to open a project. Use Ctrl / Command or the checkboxes for multi-select. All 24 projects are fixed, one-to-one, de-identified synthetic demo data.", "单击进入项目；Ctrl / Command 或复选框可多选。24 个项目均为固定一一绑定的脱敏模拟演示数据。")}</footer>

      {pendingMove ? (
        <div className="selection-modal-backdrop" role="presentation">
          <div aria-labelledby="move-title" aria-modal="true" className="selection-modal" role="dialog">
            <small>{copy(locale, "Custom grouping", "自定义分组")}</small><h2 id="move-title">{copy(locale, `Move to “${projectGroupLabel(pendingMove.target, groupBasis, locale)}”`, `移动到“${pendingMove.target}”`)}</h2>
            <p>{copy(locale, "This adjustment is outside the current automated determination. Enter a reason.", "该调整不属于当前自动认定结果，请填写调整原因。")}</p>
            <textarea autoFocus onChange={(event) => setMoveReason(event.target.value)} placeholder={copy(locale, "Example: this project is jointly handled by a designated team", "例如：该项目由指定门店联合跟进")} value={moveReason} />
            <div><button onClick={() => setPendingMove(null)} type="button">{copy(locale, "Cancel", "取消")}</button><button disabled={!moveReason.trim()} onClick={confirmMove} type="button">{copy(locale, "Confirm change", "确认调整")}</button></div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

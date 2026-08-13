import { useEffect, useState } from "react";
import { App } from "./App";
import { isProjectView, type ProjectCatalogItem, type ProjectView } from "./contracts/projectSelection";
import { DemoEntrance, ProjectSelectionBrowser, ProjectSelectionEntry } from "./components/ProjectSelection";
import { MockWorkbenchGateway } from "./gateway/mockWorkbenchGateway";
import { HttpWorkbenchGateway } from "./gateway/httpWorkbenchGateway";
import type { WorkbenchGateway } from "./gateway/workbenchGateway";
import { catalogProjectIdentity } from "./lib/workbenchLogic";
import { copy, PUBLIC_LOCALE_KEY, PublicLocaleContext, readPublicLocale, translateEnglishSurface, type PublicLocale } from "./lib/publicLocale";
import type { ReactNode } from "react";
import "./styles/project-selection.css";

const LAST_VIEW_KEY = "compare-project-selection-last-view-v1";

type RouteState =
  | { screen: "demo" }
  | { screen: "entry" }
  | { screen: "selection"; view: ProjectView }
  | { screen: "project"; projectId: string; from: ProjectView };

function routeFromLocation(): RouteState {
  const params = new URLSearchParams(window.location.search);
  const projectId = params.get("project");
  const from = isProjectView(params.get("from")) ? params.get("from") as ProjectView : "list";
  if (projectId) return { screen: "project", projectId, from };
  const view = params.get("view");
  if (isProjectView(view)) return { screen: "selection", view };
  if (params.get("select") === "1") return { screen: "entry" };
  return { screen: "demo" };
}

function routeUrl(route: RouteState) {
  const apiBase = new URLSearchParams(window.location.search).get("apiBase");
  const suffix = apiBase ? `&apiBase=${encodeURIComponent(apiBase)}` : "";
  if (route.screen === "demo") return apiBase ? `/?apiBase=${encodeURIComponent(apiBase)}` : "/";
  if (route.screen === "entry") return `/?select=1${suffix}`;
  if (route.screen === "selection") return `/?view=${route.view}${suffix}`;
  return `/?project=${encodeURIComponent(route.projectId)}&from=${route.from}${suffix}`;
}

function PublicSurface({ children, locale }: { children: ReactNode; locale: PublicLocale }) {
  useEffect(() => {
    if (locale !== "en") return;
    const root = document.getElementById("signal-council-public-surface");
    if (!root) return;
    const translate = () => translateEnglishSurface(root);
    translate();
    const observer = new MutationObserver(translate);
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [locale]);
  return <PublicLocaleContext.Provider value={locale}><div id="signal-council-public-surface">{children}</div></PublicLocaleContext.Provider>;
}

export function ProjectExperience() {
  const mockMode = import.meta.env.VITE_COMPARE_GATEWAY === "mock";
  const [route, setRoute] = useState<RouteState | null>(null);
  const [gateway, setGateway] = useState<WorkbenchGateway | null>(null);
  const [projects, setProjects] = useState<ProjectCatalogItem[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Start from the public English SSR default, then restore a user choice only
  // after hydration so the server and browser never render different trees.
  const [locale, setLocale] = useState<PublicLocale>("en");

  useEffect(() => { setLocale(readPublicLocale()); }, []);
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  const setPublicLocale = (next: PublicLocale) => { localStorage.setItem(PUBLIC_LOCALE_KEY, next); setLocale(next); };
  const languageControl = <div className="public-language-control" data-language-control aria-label={copy(locale, "Language", "语言")}><b>Signal Council · 见微</b><button aria-pressed={locale === "zh-CN"} onClick={() => setPublicLocale("zh-CN")} type="button">中</button><button aria-label="English" aria-pressed={locale === "en"} onClick={() => setPublicLocale("en")} type="button">E</button></div>;

  const installGateway = async (nextGateway: WorkbenchGateway) => {
    setLoadError(null);
    try {
      const nextProjects = await nextGateway.listProjects();
      if (nextProjects.length !== 24 || new Set(nextProjects.map((project) => project.projectId)).size !== 24) {
        throw new Error("固定演示目录必须包含 24 个唯一项目。");
      }
      setGateway(nextGateway);
      setProjects(nextProjects);
    } catch (reason) {
      setGateway(null);
      setProjects([]);
      setLoadError(reason instanceof Error ? reason.message : "无法读取项目目录。");
    }
  };

  useEffect(() => {
    const initialRoute = routeFromLocation();
    const initialGateway: WorkbenchGateway = mockMode
      ? new MockWorkbenchGateway()
      : new HttpWorkbenchGateway();
    void installGateway(initialGateway);
    setRoute(initialRoute);

    const handlePopState = () => setRoute(routeFromLocation());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = (nextRoute: RouteState) => {
    window.history.pushState({}, "", routeUrl(nextRoute));
    setRoute(nextRoute);
  };

  const openSelection = (view: ProjectView) => {
    localStorage.setItem(LAST_VIEW_KEY, view);
    navigate({ screen: "selection", view });
  };

  if (!route) {
    return <PublicSurface locale={locale}><div className="selection-loading"><b>Signal Council · 见微</b><span>{copy(locale, "Preparing the public demo…", "正在准备公开演示项目…")}</span></div></PublicSurface>;
  }

  if (route.screen === "demo") {
    return <PublicSurface locale={locale}>{languageControl}<DemoEntrance locale={locale} onEnter={() => navigate({ screen: "entry" })} /></PublicSurface>;
  }

  if (loadError) {
    return <PublicSurface locale={locale}><div className="selection-loading">{languageControl}<b>{copy(locale, "Project directory unavailable", "项目目录读取失败")}</b><span>{loadError}</span><button onClick={() => { if (gateway) void installGateway(gateway); else window.location.reload(); }} type="button">{copy(locale, "Retry", "重试")}</button></div></PublicSurface>;
  }

  if (!gateway) return <PublicSurface locale={locale}><div className="selection-loading">{languageControl}<b>Signal Council · 见微</b><span>{copy(locale, "Loading project directory…", "正在读取项目目录…")}</span></div></PublicSurface>;

  if (projects.length === 0) {
    return <PublicSurface locale={locale}><div className="selection-loading">{languageControl}<b>{copy(locale, "Project directory is empty", "项目目录为空")}</b><span>{copy(locale, "This service has no public demo projects.", "当前服务没有可进入的固定演示项目。")}</span><button onClick={() => void installGateway(gateway)} type="button">{copy(locale, "Reload directory", "重试目录")}</button></div></PublicSurface>;
  }

  if (route.screen === "entry") {
    return <PublicSurface locale={locale}>{languageControl}<ProjectSelectionEntry locale={locale} onChoose={openSelection} projects={projects} /></PublicSurface>;
  }

  if (route.screen === "selection") {
    return (<PublicSurface locale={locale}>
      <ProjectSelectionBrowser
        locale={locale}
        initialView={route.view}
        onEntry={() => navigate({ screen: "entry" })}
        onOpenProject={(projectId, view) => { localStorage.setItem(LAST_VIEW_KEY, view); navigate({ screen: "project", projectId, from: view }); }}
        onViewChange={(view) => { localStorage.setItem(LAST_VIEW_KEY, view); window.history.replaceState({}, "", routeUrl({ screen: "selection", view })); setRoute({ screen: "selection", view }); }}
        projects={projects}
      />
    </PublicSurface>);
  }

  const projectIdentity = catalogProjectIdentity(projects, route.projectId);
  if (!projectIdentity) {
    return <PublicSurface locale={locale}><div className="selection-loading">{languageControl}<b>{copy(locale, "Project not found", "项目未找到")}</b><span>{copy(locale, "The project is not in this demo batch.", "当前演示批次中没有该项目。")}</span><button onClick={() => navigate({ screen: "entry" })} type="button">{copy(locale, "Back to entry", "返回入口")}</button></div></PublicSurface>;
  }

  return (<PublicSurface locale={locale}>
      <App
      gateway={gateway}
      key={route.projectId}
      onBack={() => navigate({ screen: "selection", view: route.from })}
      projectId={projectIdentity.requestProjectId}
      projectNo={projectIdentity.projectNo}
        showSimulationControls={mockMode}
        locale={locale}
        onLocaleChange={setPublicLocale}
    />
  </PublicSurface>);
}

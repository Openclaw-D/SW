import { useEffect, useRef, useState } from "react";
import { App } from "./App";
import { isProjectView, type ProjectCatalogItem, type ProjectView } from "./contracts/projectSelection.ts";
import { ProjectSelectionBrowser, ProjectSelectionEntry } from "./components/ProjectSelection";
import { MockWorkbenchGateway } from "./gateway/mockWorkbenchGateway";
import { HttpWorkbenchGateway } from "./gateway/httpWorkbenchGateway";
import type { WorkbenchGateway } from "./gateway/workbenchGateway";
import { catalogProjectIdentity } from "./lib/workbenchLogic";
import { generateProjectCatalog } from "./mock/projectCatalog";
import { copy, PUBLIC_LOCALE_KEY, PublicLocaleContext, readPublicLocale, translateEnglishSurface, type PublicLocale } from "./lib/publicLocale";
import type { ReactNode } from "react";
import type { AccountRole, AuthenticatedAccount } from "./contracts/authentication";
import { AuthenticationClient, AuthenticationClientError, SessionExpiryCoordinator } from "./gateway/authenticationClient";
import "./styles/project-selection.css";

type RouteState =
  | { screen: "demo" }
  | { screen: "directory"; view: ProjectView }
  | { screen: "project"; projectId: string };

type AuthNotice = {
  kind: "not-authenticated" | "session-expired" | "credentials-rejected" | "signed-out" | "service-error";
  message: string;
};

function initialAuthNotice(reason: unknown): AuthNotice {
  if (reason instanceof AuthenticationClientError && reason.code === "session_expired") {
    return { kind: "session-expired", message: "会话已过期，请重新登录；登录后将返回原项目位置。" };
  }
  if (reason instanceof AuthenticationClientError && reason.code === "authentication_required") {
    return { kind: "not-authenticated", message: "当前尚未登录，请使用内网 Demo 账号继续。" };
  }
  return { kind: "service-error", message: reason instanceof Error ? reason.message : "暂时无法确认登录状态。" };
}

function loginFailureNotice(reason: unknown): AuthNotice {
  if (reason instanceof AuthenticationClientError && reason.code === "authentication_failed") {
    return { kind: "credentials-rejected", message: "账号或密码错误，请检查后重试。" };
  }
  return { kind: "service-error", message: reason instanceof Error ? reason.message : "登录失败。" };
}

function routeFromLocation(): RouteState {
  const params = new URLSearchParams(window.location.search);
  const projectId = params.get("project");
  if (projectId) return { screen: "project", projectId };
  const directoryView = params.get("directory");
  if (isProjectView(directoryView)) return { screen: "directory", view: directoryView };
  return { screen: "demo" };
}

function routeUrl(route: RouteState) {
  const apiBase = new URLSearchParams(window.location.search).get("apiBase");
  const suffix = apiBase ? `&apiBase=${encodeURIComponent(apiBase)}` : "";
  if (route.screen === "demo") return apiBase ? `/?apiBase=${encodeURIComponent(apiBase)}` : "/";
  if (route.screen === "directory") return `/?directory=${route.view}${suffix}`;
  return `/?project=${encodeURIComponent(route.projectId)}${suffix}`;
}

const PUBLIC_DIRECTORY_PROJECTS = generateProjectCatalog(
  20260816,
  new Date(Date.UTC(2026, 7, 16, 12, 0, 0)),
);

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
  const [account, setAccount] = useState<AuthenticatedAccount | null>(mockMode ? { accountId: "mock-business", username: "business", displayName: "业务", role: "business" } : null);
  const [authState, setAuthState] = useState<"recovering" | "signed-out" | "ready">(mockMode ? "ready" : "recovering");
  const [authNotice, setAuthNotice] = useState<AuthNotice | null>(null);
  const [authPending, setAuthPending] = useState(false);
  const [loginUsername, setLoginUsername] = useState("business");
  const [loginPassword, setLoginPassword] = useState("");
  const [authClient] = useState(() => new AuthenticationClient());
  const [sessionExpiryCoordinator] = useState(() => new SessionExpiryCoordinator(authClient));
  const authStateRef = useRef(authState);
  const authGenerationRef = useRef(0);
  // Start from the public English SSR default, then restore a user choice only
  // after hydration so the server and browser never render different trees.
  const [locale, setLocale] = useState<PublicLocale>("en");

  useEffect(() => { setLocale(readPublicLocale()); }, []);
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  const setPublicLocale = (next: PublicLocale) => { localStorage.setItem(PUBLIC_LOCALE_KEY, next); setLocale(next); };
  const languageControl = <div className="public-language-control" data-language-control aria-label={copy(locale, "Language", "语言")}><b>signal-council</b><button aria-pressed={locale === "zh-CN"} onClick={() => setPublicLocale("zh-CN")} type="button">中</button><button aria-label="English" aria-pressed={locale === "en"} onClick={() => setPublicLocale("en")} type="button">E</button></div>;

  const installGateway = async (nextGateway: WorkbenchGateway) => {
    setLoadError(null);
    try {
      const nextProjects = await nextGateway.listProjects();
      if (nextProjects.length !== 1 || new Set(nextProjects.map((project) => project.projectId)).size !== 1) {
        throw new Error("公开演示需要一个唯一的 canonical 项目资料包。");
      }
      setGateway(nextGateway);
      setProjects(nextProjects);
    } catch (reason) {
      setGateway(null);
      setProjects([]);
      setLoadError(reason instanceof Error ? reason.message : "无法读取项目目录。");
    }
  };

  const showSignedOut = (notice: AuthNotice) => {
    authStateRef.current = "signed-out";
    setAccount(null);
    setGateway(null);
    setProjects([]);
    setLoadError(null);
    setAuthNotice(notice);
    setAuthState("signed-out");
  };

  useEffect(() => {
    const initialRoute = routeFromLocation();
    const initialGateway: WorkbenchGateway = mockMode
      ? new MockWorkbenchGateway()
      : new HttpWorkbenchGateway();
    if (mockMode) {
      void installGateway(initialGateway);
    } else {
      void authClient.me().then((current) => {
        setAccount(current);
        setAuthNotice(null);
        authStateRef.current = "ready";
        setAuthState("ready");
        return installGateway(initialGateway);
      }).catch((reason: unknown) => { showSignedOut(initialAuthNotice(reason)); });
    }
    setRoute(initialRoute);

    const handlePopState = () => setRoute(routeFromLocation());
    const handleExpired = () => {
      if (authStateRef.current !== "ready") return;
      const generation = authGenerationRef.current;
      authStateRef.current = "recovering";
      setAuthState("recovering");
      void sessionExpiryCoordinator.verify().then((verification) => {
        if (authGenerationRef.current !== generation) return;
        if (verification.status === "active") {
          setAccount(verification.account);
          authStateRef.current = "ready";
          setAuthState("ready");
          return;
        }
        showSignedOut({ kind: "session-expired", message: "会话已过期，请重新登录；登录后将返回原项目位置。" });
      }).catch(() => {
        if (authGenerationRef.current !== generation) return;
        showSignedOut({ kind: "session-expired", message: "会话已失效且无法恢复，请重新登录；登录后将返回原项目位置。" });
      });
    };
    window.addEventListener("popstate", handlePopState);
    window.addEventListener("signal-council-session-expired", handleExpired);
    return () => { window.removeEventListener("popstate", handlePopState); window.removeEventListener("signal-council-session-expired", handleExpired); };
  }, []);

  const login = async () => {
    if (!loginUsername.trim() || !loginPassword || authPending) return;
    const generation = authGenerationRef.current + 1;
    authGenerationRef.current = generation;
    setAuthPending(true); setAuthNotice(null);
    try {
      const current = await authClient.login(loginUsername, loginPassword);
      if (authGenerationRef.current !== generation) return;
      const nextGateway: WorkbenchGateway = new HttpWorkbenchGateway();
      setAccount(current); setLoginPassword("");
      authStateRef.current = "ready";
      setAuthState("ready");
      await installGateway(nextGateway);
    } catch (reason) {
      if (authGenerationRef.current === generation) showSignedOut(loginFailureNotice(reason));
    }
    finally { setAuthPending(false); }
  };

  const logout = async () => {
    authGenerationRef.current += 1;
    authStateRef.current = "recovering";
    setAuthState("recovering");
    setAuthPending(true);
    try { if (!mockMode) await authClient.logout(); }
    finally {
      showSignedOut({ kind: "signed-out", message: "已退出登录，可使用任一内网 Demo 账号重新进入。" });
      setAuthPending(false);
    }
  };

  const switchPrincipalRole = async (nextRole: Extract<AccountRole, "business" | "risk">) => {
    if (!account || account.role === nextRole || authPending) return;
    setLoginUsername(nextRole);
    setLoginPassword("");
    if (mockMode) {
      setAccount(nextRole === "business"
        ? { accountId: "mock-business", username: "business", displayName: "业务", role: "business" }
        : { accountId: "mock-risk", username: "risk", displayName: "风控", role: "risk" });
      return;
    }
    const generation = authGenerationRef.current + 1;
    authGenerationRef.current = generation;
    authStateRef.current = "recovering";
    setAuthState("recovering");
    setAuthPending(true);
    try {
      await authClient.logout();
    } finally {
      if (authGenerationRef.current === generation) {
        showSignedOut({
          kind: "signed-out",
          message: `已选择${nextRole === "risk" ? "风控" : "业务"}账号，请输入对应密码完成身份切换。`,
        });
      }
      setAuthPending(false);
    }
  };

  const navigate = (nextRoute: RouteState) => {
    window.history.pushState({}, "", routeUrl(nextRoute));
    setRoute(nextRoute);
  };

  if (!route || authState === "recovering") {
    return <PublicSurface locale={locale}><div className="selection-loading"><b>signal-council</b><span>{copy(locale, "Preparing the public demo…", "正在准备公开演示项目…")}</span></div></PublicSurface>;
  }

  if (authState === "signed-out" || !account) {
    const notice = authNotice ?? { kind: "not-authenticated" as const, message: "当前尚未登录，请使用内网 Demo 账号继续。" };
    const noticeIsError = notice.kind === "session-expired" || notice.kind === "credentials-rejected" || notice.kind === "service-error";
    return <PublicSurface locale={locale}><main className="signal-council-login"><form onSubmit={(event) => { event.preventDefault(); void login(); }}><span>signal-council</span><h1>内网 Demo 登录</h1><p>业务、风控与系统设置账号共享项目数据，操作权限由服务端会话强制执行。</p><div className={noticeIsError ? "login-error" : "login-notice"} role={noticeIsError ? "alert" : "status"}>{notice.message}</div><label>账号<input autoComplete="username" disabled={authPending} onChange={(event) => setLoginUsername(event.target.value)} value={loginUsername} /></label><label>密码<input autoComplete="current-password" disabled={authPending} onChange={(event) => setLoginPassword(event.target.value)} type="password" value={loginPassword} /></label><button disabled={authPending || !loginUsername.trim() || !loginPassword} type="submit">{authPending ? "登录中…" : "登录"}</button><small>初始密码仅限内网 Demo；公网使用前必须替换并轮换。</small></form></main></PublicSurface>;
  }

  const accountBar = <div className="signal-council-account" role="status"><span><b>{account.displayName}</b><small>{account.username} · {account.role === "leadership" ? "系统设置" : account.role === "business" ? "业务" : "风控"}</small></span><button disabled={authPending} onClick={() => void logout()} type="button">退出</button></div>;

  if (loadError) {
    return <PublicSurface locale={locale}><div className="selection-loading">{languageControl}{accountBar}<b>{copy(locale, "Project directory unavailable", "项目目录读取失败")}</b><span>{loadError}</span><button onClick={() => { if (gateway) void installGateway(gateway); else window.location.reload(); }} type="button">{copy(locale, "Retry", "重试")}</button></div></PublicSurface>;
  }

  if (!gateway) return <PublicSurface locale={locale}><div className="selection-loading">{languageControl}<b>signal-council</b><span>{copy(locale, "Loading project directory…", "正在读取项目目录…")}</span></div></PublicSurface>;

  if (projects.length === 0) {
    return <PublicSurface locale={locale}><div className="selection-loading">{languageControl}<b>{copy(locale, "Project directory is empty", "项目目录为空")}</b><span>{copy(locale, "This service has no public demo projects.", "当前服务没有可进入的固定演示项目。")}</span><button onClick={() => void installGateway(gateway)} type="button">{copy(locale, "Reload directory", "重试目录")}</button></div></PublicSurface>;
  }

  if (route.screen === "demo") {
    return <PublicSurface locale={locale}>{languageControl}{accountBar}<ProjectSelectionEntry locale={locale} onChoose={(view) => navigate({ screen: "directory", view })} projects={PUBLIC_DIRECTORY_PROJECTS} /></PublicSurface>;
  }

  const canonicalProjectId = projects[0].projectId;
  if (route.screen === "directory") {
    return <PublicSurface locale={locale}>{languageControl}{accountBar}<ProjectSelectionBrowser initialView={route.view} locale={locale} onEntry={() => navigate({ screen: "demo" })} onOpenProject={() => navigate({ screen: "project", projectId: canonicalProjectId })} onViewChange={(view) => navigate({ screen: "directory", view })} projects={PUBLIC_DIRECTORY_PROJECTS} /></PublicSurface>;
  }

  const projectIdentity = catalogProjectIdentity(projects, route.projectId);
  if (!projectIdentity) {
    return <PublicSurface locale={locale}><div className="selection-loading">{languageControl}<b>{copy(locale, "Project not found", "项目未找到")}</b><span>{copy(locale, "The project is not the configured public demo.", "当前项目不是已配置的公开演示项目。")}</span><button onClick={() => navigate({ screen: "demo" })} type="button">{copy(locale, "Back to entry", "返回入口")}</button></div></PublicSurface>;
  }

  return (<PublicSurface locale={locale}>
      <App
      account={account}
      gateway={gateway}
      key={route.projectId}
      onBack={() => navigate({ screen: "demo" })}
      onLogout={() => void logout()}
      onPrincipalRoleChange={(role) => void switchPrincipalRole(role)}
      projectId={projectIdentity.requestProjectId}
      projectNo={projectIdentity.projectNo}
        principalRoleChangePending={authPending}
        showSimulationControls={mockMode}
        presentationMode
        locale={locale}
        onLocaleChange={setPublicLocale}
    />
  </PublicSurface>);
}

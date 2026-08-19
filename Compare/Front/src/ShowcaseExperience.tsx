import { useState } from "react";
import { App } from "./App";
import type { AccountRole, AuthenticatedAccount } from "./contracts/authentication";
import { MockWorkbenchGateway } from "./gateway/mockWorkbenchGateway";
import { PublicLocaleContext } from "./lib/publicLocale";
import { generateProjectCatalog } from "./mock/projectCatalog";

const canonicalProject = generateProjectCatalog(
  20260812,
  new Date(2026, 7, 12, 9, 0, 0),
)[0];

if (!canonicalProject) throw new Error("展示入口缺少 canonical mock 项目。");

const showcaseGateway = new MockWorkbenchGateway(20260812, [canonicalProject]);
const showcaseAccount: AuthenticatedAccount = {
  accountId: "showcase-business",
  username: "business",
  displayName: "业务",
  role: "business",
};

type ShowcaseScreen = "login" | "projects" | "workbench";

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("business");
  const [password, setPassword] = useState("123456");
  const [error, setError] = useState("");

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== "123456") {
      setError("演示密码不正确，请使用 123456。");
      return;
    }
    if (!username.trim()) {
      setError("请输入演示账号。");
      return;
    }
    onLogin();
  }

  return (
    <main className="showcase-entry showcase-login">
      <section className="showcase-login__panel" aria-labelledby="showcase-login-title">
        <div className="showcase-mark" aria-hidden="true"><span>见</span></div>
        <p className="showcase-kicker">见微 · 项目预审工作台</p>
        <h1 id="showcase-login-title">进入演示项目</h1>
        <p className="showcase-description">本包包含一套固定的脱敏演示材料，仅用于产品沟通与页面演示。</p>
        <form onSubmit={submit}>
          <label>
            <span>演示账号</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            <span>演示密码</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          {error ? <p className="showcase-form-error" role="alert">{error}</p> : null}
          <button type="submit">登录</button>
        </form>
        <p className="showcase-login__hint">默认账号：business　默认密码：123456</p>
      </section>
    </main>
  );
}

function ProjectPool({ onOpen }: { onOpen: () => void }) {
  return (
    <main className="showcase-entry showcase-project-pool">
      <header className="showcase-pool-header">
        <div><span className="showcase-mark showcase-mark--small" aria-hidden="true"><span>见</span></span><strong>见微</strong></div>
        <span>项目池</span>
      </header>
      <section className="showcase-pool-content" aria-labelledby="showcase-project-pool-title">
        <div className="showcase-pool-heading">
          <div>
            <p className="showcase-kicker">项目池</p>
            <h1 id="showcase-project-pool-title">待审项目</h1>
            <p>选择项目后查看完整预审材料、风险要点与群聊协作记录。</p>
          </div>
          <span className="showcase-project-count">1 个项目</span>
        </div>
        <article className="showcase-project-card">
          <div className="showcase-project-card__tag">待预审</div>
          <div className="showcase-project-card__main">
            <h2>{canonicalProject.companyShortName} · {canonicalProject.financingType}</h2>
            <p>{canonicalProject.projectNo}　{canonicalProject.industry}　{canonicalProject.region}</p>
          </div>
          <dl>
            <div><dt>材料</dt><dd>9 项</dd></div>
            <div><dt>待办</dt><dd>3 项</dd></div>
            <div><dt>当前等级</dt><dd>{canonicalProject.decisionGrade}</dd></div>
          </dl>
          <button type="button" onClick={onOpen}>进入项目</button>
        </article>
      </section>
    </main>
  );
}

export function ShowcaseExperience() {
  const [screen, setScreen] = useState<ShowcaseScreen>("login");
  const noRoleChange = (_role: Extract<AccountRole, "business" | "risk">) => undefined;

  return (
    <PublicLocaleContext.Provider value="zh-CN">
      <div className="showcase-experience">
        {screen === "login" ? <LoginScreen onLogin={() => setScreen("projects")} /> : null}
        {screen === "projects" ? <ProjectPool onOpen={() => setScreen("workbench")} /> : null}
        {screen === "workbench" ? (
          <App
            account={showcaseAccount}
            gateway={showcaseGateway}
            key={canonicalProject.projectId}
            onBack={() => setScreen("projects")}
            onLogout={() => setScreen("login")}
            onPrincipalRoleChange={noRoleChange}
            projectId={canonicalProject.projectId}
            projectNo={canonicalProject.projectNo}
            locale="zh-CN"
            presentationMode
            showSimulationControls
          />
        ) : null}
      </div>
    </PublicLocaleContext.Provider>
  );
}

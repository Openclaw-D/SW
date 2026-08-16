import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { join } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { AuthenticationClient, AuthenticationClientError, SessionExpiryCoordinator } from "../src/gateway/authenticationClient.ts";
import { DEFAULT_WORKBENCH_API_BASE, HttpWorkbenchGateway } from "../src/gateway/httpWorkbenchGateway.ts";

const root = new URL("../", import.meta.url);
const compareRoot = new URL("../", root);
const execFileAsync = promisify(execFile);
const meta = { requestId: "auth-test", schemaVersion: "1.0", dataStatus: "simulated", source: "test", disclaimer: "test" };
const envelope = (data, status = 200, errors = []) => new Response(JSON.stringify({ data, meta, errors }), { status, headers: { "Content-Type": "application/json" } });

function listen(handler) {
  return new Promise((resolve, reject) => {
    const server = createServer(handler);
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({ server, port: address.port });
    });
  });
}

function close(server) {
  return new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

test("authentication client uses HttpOnly-cookie transport for login, me and logout", async () => {
  const calls = [];
  const account = { accountId: "account-business", username: "business", displayName: "业务", role: "business" };
  const client = new AuthenticationClient({ apiBase: "/api/v1/", fetchImpl: async (url, init) => { calls.push({ url: String(url), init }); return envelope(String(url).endsWith("/logout") ? { loggedOut: true } : account); } });
  assert.deepEqual(await client.login("business", "123456"), account);
  assert.deepEqual(await client.me(), account);
  assert.deepEqual(await client.logout(), { loggedOut: true });
  assert.deepEqual(calls.map((call) => call.url), ["/api/v1/auth/login", "/api/v1/auth/me", "/api/v1/auth/logout"]);
  assert.ok(calls.every((call) => call.init.credentials === "include"));
  assert.equal(JSON.parse(calls[0].init.body).password, "123456");
});

test("authentication errors retain API code and HTTP status", async () => {
  const client = new AuthenticationClient({
    fetchImpl: async () => envelope(null, 401, [{ code: "authentication_failed", message: "账号或密码错误。" }]),
  });
  const error = await client.login("business", "wrong").then(() => null, (reason) => reason);
  assert.ok(error instanceof AuthenticationClientError);
  assert.equal(error.code, "authentication_failed");
  assert.equal(error.httpStatus, 401);
  assert.equal(error.message, "账号或密码错误。");
});

test("session expiry verification coalesces concurrent 401 events and accepts a restored session", async () => {
  const account = { accountId: "account-business", username: "business", displayName: "业务", role: "business" };
  let releaseFirst;
  let calls = 0;
  const firstResponseReady = new Promise((resolve) => { releaseFirst = resolve; });
  const client = new AuthenticationClient({
    fetchImpl: async () => {
      const callNumber = ++calls;
      if (callNumber === 1) await firstResponseReady;
      return callNumber === 1
        ? envelope(null, 401, [{ code: "session_expired", message: "登录状态已失效，请重新登录。" }])
        : envelope(account);
    },
  });
  const coordinator = new SessionExpiryCoordinator(client);
  const first = coordinator.verify();
  const concurrent = coordinator.verify();
  assert.strictEqual(first, concurrent);
  assert.equal(calls, 1);
  releaseFirst();
  assert.deepEqual(await first, { status: "expired" });
  assert.deepEqual(await coordinator.verify(), { status: "active", account });
  assert.equal(calls, 2);
});

test("local readiness source cannot create sessions and Start uses a side-effect-free project URL", async () => {
  const source = await readFile(new URL("start-local.ps1", compareRoot), "utf8");
  const readiness = source.slice(source.indexOf("function Test-BackReady"), source.indexOf("function Test-FrontReady"));
  assert.doesNotMatch(source, /New-DemoAuthenticatedSession|\/auth\/login|WebRequestSession/);
  assert.doesNotMatch(readiness, /\/api\/v1|Method\s+Post|WebSession/);
  assert.match(readiness, /\$\(\$script:BackUrl\)\/health/);
  assert.match(source, /\[string\]::IsNullOrWhiteSpace\(\$ProjectId\)/);
  assert.match(source, /\$\(\$script:FrontUrl\)\/\?select=1/);
  assert.match(source, /EscapeDataString\(\$ProjectId\.Trim\(\)\)/);
});

test("local Check performs only anonymous GET readiness requests", async () => {
  const requests = [];
  const front = await listen((request, response) => {
    requests.push({ method: request.method, url: request.url, service: "front" });
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end("<!doctype html><title>signal-council</title>");
  });
  const back = await listen((request, response) => {
    requests.push({ method: request.method, url: request.url, service: "back" });
    if (request.url !== "/health") {
      response.writeHead(500, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ error: "unexpected path" }));
      return;
    }
    const headers = { "Content-Type": "application/json" };
    if (request.headers.origin) headers["Access-Control-Allow-Origin"] = request.headers.origin;
    response.writeHead(200, headers);
    response.end(JSON.stringify({ data: { status: "ok" } }));
  });
  try {
    const powershell = join(process.env.SystemRoot ?? "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
    const result = await execFileAsync(powershell, [
      "-NoProfile",
      "-ExecutionPolicy", "Bypass",
      "-File", fileURLToPath(new URL("start-local.ps1", compareRoot)),
      "-Action", "Check",
      "-FrontPort", String(front.port),
      "-BackPort", String(back.port),
      "-ReadyTimeoutSeconds", "2",
    ], { cwd: fileURLToPath(compareRoot), timeout: 15_000, windowsHide: true });
    assert.match(result.stdout, /authenticated endpoints were not called/);
    assert.deepEqual(requests, [
      { method: "GET", url: "/health", service: "back" },
      { method: "GET", url: "/health", service: "back" },
      { method: "GET", url: "/", service: "front" },
    ]);
    assert.ok(requests.every((request) => request.method === "GET"));
    assert.ok(requests.every((request) => !request.url.startsWith("/api/v1")));
  } finally {
    await Promise.all([close(front.server), close(back.server)]);
  }
});

test("workbench defaults to same-origin API, includes cookies and emits no role header", async () => {
  assert.equal(DEFAULT_WORKBENCH_API_BASE, "/api/v1");
  let call;
  const gateway = new HttpWorkbenchGateway({ apiBase: DEFAULT_WORKBENCH_API_BASE, fetchImpl: async (url, init) => { call = { url: String(url), init }; return envelope([]); } });
  await gateway.listProjects();
  assert.equal(call.url, "/api/v1/projects");
  assert.equal(call.init.credentials, "include");
  assert.equal(call.init.headers["X-Compare-Role"], undefined);
});

test("login recovery, expiry, role projection and forbidden controls are wired", async () => {
  const [experience, panel, review, app, topBar, gateway, vite] = await Promise.all([
    readFile(new URL("src/ProjectExperience.tsx", root), "utf8"),
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/TopBar.tsx", root), "utf8"),
    readFile(new URL("src/gateway/httpWorkbenchGateway.ts", root), "utf8"),
    readFile(new URL("vite.config.ts", root), "utf8"),
  ]);
  assert.match(experience, /authClient\.me\(\)/);
  assert.match(experience, /signal-council-session-expired/);
  assert.match(experience, /sessionExpiryCoordinator\.verify\(\)/);
  assert.match(experience, /authStateRef\.current !== "ready"/);
  assert.match(experience, /kind: "not-authenticated"/);
  assert.match(experience, /kind: "session-expired"/);
  assert.match(experience, /kind: "credentials-rejected"/);
  assert.match(experience, /登录后将返回原项目位置/);
  assert.match(experience, /setAuthState\("recovering"\)/);
  assert.match(experience, /key=\{route\.projectId\}/);
  assert.match(experience, /authClient\.logout\(\)/);
  assert.match(experience, /switchPrincipalRole/);
  assert.match(experience, /setLoginUsername\(nextRole\)/);
  assert.match(experience, /已选择.*账号，请输入对应密码完成身份切换/);
  assert.match(experience, /系统设置账号共享项目数据/);
  assert.match(experience, /if \(mockMode\)/);
  assert.match(experience, /account\.displayName/);
  assert.match(panel, /<span className=\{accountRole === "business"/);
  assert.match(panel, /<span className=\{accountRole === "risk"/);
  assert.doesNotMatch(panel, /<span className=\{accountRole === "leadership"/);
  assert.match(panel, /打开 Agent 设置 Dashboard/);
  assert.match(panel, /canParticipate = accountRole === "business" \|\| accountRole === "risk"/);
  assert.match(panel, /disabled=\{accountRole !== "business" \|\| importPending\}/);
  assert.match(review, /canCorrect && facts\.some/);
  assert.match(review, /FormalBusinessCorrection/);
  assert.match(app, /canCorrect=\{account\.role === "business"\}/);
  assert.match(topBar, /account\.role === "leadership" \? <GlobalApprovalActions/);
  assert.match(topBar, /切换业务或风控身份/);
  assert.match(topBar, /onPrincipalRoleChange\(nextRole\)/);
  assert.match(topBar, /System settings/);
  assert.doesNotMatch(gateway, /"X-Compare-Role"/);
  assert.match(vite, /SIGNAL_COUNCIL_BACK_ORIGIN/);
  assert.match(vite, /"\/api\/v1".*target: backOrigin/s);
});

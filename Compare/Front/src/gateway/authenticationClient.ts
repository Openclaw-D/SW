import type { AuthenticatedAccount } from "../contracts/authentication";
import { DEFAULT_WORKBENCH_API_BASE } from "./httpWorkbenchGateway.ts";

type Envelope<T> = { data: T | null; errors?: Array<{ message?: string; code?: string }> };

export class AuthenticationClientError extends Error {
  readonly code: string | null;
  readonly httpStatus: number;

  constructor(message: string, options: { code?: string; httpStatus: number }) {
    super(message);
    this.name = "AuthenticationClientError";
    this.code = options.code ?? null;
    this.httpStatus = options.httpStatus;
  }
}

export type SessionVerification =
  | { status: "active"; account: AuthenticatedAccount }
  | { status: "expired" };

export class AuthenticationClient {
  private readonly apiBase: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: { apiBase?: string; fetchImpl?: typeof fetch } = {}) {
    const queryBase = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("apiBase");
    this.apiBase = (options.apiBase ?? queryBase ?? import.meta.env?.VITE_COMPARE_API_BASE ?? DEFAULT_WORKBENCH_API_BASE).replace(/\/+$/, "");
    this.fetchImpl = options.fetchImpl ?? ((input, init) => window.fetch(input, init));
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(`${this.apiBase}${path}`, { ...init, credentials: "include", headers: { Accept: "application/json", ...init.headers } });
    let payload: Envelope<T> | null = null;
    try {
      payload = await response.json() as Envelope<T>;
    } catch {
      // Preserve a stable client error even when an upstream proxy returns HTML.
    }
    const apiError = payload?.errors?.[0];
    if (!response.ok || payload?.data == null) {
      throw new AuthenticationClientError(apiError?.message ?? "认证服务请求失败。", {
        code: apiError?.code,
        httpStatus: response.status,
      });
    }
    return payload.data;
  }

  login(username: string, password: string) {
    return this.request<AuthenticatedAccount>("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
  }

  me() { return this.request<AuthenticatedAccount>("/auth/me"); }
  logout() { return this.request<{ loggedOut: boolean }>("/auth/logout", { method: "POST" }); }
}

/** Coalesces concurrent 401 broadcasts and verifies whether the current cookie is still valid. */
export class SessionExpiryCoordinator {
  private readonly client: AuthenticationClient;
  private pending: Promise<SessionVerification> | null = null;

  constructor(client: AuthenticationClient) {
    this.client = client;
  }

  verify(): Promise<SessionVerification> {
    if (this.pending) return this.pending;
    const request: Promise<SessionVerification> = this.client.me().then(
      (account): SessionVerification => ({ status: "active", account }),
      (reason: unknown): SessionVerification => {
        if (
          reason instanceof AuthenticationClientError
          && reason.httpStatus === 401
          && (reason.code === "authentication_required" || reason.code === "session_expired")
        ) {
          return { status: "expired" };
        }
        throw reason;
      },
    );
    this.pending = request;
    void request.then(
      () => { if (this.pending === request) this.pending = null; },
      () => { if (this.pending === request) this.pending = null; },
    );
    return request;
  }
}

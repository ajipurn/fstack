/** Same-origin JSON client. The Vite proxy (dev) / reverse proxy (prod) serves /api. */

export const SIGNED_OUT = "app:signed-out";

let csrf = "";
export function setCsrf(token: string) {
  csrf = token;
}

export type Issue = { field: string; message: string };

export class ApiError extends Error {
  readonly status: number;
  readonly issues: Issue[];
  constructor(status: number, message: string, issues: Issue[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.issues = issues;
  }
}

function detailOf(payload: unknown, status: number): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  if (status === 0) return "Can’t reach the API. Is `uv run tasks.py api` running?";
  return `Request failed (${status}).`;
}

export async function api<T>(path: string, init: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const method = init.method ?? "GET";
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      signal: init.signal,
      headers: {
        Accept: "application/json",
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-CSRF-Token": csrf } : {}),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, detailOf(null, 0));
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      // An HTML body with a 200 means the path isn't proxied to the API.
      throw new ApiError(response.status, "The API returned something that isn’t JSON. Check the dev proxy.");
    }
  }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event(SIGNED_OUT));
    const issues = (payload as { issues?: Issue[] } | null)?.issues ?? [];
    throw new ApiError(response.status, detailOf(payload, response.status), issues);
  }
  return payload as T;
}

export const get = <T>(path: string, signal?: AbortSignal) => api<T>(path, { signal });
export const post = <T>(path: string, body?: unknown, signal?: AbortSignal) => api<T>(path, { method: "POST", body: body ?? {}, signal });
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
export const del = <T = void>(path: string) => api<T>(path, { method: "DELETE" });

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

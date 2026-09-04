import { activeAccessToken, clearSession } from "../auth/session";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); this.name = "ApiError"; }
}

function authorizationHeader(): Record<string, string> {
  const token = activeAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function handleUnauthorized(status: number) {
  if (status !== 401 || !activeAccessToken()) return;
  clearSession();
  sessionStorage.setItem("arol.session-notice", "Your session has expired. Please sign in again.");
  window.setTimeout(() => window.location.assign("/login"), 0);
}

export function readableError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has expired. Please sign in again.";
    if (error.status >= 500) return "The service is temporarily unavailable. Please try again shortly.";
    return error.message || fallback;
  }
  if (error instanceof TypeError) return "Network error. Check your connection and try again.";
  return error instanceof Error ? error.message : fallback;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: authorizationHeader() });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    handleUnauthorized(response.status);
    throw new ApiError(body?.detail ?? "Unable to load the requested data.", response.status);
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST", headers: { "Content-Type": "application/json", ...authorizationHeader() }, body: JSON.stringify(body) });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null) as { detail?: string } | null;
    handleUnauthorized(response.status);
    throw new ApiError(errorBody?.detail ?? "Unable to send the question.", response.status);
  }
  return response.json() as Promise<T>;
}

export async function publicPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(errorBody?.detail ?? "Unable to sign in.", response.status);
  }
  return response.json() as Promise<T>;
}

export async function fetchManualPdf(machineId: string, sourceFile: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/machines/${encodeURIComponent(machineId)}/manuals/files/${encodeURIComponent(sourceFile)}`, { headers: authorizationHeader() });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    handleUnauthorized(response.status);
    throw new ApiError(body?.detail ?? "Unable to open the manual.", response.status);
  }
  return response.blob();
}

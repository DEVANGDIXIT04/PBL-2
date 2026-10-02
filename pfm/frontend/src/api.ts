import type { Tokens } from "./types";

const API = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function readTokens(): Tokens | null {
  const access = sessionStorage.getItem("access_token");
  const refresh = sessionStorage.getItem("refresh_token");
  if (!access || !refresh) return null;
  return { access_token: access, refresh_token: refresh, token_type: "bearer" };
}

export function saveTokens(tokens: Tokens | null) {
  if (!tokens) {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("refresh_token");
    return;
  }
  sessionStorage.setItem("access_token", tokens.access_token);
  sessionStorage.setItem("refresh_token", tokens.refresh_token);
}

export function hasSession() {
  return readTokens() !== null;
}

async function refreshTokens(): Promise<boolean> {
  const current = readTokens();
  if (!current) return false;
  const response = await fetch(`${API}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: current.refresh_token }),
  });
  if (!response.ok) {
    saveTokens(null);
    return false;
  }
  saveTokens((await response.json()) as Tokens);
  return true;
}

export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const tokens = readTokens();
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (tokens) headers.set("Authorization", `Bearer ${tokens.access_token}`);
  const response = await fetch(`${API}${path}`, { ...options, headers });
  if (response.status === 401 && retry && tokens && !path.includes("/auth/")) {
    const refreshed = await refreshTokens();
    if (refreshed) return api<T>(path, options, false);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function inr(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

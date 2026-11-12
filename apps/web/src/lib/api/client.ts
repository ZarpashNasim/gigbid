// Thin typed wrapper. Types come from schema.d.ts, generated from FastAPI's OpenAPI (never hand-edit that file).
import type { components } from "./schema";

export type RunInfo = components["schemas"]["RunInfo"];
export type RunDetail = components["schemas"]["RunDetail"];
export type PendingApproval = components["schemas"]["PendingApproval"];
export type ApprovalIn = components["schemas"]["ApprovalIn"];
export type ConvDetail = components["schemas"]["ConvDetail"];

export const getToken = () => (typeof window === "undefined" ? "" : localStorage.getItem("gigbid_token") ?? "");
export const setToken = (t: string) => localStorage.setItem("gigbid_token", t);

export class ApiError extends Error {
  constructor(public status: number, msg: string) { super(msg); }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}`, ...(init.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the GigBid API. Work is queued and will recover when it is back.");
  }
  if (!res.ok) throw new ApiError(res.status, res.status === 401 ? "Invalid token" : `Request failed (${res.status})`);
  return res.json() as Promise<T>;
}

export const api = {
  runs: () => call<RunInfo[]>("/runs"),
  start: (job_id: string) => call<RunInfo>("/runs", { method: "POST", body: JSON.stringify({ job_id }) }),
  detail: (id: string) => call<RunDetail>(`/runs/${encodeURIComponent(id)}`),
  approvals: () => call<PendingApproval[]>("/approvals"),
  resolve: (id: string, body: ApprovalIn) =>
    call<RunInfo>(`/approvals/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify(body) }),
  conversations: () => call<RunInfo[]>("/conversations"),
  startConversation: (thread_id: string) =>
    call<RunInfo>("/conversations", { method: "POST", body: JSON.stringify({ thread_id }) }),
  conversation: (id: string) => call<ConvDetail>(`/conversations/${encodeURIComponent(id)}`),
  health: () => call<{ ok: boolean; marketplace: string }>("/health"),
};

/** Live SSE over fetch (EventSource cannot send an Authorization header). */
export async function streamRun(
  id: string, onEvent: (kind: string, data: any) => void, signal: AbortSignal,
) {
  const res = await fetch(`/api/runs/${encodeURIComponent(id)}/stream`, {
    headers: { Authorization: `Bearer ${getToken()}` }, signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, "stream failed");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, i); buf = buf.slice(i + 2);
      const kind = /^event: (.*)$/m.exec(frame)?.[1] ?? "message";
      const data = /^data: (.*)$/m.exec(frame)?.[1];
      if (data) onEvent(kind, JSON.parse(data));
      if (kind === "end") return;
    }
  }
}

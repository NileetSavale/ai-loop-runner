import type { Session, SessionDetail, AnalyticsSummary, ChatSession, ChatSessionDetail } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  try {
    const { getSupabase } = await import("./supabase");
    const { data } = await getSupabase().auth.getSession();
    const token = data.session?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: await authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...await authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function del(path: string): Promise<void> {
  await fetch(`${BASE}${path}`, { method: "DELETE", headers: await authHeaders() });
}

export const api = {
  sessions: {
    list: () => get<Session[]>("/sessions"),
    get: (id: string) => get<SessionDetail>(`/sessions/${id}`),
    create: (body: unknown) => post<{ id: string }>("/sessions", body),
    stop: (id: string) => post<void>(`/sessions/${id}/stop`, {}),
    delete: (id: string) => del(`/sessions/${id}`),
  },
  analytics: {
    summary: () => get<AnalyticsSummary>("/analytics/summary"),
    costOverTime: () => get<{ date: string; cost_usd: number }[]>("/analytics/cost-over-time"),
    iterationDistribution: () => get<{ iterations: number; count: number }[]>("/analytics/iteration-distribution"),
    successRate: () => get<{ passed: number; failed: number; stopped: number }>("/analytics/success-rate"),
    topTasks: () => get<{ name: string; total_cost_usd: number; total_tokens: number; id: string }[]>("/analytics/top-tasks"),
  },
  testGen: {
    detectStack: (repo_path: string) =>
      get<{ stack: string }>(`/test-gen/detect-stack?repo_path=${encodeURIComponent(repo_path)}`),
    generate: (body: {
      description: string;
      repo_path: string;
      tech_stack?: string;
      context_files?: string[];
      model: string;
    }) => post<{
      test_files: { path: string; content: string }[];
      verify_command: string;
      implementation_spec: string;
    }>("/test-gen/generate", body),
    applyAndStart: (body: {
      repo_path: string;
      test_files: { path: string; content: string }[];
      verify_command: string;
      implementation_spec: string;
      session_name: string;
      model: string;
      max_iterations: number;
    }) => post<{ session_id: string }>("/test-gen/apply-and-start", body),
  },
  keys: {
    list: () => get<{ id: string; provider: string; label: string; created_at: string }[]>("/keys"),
    models: () => get<Record<string, { id: string; name: string }[]>>("/keys/models"),
    add: (body: { provider: string; api_key: string; label?: string }) => post<{ id: string; provider: string }>("/keys", body),
    delete: (id: string) => del(`/keys/${id}`),
  },
  chat: {
    list: () => get<ChatSession[]>("/chat-sessions"),
    get: (id: string) => get<ChatSessionDetail>(`/chat-sessions/${id}`),
    create: (body: unknown) => post<ChatSession>("/chat-sessions", body),
    send: (id: string, body: { prompt: string; files_context?: string[] }) =>
      post<{ message_id: string; loop_session_id: string }>(`/chat-sessions/${id}/messages`, body),
  },
};

export const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

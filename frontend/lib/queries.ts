import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

// ── query keys ────────────────────────────────────────────────────────────────
export const keys = {
  sessions: ["sessions"] as const,
  session: (id: string) => ["sessions", id] as const,
  chatSessions: ["chat-sessions"] as const,
  chatSession: (id: string) => ["chat-sessions", id] as const,
  analytics: (kind: string) => ["analytics", kind] as const,
};

// ── sessions ─────────────────────────────────────────────────────────────────
export function useSessions() {
  return useQuery({ queryKey: keys.sessions, queryFn: api.sessions.list });
}

export function useSession(id: string) {
  return useQuery({ queryKey: keys.session(id), queryFn: () => api.sessions.get(id) });
}

export function useStopSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.sessions.stop(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: keys.session(id) });
      qc.invalidateQueries({ queryKey: keys.sessions });
    },
  });
}

// ── chat ─────────────────────────────────────────────────────────────────────
export function useChatSessions() {
  return useQuery({ queryKey: keys.chatSessions, queryFn: api.chat.list });
}

export function useChatSession(id: string) {
  return useQuery({ queryKey: keys.chatSession(id), queryFn: () => api.chat.get(id) });
}

export function useSendMessage(chatSessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { prompt: string; files_context?: string[] }) =>
      api.chat.send(chatSessionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.chatSession(chatSessionId) });
    },
  });
}

// ── analytics ─────────────────────────────────────────────────────────────────
export function useAnalyticsSummary() {
  return useQuery({ queryKey: keys.analytics("summary"), queryFn: api.analytics.summary, staleTime: 60_000 });
}

export function useCostOverTime() {
  return useQuery({ queryKey: keys.analytics("cost"), queryFn: api.analytics.costOverTime, staleTime: 60_000 });
}

export function useIterationDistribution() {
  return useQuery({ queryKey: keys.analytics("distribution"), queryFn: api.analytics.iterationDistribution, staleTime: 60_000 });
}

export function useSuccessRate() {
  return useQuery({ queryKey: keys.analytics("success"), queryFn: api.analytics.successRate, staleTime: 60_000 });
}

export function useTopTasks() {
  return useQuery({ queryKey: keys.analytics("top"), queryFn: api.analytics.topTasks, staleTime: 60_000 });
}

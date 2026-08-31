import { create } from "zustand";
import type { ChatMessage } from "./types";

interface LiveState {
  token: string;       // accumulated streaming tokens for the current iteration
  iteration: number;   // which iteration is running
  verifyOutput: string;
}

interface ChatStore {
  // messages keyed by chat session id
  messages: Record<string, ChatMessage[]>;
  live: Record<string, LiveState>;  // keyed by message id

  setMessages: (chatId: string, msgs: ChatMessage[]) => void;
  addMessage: (chatId: string, msg: ChatMessage) => void;
  updateMessage: (chatId: string, msgId: string, patch: Partial<ChatMessage>) => void;

  appendToken: (msgId: string, token: string) => void;
  setLiveIteration: (msgId: string, iteration: number) => void;
  setVerifyOutput: (msgId: string, output: string) => void;
  clearLive: (msgId: string) => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: {},
  live: {},

  setMessages: (chatId, msgs) =>
    set((s) => ({ messages: { ...s.messages, [chatId]: msgs } })),

  addMessage: (chatId, msg) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [chatId]: [...(s.messages[chatId] ?? []), msg],
      },
    })),

  updateMessage: (chatId, msgId, patch) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [chatId]: (s.messages[chatId] ?? []).map((m) =>
          m.id === msgId ? { ...m, ...patch } : m
        ),
      },
    })),

  appendToken: (msgId, token) =>
    set((s) => ({
      live: {
        ...s.live,
        [msgId]: {
          ...s.live[msgId],
          token: (s.live[msgId]?.token ?? "") + token,
          iteration: s.live[msgId]?.iteration ?? 1,
          verifyOutput: s.live[msgId]?.verifyOutput ?? "",
        },
      },
    })),

  setLiveIteration: (msgId, iteration) =>
    set((s) => ({
      live: { ...s.live, [msgId]: { ...s.live[msgId], iteration, token: "", verifyOutput: "" } },
    })),

  setVerifyOutput: (msgId, output) =>
    set((s) => ({
      live: { ...s.live, [msgId]: { ...s.live[msgId], verifyOutput: output } },
    })),

  clearLive: (msgId) =>
    set((s) => {
      const next = { ...s.live };
      delete next[msgId];
      return { live: next };
    }),
}));

"use client";
import { useEffect, useRef, useState } from "react";
import { api, WS_BASE } from "@/lib/api";
import { useChatStore } from "@/lib/store";
import { useSendMessage } from "@/lib/queries";
import type { ChatMessage, WsMessage } from "@/lib/types";

export function ChatInterface({
  chatSessionId,
  initialMessages,
}: {
  chatSessionId: string;
  initialMessages: ChatMessage[];
}) {
  const { messages, live, setMessages, addMessage, updateMessage,
          appendToken, setLiveIteration, setVerifyOutput, clearLive } = useChatStore();
  const send = useSendMessage(chatSessionId);
  const [input, setInput] = useState("");
  const [filesContext, setFilesContext] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // seed store from server-fetched data
  useEffect(() => {
    setMessages(chatSessionId, initialMessages);
  }, [chatSessionId]); // eslint-disable-line

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages[chatSessionId]?.length]);

  // single WebSocket for the whole chat session
  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/chat/${chatSessionId}`);

    ws.onmessage = (e) => {
      const msg: WsMessage = JSON.parse(e.data);
      const msgId = msg.message_id;
      if (!msgId) return;

      switch (msg.event) {
        case "iteration_start":
          setLiveIteration(msgId, msg.data.iteration as number);
          break;
        case "agent_token":
          appendToken(msgId, msg.data.token as string);
          break;
        case "verify_output":
          setVerifyOutput(msgId, msg.data.output as string);
          break;
        case "session_complete": {
          const d = msg.data as { status: string; commit?: string };
          updateMessage(chatSessionId, msgId, {
            status: d.status as ChatMessage["status"],
            git_commit_hash: d.commit ?? null,
          });
          clearLive(msgId);
          break;
        }
      }
    };

    return () => ws.close();
  }, [chatSessionId]); // eslint-disable-line

  async function handleSend() {
    if (!input.trim() || send.isPending) return;
    const prompt = input.trim();
    setInput("");

    const tempId = `temp-${Date.now()}`;
    addMessage(chatSessionId, {
      id: tempId, chat_session_id: chatSessionId, prompt,
      status: "running", loop_session_id: null,
      total_iterations: 0, total_cost_usd: 0, git_commit_hash: null,
      created_at: new Date().toISOString(), completed_at: null,
    });

    try {
      const { message_id, loop_session_id } = await api.chat.send(chatSessionId, {
        prompt, files_context: filesContext.filter(Boolean),
      });
      updateMessage(chatSessionId, tempId, { id: message_id, loop_session_id } as Partial<ChatMessage>);
    } catch (err) {
      updateMessage(chatSessionId, tempId, { status: "failed" });
    }
  }

  const sessionMessages = messages[chatSessionId] ?? [];

  return (
    <div className="flex flex-col h-[calc(100vh-140px)]">
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {sessionMessages.length === 0 && (
          <p className="text-gray-400 text-sm text-center mt-12">
            Describe a feature. The loop will write code and commit it on pass.
          </p>
        )}
        {sessionMessages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} live={live[msg.id]} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t pt-4 space-y-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend(); }}
          placeholder="Describe the next feature... (⌘+Enter to send)"
          rows={3}
          className="w-full border rounded px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <div className="flex gap-2 items-center">
          <FilesInput value={filesContext} onChange={setFilesContext} />
          <button onClick={handleSend} disabled={send.isPending || !input.trim()}
            className="ml-auto bg-indigo-600 text-white px-4 py-2 rounded text-sm hover:bg-indigo-700 disabled:opacity-50">
            {send.isPending ? "Starting..." : "Run Loop"}
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg, live }: { msg: ChatMessage; live?: { token: string; iteration: number; verifyOutput: string } }) {
  const isRunning = msg.status === "running";

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-2 max-w-[75%] text-sm whitespace-pre-wrap">
          {msg.prompt}
        </div>
      </div>

      <div className={`flex justify-start`}>
        <div className={`rounded-2xl rounded-tl-sm px-4 py-3 max-w-[85%] text-sm border ${
          isRunning ? "bg-white border-gray-200" :
          msg.status === "passed" ? "bg-green-50 border-green-200" :
          "bg-red-50 border-red-200"
        }`}>
          {isRunning && live ? (
            <div className="space-y-2">
              <p className="text-blue-600 font-medium animate-pulse text-xs">
                Iteration {live.iteration ?? 1} — Claude is writing...
              </p>
              {live.token && (
                <pre className="text-xs text-gray-600 whitespace-pre-wrap max-h-48 overflow-y-auto font-mono bg-gray-50 rounded p-2">
                  {live.token}
                </pre>
              )}
              {live.verifyOutput && (
                <details open>
                  <summary className="text-xs text-gray-400 cursor-pointer">Verify output</summary>
                  <pre className="text-xs text-gray-600 whitespace-pre-wrap max-h-32 overflow-y-auto mt-1">{live.verifyOutput}</pre>
                </details>
              )}
            </div>
          ) : isRunning ? (
            <p className="text-gray-400 animate-pulse text-xs">Starting...</p>
          ) : (
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <span className={`font-medium ${msg.status === "passed" ? "text-green-700" : "text-red-600"}`}>
                  {msg.status === "passed" ? "Done" : "Failed"}
                </span>
                <span className="text-xs text-gray-400">
                  {msg.total_iterations} iter · ${msg.total_cost_usd.toFixed(4)}
                </span>
                {msg.git_commit_hash && (
                  <span className="text-xs font-mono text-green-600">{msg.git_commit_hash.slice(0, 7)}</span>
                )}
              </div>
              {msg.loop_session_id && (
                <a href={`/sessions/${msg.loop_session_id}`} target="_blank"
                  className="text-xs text-indigo-500 hover:underline">
                  View full loop →
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FilesInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const count = value.filter(Boolean).length;
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen((p) => !p)}
        className="text-xs text-gray-500 hover:text-gray-800 border rounded px-2 py-1">
        Files context {count > 0 ? `(${count})` : ""}
      </button>
      {open && (
        <div className="absolute bottom-8 left-0 bg-white border rounded shadow-lg p-3 w-72 space-y-2 z-10">
          <p className="text-xs text-gray-500 font-medium">File paths to include as context</p>
          {value.map((f, i) => (
            <div key={i} className="flex gap-1">
              <input value={f} onChange={(e) => onChange(value.map((x, j) => j === i ? e.target.value : x))}
                className="flex-1 border rounded px-2 py-1 text-xs font-mono" placeholder="src/main.py" />
              <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))}
                className="text-gray-400 hover:text-red-500">×</button>
            </div>
          ))}
          <button type="button" onClick={() => onChange([...value, ""])}
            className="text-xs text-indigo-600 hover:underline">+ Add file</button>
        </div>
      )}
    </div>
  );
}

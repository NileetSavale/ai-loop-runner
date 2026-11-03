"use client";
import { useEffect, useRef, useState } from "react";
import type { Iteration, WsMessage } from "@/lib/types";
import { authedSocket } from "@/lib/api";
import { StatusBadge } from "./StatusBadge";

interface LiveIteration extends Partial<Iteration> {
  iteration_number: number;
  status: "running" | "passed" | "failed";
  verify_output?: string;
  agent_output?: string;
}

export function LiveLoop({ sessionId, initialIterations }: { sessionId: string; initialIterations: Iteration[] }) {
  const [iterations, setIterations] = useState<LiveIteration[]>(initialIterations);
  const [done, setDone] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = authedSocket(`/ws/sessions/${sessionId}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const msg: WsMessage = JSON.parse(e.data);

      if (msg.event === "iteration_start") {
        const n = msg.data.iteration as number;
        setIterations((prev) => {
          if (prev.find((i) => i.iteration_number === n)) return prev;
          return [...prev, { iteration_number: n, status: "running" }];
        });
      }

      if (msg.event === "verify_output") {
        setIterations((prev) =>
          prev.map((i) =>
            i.status === "running"
              ? { ...i, verify_output: msg.data.output as string }
              : i
          )
        );
      }

      if (msg.event === "iteration_complete" || msg.event === "session_complete") {
        const d = msg.data as Partial<LiveIteration>;
        setIterations((prev) =>
          prev.map((i) =>
            i.iteration_number === d.iteration_number ? { ...i, ...d } : i
          )
        );
        if (msg.event === "session_complete") setDone(true);
      }
    };

    return () => ws.close();
  }, [sessionId]);

  return (
    <div className="space-y-4">
      {iterations.map((iter) => (
        <IterationRow key={iter.iteration_number} iter={iter} />
      ))}
      {done && <p className="text-sm text-gray-500 text-center">Session complete.</p>}
    </div>
  );
}

function IterationRow({ iter }: { iter: LiveIteration }) {
  const [showAgent, setShowAgent] = useState(false);
  const [showVerify, setShowVerify] = useState(true);

  return (
    <div className="border rounded-lg p-4 space-y-2">
      <div className="flex items-center gap-3">
        <span className="font-mono text-sm text-gray-500">#{iter.iteration_number}</span>
        <StatusBadge status={iter.status} />
        {iter.cost_usd != null && (
          <span className="text-xs text-gray-400">${iter.cost_usd.toFixed(4)} · {iter.input_tokens}+{iter.output_tokens} tok · {iter.duration_seconds?.toFixed(1)}s</span>
        )}
        {iter.git_commit_hash && (
          <span className="text-xs font-mono text-green-600">{iter.git_commit_hash.slice(0, 7)}</span>
        )}
      </div>

      {iter.verify_output && (
        <details open={showVerify} onToggle={(e) => setShowVerify((e.target as HTMLDetailsElement).open)}>
          <summary className={`text-xs cursor-pointer font-medium ${iter.status === "passed" ? "text-green-600" : "text-red-500"}`}>
            Verify output
          </summary>
          <pre className="mt-1 p-2 bg-gray-50 rounded text-xs overflow-x-auto whitespace-pre-wrap">{iter.verify_output}</pre>
        </details>
      )}

      {iter.agent_output && (
        <details open={showAgent} onToggle={(e) => setShowAgent((e.target as HTMLDetailsElement).open)}>
          <summary className="text-xs cursor-pointer text-gray-500 font-medium">Agent output</summary>
          <pre className="mt-1 p-2 bg-gray-50 rounded text-xs overflow-x-auto whitespace-pre-wrap">{iter.agent_output}</pre>
        </details>
      )}

      {iter.status === "running" && (
        <p className="text-xs text-blue-500 animate-pulse">Running...</p>
      )}
    </div>
  );
}

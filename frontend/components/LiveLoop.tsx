"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { AgentEvent, AgentEventKind, CascadeStep, Iteration, WsMessage } from "@/lib/types";
import { api, authedSocket } from "@/lib/api";
import { AgentView } from "./AgentView";
import { CascadeTrack, shortName } from "./CascadeTrack";
import { StatusBadge } from "./StatusBadge";

const AGENT_EVENTS: string[] = ["focus", "tool", "file_changed"];

interface LiveIteration extends Partial<Iteration> {
  iteration_number: number;
  status: "running" | "passed" | "failed";
  stage?: 1 | 2; // in a cascade: the cheap model's loop or the main model's; both number their attempts from 1
  verify_output?: string;
  agent_output?: string;
}

export function LiveLoop({ sessionId, initialIterations }: { sessionId: string; initialIterations: Iteration[] }) {
  const [iterations, setIterations] = useState<LiveIteration[]>(initialIterations);
  const [done, setDone] = useState(false);
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [cascade, setCascade] = useState<CascadeStep[]>([]);
  const [finalStatus, setFinalStatus] = useState<string | null>(null);
  const [setup, setSetup] = useState<string | null>(null);
  const stage = useRef<1 | 2>(1);
  const wsRef = useRef<WebSocket | null>(null);
  const router = useRouter();

  function addAgentEvents(incoming: AgentEvent[]) {
    // Saved and live events can overlap while the page loads, so merge them by id
    setAgentEvents((prev) => {
      const byId = new Map(prev.map((e) => [e.id, e]));
      incoming.forEach((e) => byId.set(e.id, e));
      return Array.from(byId.values()).sort((a, b) => a.id - b.id);
    });
  }

  function addCascadeSteps(incoming: CascadeStep[]) {
    if (!incoming.length) return;
    setCascade((prev) => {
      const byId = new Map(prev.map((s) => [s.id, s]));
      incoming.forEach((s) => byId.set(s.id, s));
      return Array.from(byId.values()).sort((a, b) => a.id - b.id);
    });
    const escalated = incoming.find((s) => s.step === "escalated");
    if (escalated && stage.current === 1) {
      stage.current = 2;
      // Saved iterations come in the order they ran, so the cheap model's are the first ones
      const k = escalated.cheap_iterations ?? 0;
      setIterations((prev) => prev.map((it, i) => (it.stage ? it : { ...it, stage: i < k ? 1 : 2 })));
    }
  }

  useEffect(() => {
    const ws = authedSocket(`/ws/sessions/${sessionId}`);
    wsRef.current = ws;
    api.sessions.events(sessionId).then((events) => {
      addAgentEvents(events);
      addCascadeSteps((events as unknown as CascadeStep[]).filter((e) => e.kind === "cascade"));
    }).catch(() => {});

    ws.onmessage = (e) => {
      const msg: WsMessage = JSON.parse(e.data);

      if (AGENT_EVENTS.includes(msg.event)) {
        const event = { ...msg.data, kind: msg.event as AgentEventKind } as unknown as AgentEvent;
        addAgentEvents([event]);
      }

      if (msg.event === "setup") setSetup(msg.data.text as string);

      if (msg.event === "cascade") {
        addCascadeSteps([{ ...msg.data, kind: "cascade" } as unknown as CascadeStep]);
      }

      const current = (i: LiveIteration) => (i.stage ?? 1) === stage.current;

      if (msg.event === "iteration_start") {
        const n = msg.data.iteration as number;
        setIterations((prev) => {
          if (prev.find((i) => i.iteration_number === n && current(i))) return prev;
          return [...prev, { iteration_number: n, status: "running", stage: stage.current }];
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
            i.iteration_number === d.iteration_number && current(i) ? { ...i, ...d } : i
          )
        );
        if (msg.event === "session_complete") {
          setDone(true);
          setFinalStatus(msg.data.status as string);
          router.refresh(); // the header and totals are rendered on the server
        }
      }
    };

    return () => ws.close();
  }, [sessionId, router]);

  return (
    <div className="space-y-4">
      {setup && iterations.length === 0 && !done && <p className="text-sm text-blue-500 animate-pulse">{setup}...</p>}
      {cascade.length > 0 && <CascadeTrack steps={cascade} finalStatus={finalStatus} />}
      <AgentView sessionId={sessionId} events={agentEvents} />
      {iterations.map((iter) => (
        <IterationRow key={`${iter.stage ?? 1}-${iter.iteration_number}`} iter={iter}
          model={cascade.length ? modelFor(cascade, iter.stage ?? 1) : null} />
      ))}
      {done && <p className="text-sm text-gray-500 text-center">Session complete.</p>}
    </div>
  );
}

function modelFor(steps: CascadeStep[], stage: 1 | 2): string | null {
  const step = steps.find((s) => s.step === (stage === 1 ? "cheap" : "escalated"));
  return step ? shortName(step.model) : null;
}

function IterationRow({ iter, model }: { iter: LiveIteration; model: string | null }) {
  const [showAgent, setShowAgent] = useState(false);
  const [showVerify, setShowVerify] = useState(true);

  return (
    <div className="border rounded-lg p-4 space-y-2">
      <div className="flex items-center gap-3">
        {model && <span className="text-xs font-medium text-gray-700">{model}</span>}
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

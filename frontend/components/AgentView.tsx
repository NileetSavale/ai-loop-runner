"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AgentEvent, RepoMap } from "@/lib/types";
import { type NodeStatus, RepoMapView } from "./RepoMapView";

function statusesFrom(events: AgentEvent[]): Record<string, NodeStatus> {
  const statuses: Record<string, NodeStatus> = {};
  const rank: Record<NodeStatus, number> = { focus: 0, read: 1, error: 2, changed: 3 };
  const mark = (path: string | undefined, status: NodeStatus) => {
    if (path && (!statuses[path] || rank[status] >= rank[statuses[path]])) statuses[path] = status;
  };
  events.forEach((e) => {
    if (e.kind === "focus") e.files?.forEach((f) => mark(f.path, "focus"));
    if (e.kind === "tool" && e.tool === "read_file") mark(e.target, e.error ? "error" : "read");
    if (e.kind === "tool" && e.error && (e.tool === "write_file" || e.tool === "edit_file")) mark(e.target, "error");
    if (e.kind === "file_changed") mark(e.path, "changed");
  });
  return statuses;
}

function describeTool(e: AgentEvent): string {
  switch (e.tool) {
    case "list_files": return "Listed the repo's files";
    case "read_file": return `Read ${e.target}`;
    case "search_code": return `Searched for "${e.target}"`;
    case "edit_file": return `Edited ${e.target}`;
    case "write_file": return `Wrote ${e.target}`;
    case "run_tests": return e.passed ? "Ran the tests: passed" : "Ran the tests: failed";
    default: return `${e.tool} ${e.target ?? ""}`;
  }
}

export function AgentView({ sessionId, events }: { sessionId: string; events: AgentEvent[] }) {
  const [map, setMap] = useState<RepoMap | null>(null);
  const [mapError, setMapError] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);

  const changes = events.filter((e) => e.kind === "file_changed");
  const steps = events.filter((e) => e.kind === "tool");
  const focus = events.find((e) => e.kind === "focus");
  const statuses = useMemo(() => statusesFrom(events), [events]);

  // A file the agent just created isn't on the map yet, so redraw when one appears
  const unknownFile = !!map && changes.some((c) => !map.nodes.some((n) => n.path === c.path));
  useEffect(() => {
    api.sessions.map(sessionId).then(setMap).catch(() => setMapError(true));
  }, [sessionId, unknownFile]);

  if (events.length === 0 && !map) return null;

  // Keep the most recent change in view, or where the agent was pointed before it has changed anything
  const scrollTo = changes[changes.length - 1]?.path ?? focus?.files?.[0]?.path;

  const shownSteps = picked ? steps.filter((s) => s.target === picked) : steps;
  const shownChanges = picked ? changes.filter((c) => c.path === picked) : changes;

  return (
    <section aria-label="What the agent is doing" className="space-y-3">
      {focus?.files && focus.files.length > 0 && (
        <div className="border border-amber-300 bg-amber-50 rounded-lg p-3">
          <h2 className="text-sm font-semibold text-gray-900">Where the agent was pointed</h2>
          <ul className="mt-1 space-y-0.5 text-sm text-gray-700">
            {focus.files.map((f) => (
              <li key={f.path}><span className="font-mono text-xs">{f.path}</span> <span className="text-gray-500">({f.reason})</span></li>
            ))}
          </ul>
        </div>
      )}

      {map && <RepoMapView map={map} statuses={statuses} selected={picked ? [picked] : []}
        scrollTo={scrollTo} onNodeClick={(path) => setPicked((p) => (p === path ? null : path))} />}
      {mapError && <p className="text-sm text-gray-500">The repo map isn&apos;t available because the repo can&apos;t be read.</p>}

      {picked && (
        <p className="text-sm text-gray-600">
          Showing only <span className="font-mono text-xs">{picked}</span>.{" "}
          <button className="text-indigo-600 hover:underline" onClick={() => setPicked(null)}>Show everything</button>
        </p>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="border rounded-lg p-3 min-w-0">
          <h2 className="text-sm font-semibold text-gray-900 mb-2">Activity</h2>
          {shownSteps.length === 0 ? (
            <p className="text-sm text-gray-500">{picked ? "Nothing recorded for this file." : "No actions yet."}</p>
          ) : (
            <ol className="space-y-1 text-sm max-h-72 overflow-auto">
              {shownSteps.map((s) => (
                <li key={s.id} className={s.error || s.passed === false ? "text-red-700" : "text-gray-700"}>
                  {describeTool(s)}
                  {s.error && <span className="block text-xs text-red-600">Refused: {s.error}</span>}
                </li>
              ))}
            </ol>
          )}
        </div>

        <div className="border rounded-lg p-3 min-w-0">
          <h2 className="text-sm font-semibold text-gray-900 mb-2">Changes</h2>
          {shownChanges.length === 0 ? (
            <p className="text-sm text-gray-500">{picked ? "This file wasn't changed." : "No changes yet."}</p>
          ) : (
            <ul className="space-y-2 max-h-72 overflow-auto">
              {shownChanges.map((c) => (
                <li key={c.id}>
                  <details open={shownChanges.length === 1}>
                    <summary className="text-sm cursor-pointer">
                      <span className="font-mono text-xs">{c.path}</span>{" "}
                      {c.is_new && <span className="text-xs text-gray-500">new </span>}
                      <span className="text-xs text-green-700">+{c.added}</span>{" "}
                      <span className="text-xs text-red-700">-{c.removed}</span>
                    </summary>
                    <pre className="mt-1 p-2 bg-gray-50 rounded text-xs overflow-x-auto">
                      {c.diff?.split("\n").map((line, i) => (
                        <div key={i} className={line.startsWith("+") ? "text-green-700" : line.startsWith("-") ? "text-red-700" : "text-gray-600"}>{line || " "}</div>
                      ))}
                      {c.diff_cut_off && <div className="text-gray-500">(diff shortened)</div>}
                    </pre>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

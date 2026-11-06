"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { RepoMap } from "@/lib/types";

export type NodeStatus = "focus" | "read" | "changed" | "error";

const FILE_W = 210;
const FILE_H = 28;
const FILE_GAP = 4;
const GROUP_PAD = 10;
const GROUP_TITLE = 24;
const COLUMN_GAP = 70;
const GROUP_GAP = 18;

const STATUS: Record<NodeStatus, { box: string; mark: string; label: string }> = {
  focus: { box: "fill-amber-50 stroke-amber-500", mark: "◎", label: "Likely issue" },
  read: { box: "fill-blue-50 stroke-blue-500", mark: "R", label: "Read by agent" },
  changed: { box: "fill-green-50 stroke-green-600", mark: "✎", label: "Changed" },
  error: { box: "fill-red-50 stroke-red-500", mark: "!", label: "Action refused" },
};

function layOut(map: RepoMap) {
  const columnsByLayer = new Map<number, string[]>();
  const groups = Array.from(new Set(map.nodes.map((n) => n.group))).sort();
  groups.forEach((g) => {
    const layer = map.layers[g] ?? 0;
    columnsByLayer.set(layer, [...(columnsByLayer.get(layer) ?? []), g]);
  });

  const positions = new Map<string, { x: number; y: number }>();
  const boxes: { name: string; x: number; y: number; h: number }[] = [];
  const width = GROUP_PAD * 2 + FILE_W;
  let maxY = 0;
  Array.from(columnsByLayer.keys())
    .sort((a, b) => a - b)
    .forEach((layer, column) => {
      const x = column * (width + COLUMN_GAP);
      let y = 0;
      columnsByLayer.get(layer)!.forEach((group) => {
        const files = map.nodes.filter((n) => n.group === group);
        const h = GROUP_TITLE + files.length * (FILE_H + FILE_GAP) + GROUP_PAD;
        boxes.push({ name: group, x, y, h });
        files.forEach((f, i) =>
          positions.set(f.path, { x: x + GROUP_PAD, y: y + GROUP_TITLE + i * (FILE_H + FILE_GAP) })
        );
        y += h + GROUP_GAP;
      });
      maxY = Math.max(maxY, y);
    });
  const columns = columnsByLayer.size;
  return { positions, boxes, boxWidth: width, width: Math.max(columns * (width + COLUMN_GAP) - COLUMN_GAP, width), height: maxY };
}

function shorten(name: string, max = 26) {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

export function RepoMapView({
  map,
  statuses = {},
  selected = [],
  onNodeClick,
  scrollTo,
}: {
  map: RepoMap;
  statuses?: Record<string, NodeStatus>;
  selected?: string[];
  onNodeClick?: (path: string) => void;
  scrollTo?: string;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const layout = useMemo(() => layOut(map), [map]);
  const scroller = useRef<HTMLDivElement>(null);

  const target = scrollTo ? layout.positions.get(scrollTo) : undefined;
  useEffect(() => {
    if (target && scroller.current) {
      scroller.current.scrollTo({
        left: target.x - scroller.current.clientWidth / 2 + FILE_W / 2,
        top: target.y - scroller.current.clientHeight / 2,
        behavior: "smooth",
      });
    }
  }, [target]);

  // Drawing every import makes an unreadable tangle. Show the links between files that matter right now.
  const chosen = new Set([...selected, ...(hovered ? [hovered] : [])]);
  const marked = new Set(Object.keys(statuses));

  if (map.nodes.length === 0) {
    return <p className="text-sm text-gray-500">No code files found in this repo.</p>;
  }

  return (
    <div className="border rounded-lg bg-white">
      <div className="flex flex-wrap gap-x-4 gap-y-1 px-3 py-2 border-b text-xs text-gray-600">
        {(Object.keys(STATUS) as NodeStatus[]).map((s) => (
          <span key={s} className="flex items-center gap-1">
            <span className="font-bold w-3 text-center" aria-hidden>{STATUS[s].mark}</span>
            {STATUS[s].label}
          </span>
        ))}
        <span className="text-gray-400">Hover or select a file to see what it imports and what imports it</span>
        {map.truncated && <span className="text-amber-700">Large repo: showing the first 400 files</span>}
      </div>
      <div ref={scroller} className="overflow-auto max-h-[32rem] p-3">
        <svg
          width={layout.width}
          height={layout.height}
          role="group"
          aria-label={`Repo map with ${map.nodes.length} files`}
        >
          <defs>
            <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0 0 L8 4 L0 8 Z" className="fill-gray-500" />
            </marker>
          </defs>

          {layout.boxes.map((b) => (
            <g key={b.name}>
              <rect x={b.x} y={b.y} width={layout.boxWidth} height={b.h} rx={8} className="fill-gray-50 stroke-gray-200" />
              <text x={b.x + GROUP_PAD} y={b.y + 16} className="fill-gray-500 text-[11px] font-medium">
                {shorten(b.name === "." ? "(repo root)" : b.name, 32)}
              </text>
            </g>
          ))}

          {map.edges.map((e) => {
            const from = layout.positions.get(e.from);
            const to = layout.positions.get(e.to);
            if (!from || !to) return null;
            if (!chosen.has(e.from) && !chosen.has(e.to) && !(marked.has(e.from) && marked.has(e.to))) return null;
            const x1 = from.x + FILE_W;
            const y1 = from.y + FILE_H / 2;
            const x2 = to.x;
            const y2 = to.y + FILE_H / 2;
            const bend = Math.max(Math.abs(x2 - x1) / 2, 30);
            return (
              <path
                key={`${e.from}>${e.to}`}
                d={`M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - bend} ${y2} ${x2} ${y2}`}
                fill="none"
                markerEnd="url(#arrow)"
                className="stroke-gray-500"
                strokeWidth={1.5}
              />
            );
          })}

          {map.nodes.map((n) => {
            const p = layout.positions.get(n.path)!;
            const status = statuses[n.path];
            const isSelected = selected.includes(n.path);
            const name = n.path.split("/").pop()!;
            const summary = [n.path, status && STATUS[status].label, isSelected && "selected"].filter(Boolean).join(", ");
            return (
              <g
                key={n.path}
                role={onNodeClick ? "button" : undefined}
                tabIndex={onNodeClick ? 0 : undefined}
                aria-label={summary}
                aria-pressed={onNodeClick ? isSelected : undefined}
                className={onNodeClick ? "cursor-pointer focus:outline-none [&:focus_rect]:stroke-indigo-600" : undefined}
                onClick={() => onNodeClick?.(n.path)}
                onKeyDown={(e) => {
                  if (onNodeClick && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onNodeClick(n.path);
                  }
                }}
                onMouseEnter={() => setHovered(n.path)}
                onMouseLeave={() => setHovered(null)}
              >
                <title>{[n.path, ...n.symbols.slice(0, 12).map((s) => `${s.name} (line ${s.line})`)].join("\n")}</title>
                <rect
                  x={p.x}
                  y={p.y}
                  width={FILE_W}
                  height={FILE_H}
                  rx={5}
                  strokeWidth={status || isSelected ? 2 : 1}
                  className={isSelected ? "fill-indigo-50 stroke-indigo-600" : status ? STATUS[status].box : "fill-white stroke-gray-300"}
                />
                <text x={p.x + 8} y={p.y + 18} className={`text-xs ${n.is_test ? "fill-gray-500 italic" : "fill-gray-800"}`}>
                  {shorten(name)}
                </text>
                {(status || isSelected) && (
                  <text x={p.x + FILE_W - 8} y={p.y + 18} textAnchor="end" className="text-xs font-bold fill-gray-800" aria-hidden>
                    {isSelected ? "✓" : STATUS[status!].mark}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

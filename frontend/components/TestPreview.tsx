"use client";
import { useState } from "react";

interface TestFile {
  path: string;
  content: string;
}

export function TestPreview({
  files,
  onChange,
}: {
  files: TestFile[];
  onChange: (files: TestFile[]) => void;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set([0]));

  function toggle(i: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }

  function updateContent(i: number, content: string) {
    onChange(files.map((f, j) => (j === i ? { ...f, content } : f)));
  }

  function lineCount(content: string) {
    return content.split("\n").length;
  }

  return (
    <div className="space-y-3">
      {files.map((file, i) => (
        <div key={i} className="border rounded-lg overflow-hidden">
          {/* header */}
          <div className="flex items-center justify-between bg-gray-50 px-4 py-2 border-b">
            <button onClick={() => toggle(i)} className="flex items-center gap-2 text-sm font-mono text-gray-700 hover:text-gray-900">
              <span className={`text-gray-400 transition-transform ${expanded.has(i) ? "rotate-90" : ""}`}>▶</span>
              {file.path}
              <span className="text-xs text-gray-400 font-sans">{lineCount(file.content)} lines</span>
            </button>
            <div className="flex gap-2">
              <button
                onClick={() => { setEditing(editing === i ? null : i); if (!expanded.has(i)) toggle(i); }}
                className="text-xs text-indigo-600 hover:underline"
              >
                {editing === i ? "Done" : "Edit"}
              </button>
            </div>
          </div>

          {/* content */}
          {expanded.has(i) && (
            editing === i ? (
              <textarea
                value={file.content}
                onChange={(e) => updateContent(i, e.target.value)}
                rows={Math.min(lineCount(file.content) + 2, 40)}
                className="w-full p-4 text-xs font-mono bg-white focus:outline-none resize-y"
                spellCheck={false}
              />
            ) : (
              <pre className="p-4 text-xs font-mono bg-white overflow-x-auto whitespace-pre max-h-96 overflow-y-auto">
                <code>{file.content}</code>
              </pre>
            )
          )}
        </div>
      ))}
    </div>
  );
}

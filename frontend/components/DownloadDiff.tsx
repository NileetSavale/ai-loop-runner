"use client";
import { useState } from "react";
import { api } from "@/lib/api";

// The session's changes as a patch: `git apply` it in your own clone
export function DownloadDiff({ sessionId }: { sessionId: string }) {
  const [error, setError] = useState("");

  async function download() {
    setError("");
    try {
      const text = await api.sessions.diff(sessionId);
      if (!text.trim()) return setError("The session didn't change anything.");
      const url = URL.createObjectURL(new Blob([text], { type: "text/x-diff" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: `loop-runner-${sessionId.slice(0, 8)}.diff` });
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" onClick={download} className="text-sm text-indigo-600 hover:underline">Download changes (.diff)</button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </span>
  );
}

"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { RepoMapView } from "@/components/RepoMapView";
import type { RepoMap } from "@/lib/types";

export default function NewSession() {
  const router = useRouter();
  const [files, setFiles] = useState<string[]>([""]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [repoMap, setRepoMap] = useState<RepoMap | null>(null);
  const [mapError, setMapError] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  async function showMap() {
    setMapError("");
    const repoPath = new FormData(formRef.current!).get("repo_path") as string;
    if (!repoPath) return setMapError("Enter a repo path first.");
    try {
      setRepoMap(await api.sessions.repoMap(repoPath));
    } catch {
      setRepoMap(null);
      setMapError("Couldn't read that repo. Check the path.");
    }
  }

  function toggleFile(path: string) {
    setFiles((prev) => {
      const chosen = prev.filter(Boolean);
      const next = chosen.includes(path) ? chosen.filter((f) => f !== path) : [...chosen, path];
      return next.length ? next : [""];
    });
  }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const f = new FormData(e.currentTarget);

    try {
      const { id } = await api.sessions.create({
        name: f.get("name"),
        repo_path: f.get("repo_path"),
        verify_command: f.get("verify_command"),
        max_iterations: Number(f.get("max_iterations")),
        max_cost_usd: f.get("max_cost_usd") ? Number(f.get("max_cost_usd")) : undefined,
        add_tests: f.get("add_tests") === "on",
        cascade: f.get("cascade") === "on",
        model: f.get("model"),
        task: {
          title: f.get("task_title"),
          spec: f.get("spec"),
          files_context: files.filter(Boolean),
        },
      });
      router.push(`/sessions/${id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-xl font-bold text-gray-900 mb-6">New Session</h1>
      <form ref={formRef} onSubmit={submit} className="space-y-5">
        <Field label="Session name" name="name" placeholder="e.g. Add rate limiting" required />
        <Field label="Repo path" name="repo_path" placeholder="/Users/you/projects/my-app" required />
        <div>
          <button type="button" onClick={showMap} className="text-sm text-indigo-600 hover:underline">
            Show repo map and point the agent at files
          </button>
          {mapError && <p className="text-sm text-red-600 mt-1">{mapError}</p>}
          {repoMap && (
            <div className="mt-2">
              <p className="text-xs text-gray-500 mb-2">Select the files where the issue is. The agent starts there.</p>
              <RepoMapView map={repoMap} selected={files.filter(Boolean)} onNodeClick={toggleFile} />
            </div>
          )}
        </div>
        <Field label="Task title" name="task_title" placeholder="e.g. Rate limit auth endpoints" required />

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Task spec</label>
          <textarea name="spec" rows={8} required
            className="w-full border rounded px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="Describe exactly what to implement..." />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Files context</label>
          {files.map((f, i) => (
            <div key={i} className="flex gap-2 mb-2">
              <input value={f} onChange={(e) => setFiles((p) => p.map((x, j) => j === i ? e.target.value : x))}
                className="flex-1 border rounded px-3 py-1.5 text-sm font-mono" placeholder="src/routes/auth.py" />
              <button type="button" onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}
                className="text-gray-400 hover:text-red-500 text-lg leading-none">×</button>
            </div>
          ))}
          <button type="button" onClick={() => setFiles((p) => [...p, ""])}
            className="text-sm text-indigo-600 hover:underline">+ Add file</button>
        </div>

        <Field label="Verify command" name="verify_command" placeholder="pytest tests/" required />

        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input name="add_tests" type="checkbox" />
          Also write tests for the change
        </label>

        <label className="flex items-start gap-2 text-sm text-gray-700">
          <input name="cascade" type="checkbox" className="mt-0.5" />
          <span>
            Try a cheap model first
            <span className="block text-xs text-gray-500">
              Haiku explores and tries the fix. If its fix passes, Sonnet reviews it; the model below redoes the task
              only if the fix fails or the review rejects it. Needs a Claude model below and no uncommitted changes.
            </span>
          </span>
        </label>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Max iterations</label>
            <input name="max_iterations" type="number" defaultValue={10} min={1} max={50}
              className="w-full border rounded px-3 py-1.5 text-sm" />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Cost limit (USD)</label>
            <input name="max_cost_usd" type="number" placeholder="Default: 5" min={0.01} step={0.01}
              className="w-full border rounded px-3 py-1.5 text-sm" />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
            <select name="model" className="w-full border rounded px-3 py-1.5 text-sm">
              <option value="claude-sonnet-5-5">claude-sonnet-5-5</option>
              <option value="claude-opus-5-5">claude-opus-5-5</option>
              <option value="claude-haiku-5-5">claude-haiku-5-5</option>
              <option value="claude-sonnet-4-6">claude-sonnet-4-6</option>
              <option value="claude-opus-4-8">claude-opus-4-8</option>
              <option value="claude-haiku-4-5-20251001">claude-haiku-4-5</option>
            </select>
          </div>
        </div>

        {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}

        <button disabled={loading} type="submit"
          className="w-full bg-indigo-600 text-white py-2 rounded hover:bg-indigo-700 disabled:opacity-50 font-medium">
          {loading ? "Starting..." : "Start Session"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, name, placeholder, required }: { label: string; name: string; placeholder?: string; required?: boolean }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input name={name} placeholder={placeholder} required={required}
        className="w-full border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
    </div>
  );
}

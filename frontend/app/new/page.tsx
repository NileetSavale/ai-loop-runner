"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function NewSession() {
  const router = useRouter();
  const [files, setFiles] = useState<string[]>([""]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
    <div className="max-w-2xl">
      <h1 className="text-xl font-bold text-gray-900 mb-6">New Session</h1>
      <form onSubmit={submit} className="space-y-5">
        <Field label="Session name" name="name" placeholder="e.g. Add rate limiting" required />
        <Field label="Repo path" name="repo_path" placeholder="/Users/you/projects/my-app" required />
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

        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Max iterations</label>
            <input name="max_iterations" type="number" defaultValue={10} min={1} max={50}
              className="w-full border rounded px-3 py-1.5 text-sm" />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
            <select name="model" className="w-full border rounded px-3 py-1.5 text-sm">
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

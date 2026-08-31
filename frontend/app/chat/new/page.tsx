"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function NewChatSession() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const f = new FormData(e.currentTarget);
    try {
      const session = await api.chat.create({
        name: f.get("name"),
        repo_path: f.get("repo_path"),
        verify_command: f.get("verify_command"),
        max_iterations: Number(f.get("max_iterations")),
        model: f.get("model"),
      });
      router.push(`/chat/${session.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="text-xl font-bold text-gray-900 mb-6">New Chat Session</h1>
      <p className="text-sm text-gray-500 mb-6">
        Set the repo and test command once. Then keep prompting features — each message
        runs a full loop and commits on pass.
      </p>

      <form onSubmit={submit} className="space-y-4">
        <Field label="Name" name="name" placeholder="My project" required />
        <Field label="Repo path" name="repo_path" placeholder="/Users/you/projects/my-app" required />
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
          {loading ? "Creating..." : "Start Chat Session"}
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

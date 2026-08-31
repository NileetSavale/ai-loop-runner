"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const PROVIDERS = [
  { id: "anthropic", name: "Anthropic", placeholder: "sk-ant-..." },
  { id: "openai",    name: "OpenAI",    placeholder: "sk-..." },
  { id: "google",    name: "Google",    placeholder: "AIza..." },
  { id: "mistral",   name: "Mistral",   placeholder: "..." },
];

interface StoredKey { id: string; provider: string; label: string; created_at: string }

export default function KeysPage() {
  const [keys, setKeys] = useState<StoredKey[]>([]);
  const [adding, setAdding] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setKeys(await api.keys.list().catch(() => []));
  }

  useEffect(() => { load(); }, []);

  async function save(provider: string) {
    if (!value.trim()) return;
    setSaving(true);
    setError("");
    try {
      await api.keys.add({ provider, api_key: value.trim(), label: label || provider });
      setValue(""); setLabel(""); setAdding(null);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    await api.keys.delete(id);
    await load();
  }

  return (
    <div className="max-w-lg">
      <h1 className="text-xl font-bold text-gray-900 mb-2">API Keys</h1>
      <p className="text-sm text-gray-500 mb-6">
        Add your own keys to use BYOK mode — zero markup, billed directly by the provider.
        Leave empty to use Loop Runner's keys (usage-based billing applies).
      </p>

      <div className="space-y-4">
        {PROVIDERS.map((p) => {
          const stored = keys.find((k) => k.provider === p.id);
          return (
            <div key={p.id} className="border rounded-lg p-4">
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm text-gray-900">{p.name}</span>
                {stored ? (
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded">BYOK active</span>
                    <button onClick={() => remove(stored.id)} className="text-xs text-red-500 hover:underline">Remove</button>
                  </div>
                ) : (
                  <button onClick={() => { setAdding(p.id); setValue(""); setLabel(""); }}
                    className="text-xs text-indigo-600 hover:underline">+ Add key</button>
                )}
              </div>

              {adding === p.id && (
                <div className="mt-3 space-y-2">
                  <input value={value} onChange={(e) => setValue(e.target.value)}
                    placeholder={p.placeholder} type="password"
                    className="w-full border rounded px-3 py-1.5 text-sm font-mono" />
                  <input value={label} onChange={(e) => setLabel(e.target.value)}
                    placeholder="Label (optional)" className="w-full border rounded px-3 py-1.5 text-sm" />
                  {error && <p className="text-xs text-red-600">{error}</p>}
                  <div className="flex gap-2">
                    <button onClick={() => save(p.id)} disabled={saving || !value.trim()}
                      className="bg-indigo-600 text-white text-xs px-3 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50">
                      {saving ? "Saving..." : "Save"}
                    </button>
                    <button onClick={() => setAdding(null)} className="text-xs text-gray-500 hover:text-gray-800">Cancel</button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

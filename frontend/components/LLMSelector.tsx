"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Model { id: string; name: string }
type ModelMap = Record<string, Model[]>;

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google",
  mistral: "Mistral",
};

export function LLMSelector({
  name = "model",
  defaultValue = "claude-sonnet-4-6",
}: {
  name?: string;
  defaultValue?: string;
}) {
  const [models, setModels] = useState<ModelMap>({});
  const [selected, setSelected] = useState(defaultValue);

  useEffect(() => {
    api.keys.models().then(setModels).catch(() => {});
  }, []);

  const allModels = Object.values(models).flat();

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
      <select name={name} value={selected} onChange={(e) => setSelected(e.target.value)}
        className="w-full border rounded px-3 py-1.5 text-sm">
        {Object.entries(models).map(([provider, providerModels]) => (
          <optgroup key={provider} label={PROVIDER_LABELS[provider] ?? provider}>
            {providerModels.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </optgroup>
        ))}
        {allModels.length === 0 && (
          <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
        )}
      </select>
      <p className="text-xs text-gray-400 mt-1">
        Uses your BYOK key if configured in{" "}
        <a href="/settings/keys" className="text-indigo-500 hover:underline">Settings</a>,
        otherwise Loop Runner's key.
      </p>
    </div>
  );
}

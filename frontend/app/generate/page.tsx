"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { LLMSelector } from "@/components/LLMSelector";
import { TestPreview } from "@/components/TestPreview";

type Step = "describe" | "review" | "starting";

interface GeneratedResult {
  test_files: { path: string; content: string }[];
  verify_command: string;
  implementation_spec: string;
}

const STACKS = ["auto-detect", "python", "typescript", "javascript", "go", "rust", "ruby", "java"];

export default function GeneratePage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("describe");

  // step 1 state
  const [description, setDescription] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [stack, setStack] = useState("auto-detect");
  const [contextFiles, setContextFiles] = useState<string[]>([""]);
  const [model, setModel] = useState("claude-sonnet-4-6");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");

  // step 2 state
  const [result, setResult] = useState<GeneratedResult | null>(null);
  const [sessionName, setSessionName] = useState("");
  const [maxIter, setMaxIter] = useState(10);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  // auto-detect stack when repo path is valid
  useEffect(() => {
    if (!repoPath || stack !== "auto-detect") return;
    const t = setTimeout(() => {
      api.testGen.detectStack(repoPath)
        .then((r) => setStack(r.stack))
        .catch(() => {});
    }, 600);
    return () => clearTimeout(t);
  }, [repoPath, stack]);

  async function generate() {
    if (!description.trim() || !repoPath.trim()) return;
    setGenerating(true);
    setGenError("");
    try {
      const r = await api.testGen.generate({
        description: description.trim(),
        repo_path: repoPath.trim(),
        tech_stack: stack === "auto-detect" ? undefined : stack,
        context_files: contextFiles.filter(Boolean),
        model,
      });
      setResult(r);
      setSessionName(description.trim().slice(0, 60));
      setStep("review");
    } catch (e: unknown) {
      setGenError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function startLoop() {
    if (!result) return;
    setStarting(true);
    setStartError("");
    try {
      const { session_id } = await api.testGen.applyAndStart({
        repo_path: repoPath.trim(),
        test_files: result.test_files,
        verify_command: result.verify_command,
        implementation_spec: result.implementation_spec,
        session_name: sessionName || description.slice(0, 60),
        model,
        max_iterations: maxIter,
      });
      router.push(`/sessions/${session_id}`);
    } catch (e: unknown) {
      setStartError(e instanceof Error ? e.message : "Failed to start");
      setStarting(false);
    }
  }

  return (
    <div className="max-w-3xl">
      {/* stepper */}
      <div className="flex items-center gap-2 mb-8">
        {(["describe", "review"] as Step[]).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            {i > 0 && <div className="w-8 h-px bg-gray-200" />}
            <div className={`flex items-center gap-2 text-sm font-medium ${step === s ? "text-indigo-600" : "text-gray-400"}`}>
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${step === s ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-500"}`}>
                {i + 1}
              </span>
              {s === "describe" ? "Describe" : "Review & Run"}
            </div>
          </div>
        ))}
      </div>

      {step === "describe" && (
        <div className="space-y-6">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Generate test suite</h1>
            <p className="text-sm text-gray-500 mt-1">
              Describe what you're building. The agent writes failing tests that define
              the spec — then the loop implements the code until they pass.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              What are you building?
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={6}
              placeholder={`Examples:\n\n"A sliding-window rate limiter class that tracks requests per client. Max 5 requests per minute. Returns retry-after seconds when blocked."\n\n"A REST API endpoint POST /users that validates email uniqueness, hashes passwords with bcrypt, and returns 201 with the user ID on success."`}
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Repo path</label>
              <input value={repoPath} onChange={(e) => { setRepoPath(e.target.value); setStack("auto-detect"); }}
                placeholder="/Users/you/projects/my-app"
                className="w-full border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tech stack</label>
              <select value={stack} onChange={(e) => setStack(e.target.value)}
                className="w-full border rounded px-3 py-1.5 text-sm">
                {STACKS.map((s) => (
                  <option key={s} value={s}>{s === "auto-detect" ? "Auto-detect" : s}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Existing files to include as context <span className="text-gray-400 font-normal">(optional — helps the agent match your style)</span>
            </label>
            {contextFiles.map((f, i) => (
              <div key={i} className="flex gap-2 mb-2">
                <input value={f} onChange={(e) => setContextFiles((p) => p.map((x, j) => j === i ? e.target.value : x))}
                  placeholder="src/models.py" className="flex-1 border rounded px-3 py-1.5 text-sm font-mono" />
                <button type="button" onClick={() => setContextFiles((p) => p.filter((_, j) => j !== i))}
                  className="text-gray-400 hover:text-red-500 text-lg leading-none">×</button>
              </div>
            ))}
            <button type="button" onClick={() => setContextFiles((p) => [...p, ""])}
              className="text-sm text-indigo-600 hover:underline">+ Add file</button>
          </div>

          <LLMSelector defaultValue={model} />

          {genError && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{genError}</p>}

          <button onClick={generate} disabled={generating || !description.trim() || !repoPath.trim()}
            className="w-full bg-indigo-600 text-white py-2.5 rounded hover:bg-indigo-700 disabled:opacity-50 font-medium">
            {generating ? (
              <span className="flex items-center justify-center gap-2">
                <Spinner /> Generating tests...
              </span>
            ) : "Generate Test Suite →"}
          </button>
        </div>
      )}

      {step === "review" && result && (
        <div className="space-y-6">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-xl font-bold text-gray-900">Review generated tests</h1>
              <p className="text-sm text-gray-500 mt-1">
                {result.test_files.length} file{result.test_files.length !== 1 ? "s" : ""} · verify: <code className="bg-gray-100 px-1 rounded">{result.verify_command}</code>
              </p>
            </div>
            <button onClick={() => { setStep("describe"); setResult(null); }}
              className="text-sm text-gray-500 hover:text-gray-800 border rounded px-3 py-1.5">
              ← Regenerate
            </button>
          </div>

          {/* implementation spec */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-xs font-semibold text-blue-700 mb-1">Implementation spec (sent to coding agent)</p>
            <p className="text-sm text-blue-900">{result.implementation_spec}</p>
          </div>

          {/* test file previews */}
          <TestPreview files={result.test_files} onChange={(files) => setResult({ ...result, test_files: files })} />

          {/* session config */}
          <div className="border-t pt-4 space-y-3">
            <h2 className="text-sm font-semibold text-gray-700">Loop configuration</h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Session name</label>
                <input value={sessionName} onChange={(e) => setSessionName(e.target.value)}
                  className="w-full border rounded px-3 py-1.5 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Max iterations</label>
                <input type="number" value={maxIter} onChange={(e) => setMaxIter(Number(e.target.value))}
                  min={1} max={50} className="w-full border rounded px-3 py-1.5 text-sm" />
              </div>
            </div>
          </div>

          {startError && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{startError}</p>}

          <button onClick={startLoop} disabled={starting}
            className="w-full bg-green-600 text-white py-2.5 rounded hover:bg-green-700 disabled:opacity-50 font-medium">
            {starting ? (
              <span className="flex items-center justify-center gap-2"><Spinner /> Writing tests & starting loop...</span>
            ) : "Write Tests & Start Loop →"}
          </button>
        </div>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
    </svg>
  );
}

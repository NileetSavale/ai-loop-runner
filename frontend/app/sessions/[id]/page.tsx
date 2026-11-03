import { api } from "@/lib/api-server";
import { StatusBadge } from "@/components/StatusBadge";
import { LiveLoop } from "@/components/LiveLoop";
import { StopButton } from "./StopButton";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function SessionPage({ params }: { params: { id: string } }) {
  const session = await api.sessions.get(params.id).catch(() => null);
  if (!session) notFound();

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-gray-900">{session.name}</h1>
            <StatusBadge status={session.status} />
          </div>
          <p className="text-sm text-gray-500 mt-1">{session.repo_path}</p>
          <p className="text-xs text-gray-400 font-mono mt-0.5">{session.verify_command}</p>
        </div>
        {session.status === "running" && <StopButton sessionId={session.id} />}
      </div>

      <LiveLoop sessionId={session.id} initialIterations={session.iterations} />

      {session.status !== "running" && (
        <div className="border-t pt-4 text-sm text-gray-500 flex gap-6">
          <span>Total cost: <strong className="text-gray-900">${session.total_cost_usd.toFixed(4)}</strong></span>
          <span>Iterations: <strong className="text-gray-900">{session.total_iterations}</strong></span>
          <span>Tokens: <strong className="text-gray-900">{session.total_tokens.toLocaleString()}</strong></span>
        </div>
      )}
    </div>
  );
}

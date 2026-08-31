import Link from "next/link";
import type { Session } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

export function SessionCard({ session }: { session: Session }) {
  const duration = session.completed_at
    ? ((new Date(session.completed_at).getTime() - new Date(session.created_at).getTime()) / 1000).toFixed(0)
    : null;

  return (
    <Link href={`/sessions/${session.id}`} className="block border rounded-lg p-4 hover:bg-gray-50 transition-colors">
      <div className="flex items-center justify-between">
        <span className="font-medium text-gray-900">{session.name}</span>
        <StatusBadge status={session.status} />
      </div>
      <div className="mt-1 text-sm text-gray-500 flex gap-4">
        <span>{session.total_iterations} iter</span>
        <span>${session.total_cost_usd.toFixed(4)}</span>
        {duration && <span>{duration}s</span>}
        <span>{new Date(session.created_at).toLocaleDateString()}</span>
      </div>
    </Link>
  );
}

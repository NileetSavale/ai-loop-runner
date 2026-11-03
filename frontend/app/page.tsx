import { api } from "@/lib/api-server";
import { SessionCard } from "@/components/SessionCard";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [sessions, summary] = await Promise.all([
    api.sessions.list().catch(() => []),
    api.analytics.summary().catch(() => null),
  ]);

  const active = sessions.find((s) => s.status === "running");
  const recent = sessions.slice(0, 5);

  return (
    <div className="space-y-8">
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Sessions", value: summary.total_sessions },
            { label: "Success rate", value: `${(summary.success_rate * 100).toFixed(0)}%` },
            { label: "Total cost", value: `$${summary.total_cost_usd.toFixed(2)}` },
            { label: "Avg iterations", value: summary.avg_iterations_to_pass.toFixed(1) },
          ].map((stat) => (
            <div key={stat.label} className="bg-white border rounded-lg p-4">
              <p className="text-xs text-gray-500">{stat.label}</p>
              <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
            </div>
          ))}
        </div>
      )}

      {active && (
        <div>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Active</h2>
          <SessionCard session={active} />
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Recent Sessions</h2>
          <Link href="/sessions" className="text-sm text-indigo-600 hover:underline">View all</Link>
        </div>
        {recent.length === 0 ? (
          <p className="text-gray-400 text-sm">No sessions yet. <Link href="/new" className="text-indigo-600 hover:underline">Start one.</Link></p>
        ) : (
          <div className="space-y-2">{recent.map((s) => <SessionCard key={s.id} session={s} />)}</div>
        )}
      </div>
    </div>
  );
}

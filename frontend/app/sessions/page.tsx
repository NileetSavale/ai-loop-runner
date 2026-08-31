import { api } from "@/lib/api";
import { SessionCard } from "@/components/SessionCard";

export const dynamic = "force-dynamic";

export default async function SessionsPage() {
  const sessions = await api.sessions.list().catch(() => []);

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-900 mb-6">All Sessions</h1>
      {sessions.length === 0 ? (
        <p className="text-gray-400">No sessions yet.</p>
      ) : (
        <div className="space-y-2">
          {sessions.map((s) => <SessionCard key={s.id} session={s} />)}
        </div>
      )}
    </div>
  );
}

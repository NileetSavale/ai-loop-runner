import { api } from "@/lib/api-server";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function ChatListPage() {
  const sessions = await api.chat.list().catch(() => []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-gray-900">Chat Sessions</h1>
        <Link href="/chat/new" className="bg-indigo-600 text-white text-sm px-3 py-1.5 rounded hover:bg-indigo-700">
          New Chat
        </Link>
      </div>

      {sessions.length === 0 ? (
        <p className="text-gray-400 text-sm">
          No chat sessions yet. <Link href="/chat/new" className="text-indigo-600 hover:underline">Start one.</Link>
        </p>
      ) : (
        <div className="space-y-2">
          {sessions.map((s) => (
            <Link key={s.id} href={`/chat/${s.id}`}
              className="block border rounded-lg p-4 bg-white hover:bg-gray-50 transition-colors">
              <p className="font-medium text-gray-900">{s.name}</p>
              <p className="text-xs text-gray-400 mt-1 font-mono">{s.repo_path}</p>
              <p className="text-xs text-gray-400">{s.verify_command} · {s.model}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

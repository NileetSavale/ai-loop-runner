import { api } from "@/lib/api-server";
import { ChatInterface } from "@/components/ChatInterface";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const session = await api.chat.get(id).catch(() => null);
  if (!session) notFound();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-gray-900">{session.name}</h1>
        <p className="text-xs text-gray-400 font-mono mt-0.5">
          {session.repo_path} · {session.verify_command} · {session.model}
        </p>
      </div>
      <ChatInterface chatSessionId={session.id} initialMessages={session.messages} />
    </div>
  );
}

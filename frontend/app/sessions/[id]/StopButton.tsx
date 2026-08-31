"use client";
import { useRouter } from "next/navigation";
import { useStopSession } from "@/lib/queries";

export function StopButton({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const stop = useStopSession();

  async function handleStop() {
    await stop.mutateAsync(sessionId);
    router.refresh();
  }

  return (
    <button onClick={handleStop} disabled={stop.isPending}
      className="text-sm px-3 py-1.5 border border-red-300 text-red-600 rounded hover:bg-red-50 disabled:opacity-50">
      {stop.isPending ? "Stopping..." : "Stop"}
    </button>
  );
}

"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authEnabled, getSupabase } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";

export function NavUser() {
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (!authEnabled) return;
    const sb = getSupabase();
    sb.auth.getUser().then(({ data }) => setUser(data.user));
    const { data: { subscription } } = sb.auth.onAuthStateChange((_, session) => {
      setUser(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  async function signOut() {
    await getSupabase().auth.signOut();
    router.push("/login");
  }

  if (!authEnabled) return (
    <span className="text-sm text-gray-500" title="No login: Supabase isn't configured">Local mode</span>
  );

  if (!user) return (
    <Link href="/login" className="text-sm text-gray-500 hover:text-gray-900">Sign in</Link>
  );

  return (
    <div className="relative">
      <button onClick={() => setOpen((p) => !p)}
        className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 font-medium text-sm flex items-center justify-center">
        {user.email?.[0].toUpperCase()}
      </button>
      {open && (
        <div className="absolute right-0 top-10 bg-white border rounded-lg shadow-lg w-48 py-1 z-20">
          <p className="px-3 py-1 text-xs text-gray-400 truncate">{user.email}</p>
          <Link href="/settings/keys" onClick={() => setOpen(false)}
            className="block px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
            API Keys
          </Link>
          <button onClick={signOut}
            className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-red-50">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

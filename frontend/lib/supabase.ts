import { createBrowserClient } from "@supabase/ssr";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

// Without Supabase settings the site runs in local mode: no login, and the backend serves it anonymously
// (ALLOW_ANONYMOUS=true), so a fresh clone works with no accounts to set up.
export const authEnabled = Boolean(url && key);

// ponytail: one singleton for the browser
let _client: ReturnType<typeof createBrowserClient> | null = null;

export function getSupabase() {
  if (!authEnabled) throw new Error("Login is off: Supabase isn't configured (local mode)");
  if (!_client) _client = createBrowserClient(url, key);
  return _client;
}

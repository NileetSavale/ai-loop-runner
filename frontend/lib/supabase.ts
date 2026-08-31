import { createBrowserClient } from "@supabase/ssr";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

// ponytail: one singleton for the browser
let _client: ReturnType<typeof createBrowserClient> | null = null;

export function getSupabase() {
  if (!_client) _client = createBrowserClient(url, key);
  return _client;
}

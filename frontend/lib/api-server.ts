import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { createApi } from "./api";

// For server components: the browser client can't see the session, so read it from cookies
async function serverToken(): Promise<string> {
  try {
    const store = await cookies();
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      { cookies: { getAll: () => store.getAll(), setAll: () => {} } }
    );
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? "";
  } catch {
    return "";
  }
}

// In production the browser's relative /api URL means nothing on the server, so call the backend directly
export const api = createApi(
  process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  serverToken
);

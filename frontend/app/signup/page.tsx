"use client";
import { useState } from "react";
import Link from "next/link";
import { getSupabase } from "@/lib/supabase";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const { error } = await getSupabase().auth.signUp({ email, password });
    if (error) { setError(error.message); setLoading(false); }
    else setDone(true);
  }

  if (done) return (
    <div className="max-w-sm mx-auto mt-16 text-center">
      <p className="text-lg font-medium text-gray-900">Check your email</p>
      <p className="text-sm text-gray-500 mt-2">We sent a confirmation link to <strong>{email}</strong>.</p>
    </div>
  );

  return (
    <div className="max-w-sm mx-auto mt-16">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Create account</h1>
      <p className="text-sm text-gray-500 mb-8">
        Already have one? <Link href="/login" className="text-indigo-600 hover:underline">Sign in</Link>
      </p>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        </div>
        {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}
        <button type="submit" disabled={loading}
          className="w-full bg-indigo-600 text-white py-2 rounded hover:bg-indigo-700 disabled:opacity-50 font-medium text-sm">
          {loading ? "Creating account..." : "Create account"}
        </button>
      </form>
    </div>
  );
}

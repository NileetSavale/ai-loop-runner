import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { Providers } from "./providers";
import { NavUser } from "@/components/NavUser";

export const metadata: Metadata = { title: "Loop Runner" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 min-h-screen">
        <Providers>
          <nav className="bg-white border-b px-6 py-3 flex flex-wrap gap-x-6 gap-y-2 items-center">
            <Link href="/" className="font-semibold text-gray-900">Loop Runner</Link>
            <Link href="/chat" className="text-sm text-gray-500 hover:text-gray-900">Chat</Link>
            <Link href="/sessions" className="text-sm text-gray-500 hover:text-gray-900">Sessions</Link>
            <Link href="/analytics" className="text-sm text-gray-500 hover:text-gray-900">Analytics</Link>
            <div className="ml-auto flex items-center gap-3">
              <Link href="/generate" className="bg-indigo-600 text-white text-sm px-3 py-1.5 rounded hover:bg-indigo-700">
                Generate Tests
              </Link>
              <NavUser />
            </div>
          </nav>
          <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}

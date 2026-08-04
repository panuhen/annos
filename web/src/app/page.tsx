"use client";

import Link from "next/link";

import { authClient } from "@/lib/auth-client";

export default function Home() {
  const { data: session, isPending } = authClient.useSession();

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col p-6">
      <main className="flex flex-1 flex-col justify-center gap-4">
        <h1 className="text-3xl font-semibold">Annos</h1>
        <p className="text-neutral-500">
          Food, exercise and weight tracking — over MCP and on the web.
        </p>
        {isPending ? null : session ? (
          <div className="flex items-center gap-4 text-sm">
            <span>Signed in.</span>
            <button
              onClick={() => authClient.signOut()}
              className="underline"
            >
              Sign out
            </button>
          </div>
        ) : (
          <div className="flex gap-4 text-sm">
            <Link href="/sign-in" className="underline">
              Sign in
            </Link>
            <Link href="/sign-up" className="underline">
              Sign up
            </Link>
          </div>
        )}
      </main>
      <footer className="py-4 text-xs text-neutral-500">
        Food composition data:{" "}
        <a
          href="https://fineli.fi"
          className="underline"
          rel="license noopener"
        >
          Fineli
        </a>
        , National Institute for Health and Welfare,{" "}
        <a
          href="https://creativecommons.org/licenses/by/4.0/"
          className="underline"
          rel="license noopener"
        >
          CC BY 4.0
        </a>
        .
      </footer>
    </div>
  );
}

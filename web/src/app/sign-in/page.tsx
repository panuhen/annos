"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthSheet } from "@/components/auth-sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";

/**
 * Doubles as the OAuth login page: when an MCP client hits /mcp/authorize
 * unauthenticated, Better Auth redirects here with the OAuth query intact.
 * After sign-in we send the browser back to the authorize endpoint with that
 * same query so the flow can finish.
 */
function SignInForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const oauthFlow = searchParams.has("client_id");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const { error } = await authClient.signIn.email({ email, password });
    if (error) {
      setError(error.message ?? "Sign-in failed");
      setPending(false);
      return;
    }
    if (oauthFlow) {
      window.location.href = `/api/auth/mcp/authorize?${searchParams.toString()}`;
    } else {
      router.push("/");
    }
  }

  return (
    <AuthSheet title="Sign in">
      {oauthFlow && (
        <p className="mb-4 border border-border px-3 py-2 text-sm">
          An application is asking to access your Annos data. Sign in to continue.
        </p>
      )}
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="email" className="mb-1.5 font-mono text-xs uppercase">
            Email
          </Label>
          <Input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-12 text-base"
          />
        </div>
        <div>
          <Label htmlFor="password" className="mb-1.5 font-mono text-xs uppercase">
            Password
          </Label>
          <Input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-12 text-base"
          />
        </div>
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="mt-1 flex min-h-12 items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-5 text-sm text-muted-foreground">
        No account?{" "}
        <Link href="/sign-up" className="text-primary underline underline-offset-2">
          Sign up
        </Link>
      </p>
    </AuthSheet>
  );
}

export default function SignInPage() {
  return (
    <Suspense>
      <SignInForm />
    </Suspense>
  );
}

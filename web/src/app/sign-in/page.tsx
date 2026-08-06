"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { useTranslations } from "next-intl";

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
  const t = useTranslations("auth");
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const oauthFlow = searchParams.has("client_id");

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    // The values come from the form, not component state: credentials the
    // browser autofills never fire React's onChange, so a submit reading
    // state posts empty strings — the "enter it twice" bug.
    const form = new FormData(event.currentTarget);
    const { error } = await authClient.signIn.email({
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    });
    if (error) {
      setError(error.message ?? t("signInFailed"));
      setPending(false);
      return;
    }
    if (oauthFlow) {
      window.location.href = `/api/auth/mcp/authorize?${searchParams.toString()}`;
    } else {
      // A full navigation, not router.push: crossing the auth boundary is
      // where the client-side session store must be rebuilt, not trusted.
      window.location.href = "/";
    }
  }

  return (
    <AuthSheet title={t("signInTitle")}>
      {oauthFlow && (
        <p className="mb-4 border border-border px-3 py-2 text-sm">
          {t("oauthNotice")}
        </p>
      )}
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="email" className="mb-1.5 font-mono text-xs uppercase">
            {t("email")}
          </Label>
          <Input
            id="email"
            name="email"
            type="email"
            required
            autoComplete="email"
            className="h-12 text-base"
          />
        </div>
        <div>
          <Label htmlFor="password" className="mb-1.5 font-mono text-xs uppercase">
            {t("password")}
          </Label>
          <Input
            id="password"
            name="password"
            type="password"
            required
            autoComplete="current-password"
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
          {pending ? t("signingIn") : t("signIn")}
        </button>
      </form>
      <p className="mt-5 text-sm text-muted-foreground">
        {t("noAccount")}{" "}
        <Link href="/sign-up" className="text-primary underline underline-offset-2">
          {t("signUp")}
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

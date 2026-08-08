"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { useTranslations } from "next-intl";

import { AuthSheet } from "@/components/auth-sheet";
import { GoogleButton } from "@/components/google-button";
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
  // Set when sign-in fails on an unverified address, so the page can offer to
  // resend the confirmation link to exactly that address.
  const [unverified, setUnverified] = useState<string | null>(null);
  const [resent, setResent] = useState(false);

  const oauthFlow = searchParams.has("client_id");
  const googleEnabled = process.env.NEXT_PUBLIC_GOOGLE_ENABLED === "true";
  // Where a completed sign-in should land — the OAuth continuation when this
  // page is standing in as the MCP login page, otherwise the app root. Google
  // sign-in uses the same target.
  const destination = oauthFlow
    ? `/api/auth/mcp/authorize?${searchParams.toString()}`
    : "/";

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setUnverified(null);
    setResent(false);
    // The values come from the form, not component state: credentials the
    // browser autofills never fire React's onChange, so a submit reading
    // state posts empty strings — the "enter it twice" bug.
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const { error } = await authClient.signIn.email({
      email,
      password: String(form.get("password") ?? ""),
    });
    if (error) {
      // Verification is required: an unverified account can't sign in. Say so
      // plainly and let them resend, rather than the generic failure.
      if (error.code === "EMAIL_NOT_VERIFIED") {
        setUnverified(email);
        setError(t("notVerified"));
      } else {
        setError(error.message ?? t("signInFailed"));
      }
      setPending(false);
      return;
    }
    // A full navigation, not router.push: crossing the auth boundary is where
    // the client-side session store must be rebuilt, not trusted.
    window.location.href = destination;
  }

  async function resendVerification() {
    if (!unverified) return;
    await authClient.sendVerificationEmail({ email: unverified, callbackURL: "/welcome" });
    setResent(true);
  }

  return (
    <AuthSheet title={t("signInTitle")}>
      {oauthFlow && (
        <p className="mb-4 border border-border px-3 py-2 text-sm">
          {t("oauthNotice")}
        </p>
      )}
      {googleEnabled && (
        <>
          <GoogleButton callbackURL={destination} />
          <div className="my-4 flex items-center gap-3 text-xs uppercase text-muted-foreground">
            <span className="h-px flex-1 bg-border" />
            {t("or")}
            <span className="h-px flex-1 bg-border" />
          </div>
        </>
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
          <Link
            href="/forgot-password"
            className="mt-1.5 inline-block text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            {t("forgotPassword")}
          </Link>
        </div>
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        {unverified &&
          (resent ? (
            <p className="text-sm text-muted-foreground">{t("resendSent")}</p>
          ) : (
            <button
              type="button"
              onClick={resendVerification}
              className="self-start text-sm text-primary underline underline-offset-2"
            >
              {t("resend")}
            </button>
          ))}
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

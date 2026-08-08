"use client";

import Link from "next/link";
import { useState } from "react";

import { useTranslations } from "next-intl";

import { AuthSheet } from "@/components/auth-sheet";
import { GoogleButton } from "@/components/google-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";

/**
 * Registration is UI-only by design — a hallucinating MCP client must not be
 * able to create an account. Better Auth owns the credential; the Annos
 * profile (with its generated nickname) is created at /welcome afterwards.
 *
 * No name is collected: Better Auth's `name` field is deliberately left empty.
 * The only human-readable identifier Annos ever uses is its own generated
 * nickname.
 */
export default function SignUpPage() {
  const t = useTranslations("auth");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // Verification is required, so sign-up no longer yields a session. Instead of
  // sending the browser to /welcome, we show a "check your mail" state; the
  // nickname roll now happens on the verification click (auth.ts routes it to
  // /welcome via autoSignInAfterVerification).
  const [sent, setSent] = useState(false);
  const googleEnabled = process.env.NEXT_PUBLIC_GOOGLE_ENABLED === "true";

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    // Form values, not component state — autofilled credentials never fire
    // React's onChange. Same fix as the sign-in page.
    const form = new FormData(event.currentTarget);
    const { error } = await authClient.signUp.email({
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
      name: "",
      // The verification link lands here, session in hand, to draw a nickname.
      callbackURL: "/welcome",
    });
    if (error) {
      setError(error.message ?? t("signUpFailed"));
      setPending(false);
      return;
    }
    setSent(true);
    setPending(false);
  }

  if (sent) {
    return (
      <AuthSheet title={t("checkEmailTitle")}>
        <p className="text-sm text-muted-foreground">{t("checkEmailBody")}</p>
        <p className="mt-5 text-sm text-muted-foreground">
          <Link href="/sign-in" className="text-primary underline underline-offset-2">
            {t("signIn")}
          </Link>
        </p>
      </AuthSheet>
    );
  }

  return (
    <AuthSheet title={t("signUpTitle")}>
      {googleEnabled && (
        <>
          <GoogleButton />
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
            minLength={12}
            autoComplete="new-password"
            className="h-12 text-base"
          />
        </div>
        <p className="text-xs text-muted-foreground">
          {t("quarantine")}
        </p>
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
          {pending ? t("creating") : t("signUp")}
        </button>
        <p className="text-xs text-muted-foreground">
          {t.rich("agree", {
            terms: (chunks) => (
              <Link href="/terms" className="underline underline-offset-2 hover:text-foreground">
                {chunks}
              </Link>
            ),
            privacy: (chunks) => (
              <Link href="/privacy" className="underline underline-offset-2 hover:text-foreground">
                {chunks}
              </Link>
            ),
          })}
        </p>
      </form>
      <p className="mt-5 text-sm text-muted-foreground">
        {t("haveAccount")}{" "}
        <Link href="/sign-in" className="text-primary underline underline-offset-2">
          {t("signIn")}
        </Link>
      </p>
    </AuthSheet>
  );
}

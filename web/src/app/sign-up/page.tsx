"use client";

import Link from "next/link";
import { useState } from "react";

import { useTranslations } from "next-intl";

import { AuthSheet } from "@/components/auth-sheet";
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
    });
    if (error) {
      setError(error.message ?? t("signUpFailed"));
      setPending(false);
      return;
    }
    // Full navigation: crossing the auth boundary rebuilds the session store.
    window.location.href = "/welcome";
  }

  return (
    <AuthSheet title={t("signUpTitle")}>
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
            minLength={8}
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

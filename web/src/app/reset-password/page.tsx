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
 * Lands here from the reset link. Better Auth validates the token and redirects
 * with `?token=` (or `?error=` when it's spent or expired). We only choose the
 * new password; the token proves the identity.
 */
function ResetPasswordForm() {
  const t = useTranslations("auth");
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const linkError = searchParams.get("error");

  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  // No token, or Better Auth already rejected it: nothing to submit against.
  if (!token || linkError) {
    return (
      <AuthSheet title={t("resetTitle")}>
        <p className="text-sm text-destructive" role="alert">
          {t("resetInvalid")}
        </p>
        <p className="mt-5 text-sm text-muted-foreground">
          <Link
            href="/forgot-password"
            className="text-primary underline underline-offset-2"
          >
            {t("forgotTitle")}
          </Link>
        </p>
      </AuthSheet>
    );
  }

  if (done) {
    return (
      <AuthSheet title={t("resetTitle")}>
        <p className="text-sm text-muted-foreground">{t("resetDone")}</p>
        <p className="mt-5 text-sm text-muted-foreground">
          <Link href="/sign-in" className="text-primary underline underline-offset-2">
            {t("signIn")}
          </Link>
        </p>
      </AuthSheet>
    );
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const { error } = await authClient.resetPassword({
      newPassword: String(form.get("password") ?? ""),
      token: token!,
    });
    if (error) {
      setError(error.message ?? t("resetFailed"));
      setPending(false);
      return;
    }
    setDone(true);
    setPending(false);
  }

  return (
    <AuthSheet title={t("resetTitle")}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="password" className="mb-1.5 font-mono text-xs uppercase">
            {t("newPassword")}
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
          {pending ? t("resetting") : t("resetSubmit")}
        </button>
      </form>
    </AuthSheet>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPasswordForm />
    </Suspense>
  );
}

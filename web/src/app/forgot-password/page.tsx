"use client";

import Link from "next/link";
import { useState } from "react";

import { useTranslations } from "next-intl";

import { AuthSheet } from "@/components/auth-sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";

/**
 * Request a password-reset link. The response is deliberately the same whether
 * or not the address has an account — an account either exists or it doesn't is
 * not something this page will confirm to an enumerator.
 */
export default function ForgotPasswordPage() {
  const t = useTranslations("auth");
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    const form = new FormData(event.currentTarget);
    // Better Auth appends the token to redirectTo; /reset-password reads it.
    // Errors are swallowed on purpose — the screen looks identical either way.
    await authClient.requestPasswordReset({
      email: String(form.get("email") ?? ""),
      redirectTo: "/reset-password",
    });
    setSent(true);
    setPending(false);
  }

  if (sent) {
    return (
      <AuthSheet title={t("forgotTitle")}>
        <p className="text-sm text-muted-foreground">{t("resetSent")}</p>
        <p className="mt-5 text-sm text-muted-foreground">
          <Link href="/sign-in" className="text-primary underline underline-offset-2">
            {t("backToSignIn")}
          </Link>
        </p>
      </AuthSheet>
    );
  }

  return (
    <AuthSheet title={t("forgotTitle")}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">{t("forgotBody")}</p>
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
        <button
          type="submit"
          disabled={pending}
          className="mt-1 flex min-h-12 items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending ? t("sending") : t("sendResetLink")}
        </button>
      </form>
      <p className="mt-5 text-sm text-muted-foreground">
        <Link href="/sign-in" className="text-primary underline underline-offset-2">
          {t("backToSignIn")}
        </Link>
      </p>
    </AuthSheet>
  );
}

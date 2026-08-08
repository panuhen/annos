"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { AnnosWordmark } from "@/components/wordmark";

/** The letterhead shell shared by the pages outside the app gate: the mark
 * and wordmark centered above the sheet's opening rule, with the legal links
 * ruled off at the foot — the one place they're reachable pre-sign-in. */
export function AuthSheet({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const t = useTranslations("auth");
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-4 py-10">
      <header className="flex flex-col items-center pb-4">
        <Link href="/" className="flex flex-col items-center">
          <AnnosWordmark className="text-5xl" />
        </Link>
      </header>
      <div className="border-t-2 border-foreground" />
      <h1 className="pt-4 text-2xl font-bold tracking-tight text-balance">{title}</h1>
      <div className="pt-5">{children}</div>
      <footer className="mt-8 flex justify-center gap-4 border-t border-border pt-4 font-mono text-xs uppercase tracking-wide text-muted-foreground">
        <Link href="/privacy" className="hover:text-foreground">
          {t("privacyLink")}
        </Link>
        <Link href="/terms" className="hover:text-foreground">
          {t("termsLink")}
        </Link>
      </footer>
    </main>
  );
}

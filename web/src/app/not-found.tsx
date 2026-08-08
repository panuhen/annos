import Link from "next/link";

import { useTranslations } from "next-intl";

/**
 * The one page reached by accident, so it stays in character: "404" set in the
 * same Playwrite Cuba hand as the wordmark — the mark's face carrying the error,
 * so no wordmark is needed above it — under a short sheet rule, a menu-themed
 * line, and the single ochre way back. Rendered by the root layout only
 * (outside the app gate), so no nav bar, like the auth sheets.
 */
export default function NotFound() {
  const t = useTranslations("notFound");
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center px-4 py-10 text-center">
      <p className="font-display text-8xl leading-none">404</p>
      <div className="mt-8 w-16 border-t-2 border-foreground" />
      <p className="mt-8 text-base text-muted-foreground text-balance">
        {t("message")}
      </p>
      <Link
        href="/"
        className="mt-8 font-mono text-sm uppercase tracking-wide text-primary underline underline-offset-4 hover:opacity-80"
      >
        {t("home")}
      </Link>
    </main>
  );
}

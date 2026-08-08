import Link from "next/link";

import { AnnosWordmark } from "@/components/wordmark";

/**
 * The shell for the public legal pages (/privacy, /terms). Same letterhead as
 * the auth sheet — wordmark over an opening rule — widened for reading, with
 * the prose styled through child-combinator classes so each page body is plain
 * numbered <section>/<h2>/<p>/<ul> JSX. English only, by decision: the legal
 * text is not part of the app's trilingual string system.
 */
export function LegalLayout({
  title,
  lastUpdated,
  children,
}: {
  title: string;
  lastUpdated: string;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 py-10">
      <header className="flex flex-col items-center pb-4">
        <Link href="/" className="flex flex-col items-center">
          <AnnosWordmark className="text-5xl" />
        </Link>
      </header>
      <div className="border-t-2 border-foreground" />
      <h1 className="pt-4 text-2xl font-bold tracking-tight text-balance">{title}</h1>
      <p className="mt-1 font-mono text-xs uppercase tracking-wide text-muted-foreground">
        Last updated: {lastUpdated}
      </p>

      <article
        className={[
          "mt-6",
          "[&_h2]:mt-8 [&_h2]:mb-2 [&_h2]:text-base [&_h2]:font-bold [&_h2]:text-foreground",
          "[&_p]:mb-3 [&_p]:text-sm [&_p]:leading-relaxed [&_p]:text-muted-foreground",
          "[&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1",
          "[&_li]:text-sm [&_li]:leading-relaxed [&_li]:text-muted-foreground",
          "[&_a]:text-foreground [&_a]:underline [&_a]:underline-offset-2",
          "[&_strong]:font-semibold [&_strong]:text-foreground",
          "[&_.fine]:text-xs [&_.fine]:text-muted-foreground",
        ].join(" ")}
      >
        {children}
      </article>

      <footer className="mt-10 flex gap-4 border-t border-border pt-4 font-mono text-xs uppercase tracking-wide text-muted-foreground">
        <Link href="/" className="hover:text-foreground">
          Home
        </Link>
        <Link href="/privacy" className="hover:text-foreground">
          Privacy
        </Link>
        <Link href="/terms" className="hover:text-foreground">
          Terms
        </Link>
      </footer>
    </main>
  );
}

import Link from "next/link";

import { FineliFooter } from "@/components/fineli-footer";
import { AnnosWordmark } from "@/components/wordmark";

/** The letterhead shell shared by the pages outside the app gate: the mark
 * and wordmark centered above the sheet's opening rule. */
export function AuthSheet({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col px-4">
      <header className="flex flex-col items-center pt-10 pb-4">
        <Link href="/" className="flex flex-col items-center">
          <AnnosWordmark className="text-5xl" />
        </Link>
      </header>
      <div className="border-t-2 border-foreground" />
      <h1 className="pt-4 text-2xl font-bold tracking-tight text-balance">{title}</h1>
      <div className="flex-1 pt-5 pb-10">{children}</div>
      <FineliFooter className="pb-6 font-mono text-[0.625rem] leading-relaxed text-muted-foreground" />
    </main>
  );
}

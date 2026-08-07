import Link from "next/link";

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
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-4 py-10">
      <header className="flex flex-col items-center pb-4">
        <Link href="/" className="flex flex-col items-center">
          <AnnosWordmark className="text-5xl" />
        </Link>
      </header>
      <div className="border-t-2 border-foreground" />
      <h1 className="pt-4 text-2xl font-bold tracking-tight text-balance">{title}</h1>
      <div className="pt-5">{children}</div>
    </main>
  );
}

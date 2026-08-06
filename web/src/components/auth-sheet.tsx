import Link from "next/link";

/** The letterhead shell shared by the pages outside the app gate. */
export function AuthSheet({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col px-4">
      <header className="pt-10 pb-2">
        <Link href="/" className="text-sm font-bold tracking-tight">
          Annos
        </Link>
      </header>
      <div className="border-t-2 border-foreground" />
      <h1 className="pt-4 text-2xl font-bold tracking-tight text-balance">{title}</h1>
      <div className="flex-1 pt-5 pb-10">{children}</div>
      <footer className="pb-6 font-mono text-[0.625rem] leading-relaxed text-muted-foreground">
        Food composition data:{" "}
        <a href="https://fineli.fi" rel="license noopener" className="underline">
          Fineli
        </a>
        , National Institute for Health and Welfare,{" "}
        <a
          href="https://creativecommons.org/licenses/by/4.0/"
          rel="license noopener"
          className="underline"
        >
          CC BY 4.0
        </a>
        .
      </footer>
    </main>
  );
}

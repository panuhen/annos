import { DeviceMobile, Plugs } from "@phosphor-icons/react/dist/ssr";
import type { Metadata } from "next";
import Link from "next/link";

import { CopyButton } from "@/components/copy-button";
import { AnnosWordmark } from "@/components/wordmark";
import { MCP_URL_DISPLAY } from "@/lib/mcp";
import enMessages from "../../../messages/en.json";

/**
 * One day on Annos — the logged-out front page (rewritten under / by the
 * proxy; also reachable at /hello directly).
 *
 * THESIS: the landing is one specimen day at poster scale, refusing both the
 * hero-features-CTA template and the quiet letter. STORY: the visitor scrolls
 * a Tuesday from breakfast to the closing rule — each beat pairs a claim with
 * the sheet fragment that proves it — and leaves knowing what Annos is, that
 * it's honest about data, and how to join. FIRST VIEWPORT: letterhead with
 * the specimen day, a poster headline, the chat line, and breakfast stamping
 * onto the sheet row by row, CTA in reach. FORM: specimen-day timeline —
 * grounded candidate 4, seed eac670ca (re-roll after the letter, seed
 * 06377c6a, was rejected). The timeline spine is a hairline; times are mono;
 * every number sits in the price column; ochre appears only on actions. The
 * stamp keeps its one meaning — a record landing — timed in the hero,
 * scroll-scrubbed in the beats.
 */

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

// The landing is English-only by decision: a marketing surface where a
// per-visitor translation read worse than one clean English page. The copy
// lives in en.json's `landing` and is read directly here, bypassing the locale
// machinery entirely, so every visitor gets the same English page while the
// rest of the app stays trilingual. en.json is the only file carrying
// `landing`; the two link-bearing lines are inlined below as JSX.
const COPY = enMessages.landing;

export function generateMetadata(): Metadata {
  return { title: COPY.metaTitle, description: COPY.metaDescription };
}

/** One dish line: name (with optional provenance tag), portion in faded
 * mono, kcal in the fixed right-aligned price column. */
function Dish({
  name,
  tag,
  portion,
  kcal,
  className,
  style,
}: {
  name: string;
  tag?: string;
  portion: string;
  kcal: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div className={`flex items-baseline gap-2 py-1.5 ${className ?? ""}`} style={style}>
      <span className="truncate">{name}</span>
      {tag && <span className="font-mono text-xs text-muted-foreground">({tag})</span>}
      <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground">{portion}</span>
      <span className="tnum w-12 shrink-0 text-right font-mono text-sm">{kcal}</span>
    </div>
  );
}

/** A meal entry fragment: header line, dishes, 2px rule closing on the
 * total in the price column. */
function Entry({
  meal,
  time,
  tagline,
  totalLabel,
  totalValue,
  children,
  stampOnView,
}: {
  meal: string;
  time: string;
  tagline?: string;
  totalLabel: string;
  totalValue: string;
  children: React.ReactNode;
  stampOnView?: boolean;
}) {
  return (
    <div className={`border-y border-border py-4 ${stampOnView ? "stamp-on-view" : ""}`}>
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-bold uppercase tracking-wider">{meal}</span>
        <span className="font-mono text-xs text-muted-foreground">
          {time}
          {tagline ? <> · ({tagline})</> : null}
        </span>
      </div>
      <div className="pt-2">{children}</div>
      <div className="mt-3 flex items-baseline justify-between border-t-2 border-foreground pt-3">
        <span className="text-sm font-bold">{totalLabel}</span>
        <span className="tnum font-mono text-sm">{totalValue}</span>
      </div>
    </div>
  );
}

/** A totals measure: hairline scale, 3px ink stroke over the fraction. */
function Measure({ fraction }: { fraction: number }) {
  return (
    <div aria-hidden className="relative mt-2 h-[3px]">
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
      <div
        className="absolute inset-y-0 left-0 bg-foreground"
        style={{ width: `${Math.min(fraction * 100, 100)}%` }}
      />
    </div>
  );
}

/** A timeline beat: mono time pinned to the spine, claim, proof fragment. */
function Beat({
  time,
  claim,
  body,
  children,
}: {
  time: string;
  claim: string;
  body: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="relative border-l border-border pb-20 pl-6 sm:pl-10 lg:pb-28">
      <span className="absolute -left-px top-0 -translate-x-1/2 bg-background py-1 font-mono text-xs text-muted-foreground">
        {time}
      </span>
      <div className="pt-8 lg:grid lg:grid-cols-2 lg:items-center lg:gap-x-20 lg:pt-10">
        <div>
          <h2 className="max-w-xl text-3xl font-bold tracking-tight text-balance lg:text-4xl">
            {claim}
          </h2>
          <p className="mt-4 max-w-lg text-sm leading-relaxed text-muted-foreground lg:text-base">
            {body}
          </p>
        </div>
        <div className="mt-8 lg:mt-0">{children}</div>
      </div>
    </section>
  );
}

export default function HelloPage() {
  const t = (key: keyof typeof COPY) => COPY[key];

  const github = (chunks: React.ReactNode) => (
    <a
      href="https://github.com/panuhen/annos"
      rel="noopener"
      className={`underline underline-offset-2 hover:text-foreground ${FOCUS}`}
    >
      {chunks}
    </a>
  );

  const totalRow = (label: string, value: string) => (
    <div className="flex items-baseline justify-between">
      <span className="text-sm font-bold">{label}</span>
      <span className="tnum font-mono text-sm">{value}</span>
    </div>
  );

  return (
    <main className="mx-auto max-w-6xl px-5 py-8 lg:px-8 lg:py-12">
      {/* Letterhead: the wordmark and the specimen day. */}
      <header className="flex items-baseline justify-between pb-4">
        <AnnosWordmark className="text-4xl" />
        <span className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
          {t("specimenDay")} · 08:12–21:00
        </span>
      </header>
      <div className="border-t-2 border-foreground" />

      {/* 08:12 — the hero: say it, and it's on the sheet. The first beat of
          the spine, so the timeline starts where the day does. */}
      <section className="relative mt-8 border-l border-border pt-6 pb-20 pl-6 sm:pl-10 lg:mt-14 lg:grid lg:grid-cols-[1.1fr_1fr] lg:items-center lg:gap-x-20 lg:pt-12 lg:pb-28">
        <span className="absolute -left-px top-0 -translate-x-1/2 bg-background py-1 font-mono text-xs text-muted-foreground">
          08:12
        </span>
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-5xl lg:text-6xl">
            {t("heroTitle")}
          </h1>
          {/* No subtitle — the specimen demo carries the hero; the title goes
              straight to the action. A contained button (not the close's
              full-width row) with sign-in beside it, so the two CTAs read as
              deliberately different moments. */}
          <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-center lg:mt-10">
            <Link
              href="/sign-up"
              className={`flex min-h-12 w-full items-center justify-center bg-primary px-8 text-base font-bold text-primary-foreground hover:opacity-90 sm:w-auto ${FOCUS}`}
            >
              {t("cta")}
            </Link>
            <p className="text-sm text-muted-foreground">
              {t("haveAccount")}{" "}
              <Link href="/sign-in" className={`font-bold text-primary hover:opacity-90 ${FOCUS}`}>
                {t("signIn")}
              </Link>
            </p>
          </div>
        </div>

        <figure className="mt-8 lg:mt-0">
          <blockquote className="text-base leading-relaxed lg:text-lg">
            {t("specimenQuote")}
          </blockquote>
          <div className="mt-5 border-y border-border py-4">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold uppercase tracking-wider">
                {t("specimenMeal")}
              </span>
              <span className="font-mono text-xs text-muted-foreground">
                08:12 · ({t("specimenExample")})
              </span>
            </div>
            <div className="pt-2">
              <Dish
                name={t("specimenEgg")}
                portion={t("specimenEggPortion")}
                kcal={171}
                className="stamp-in"
                style={{ animationDelay: "400ms" }}
              />
              <Dish
                name={t("specimenBread")}
                portion="35 g"
                kcal={86}
                className="stamp-in"
                style={{ animationDelay: "700ms" }}
              />
              <Dish
                name={t("specimenButter")}
                portion="5 g"
                kcal={36}
                className="stamp-in"
                style={{ animationDelay: "1000ms" }}
              />
            </div>
            <div
              className="stamp-in mt-3 flex items-baseline justify-between border-t-2 border-foreground pt-3"
              style={{ animationDelay: "1300ms" }}
            >
              <span className="text-sm font-bold">{t("specimenTotal")}</span>
              <span className="tnum font-mono text-sm">293 kcal</span>
            </div>
          </div>
        </figure>
      </section>

      {/* 11:45 — honest data. */}
      <Beat time="11:45" claim={t("lunchClaim")} body={t("lunchBody")}>
        <Entry
          meal={t("specimenLunch")}
          time="11:45"
          tagline={t("specimenExample")}
          totalLabel={t("specimenTotal")}
          totalValue="812 kcal"
          stampOnView
        >
          <Dish name={t("specimenSoup")} portion="300 g" kcal={246} />
          <Dish name={t("specimenBread")} portion="35 g" kcal={86} />
          <Dish name={t("specimenWok")} tag="AI" portion="350 g" kcal={480} />
        </Entry>
      </Beat>

      {/* 16:30 — exercise, estimated and kept out of the food maths. */}
      <Beat time="16:30" claim={t("exerciseClaim")} body={t("exerciseBody")}>
        <div className="stamp-on-view border-y border-border py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-xs font-bold uppercase tracking-wider">
              {t("specimenExercise")}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              16:30 · ({t("specimenExample")})
            </span>
          </div>
          <div className="flex items-baseline gap-2 pt-2">
            <span className="truncate">{t("specimenRun")}</span>
            <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground">32 min</span>
            {/* ≈ marks the estimate, the way (AI) marks a guessed dish; it never
                joins the day's energy total. */}
            <span className="tnum shrink-0 text-right font-mono text-sm">≈ 390 kcal</span>
          </div>
        </div>
      </Beat>

      {/* 17:30 — weight and goal. */}
      <Beat time="17:30" claim={t("weightClaim")} body={t("weightBody")}>
        <div className="stamp-on-view border-y border-border py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-xs font-bold uppercase tracking-wider">
              {t("specimenWeight")}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              17:30 · ({t("specimenExample")})
            </span>
          </div>
          <div className="flex items-baseline justify-between pt-3">
            <span className="tnum font-mono text-2xl">{t("specimenWeightValue")}</span>
            <span className="tnum font-mono text-sm text-muted-foreground">{t("specimenRate")}</span>
          </div>
          <div className="mt-3 border-t-2 border-foreground pt-3">
            <div className="flex items-baseline justify-between">
              <span className="tnum font-mono text-sm">2 100 kcal</span>
              <span className="tnum font-mono text-xs text-muted-foreground">
                {t("specimenTargetProtein")}
              </span>
            </div>
          </div>
        </div>
      </Beat>

      {/* 21:00 — the day ruled off. */}
      <Beat
        time="21:00"
        claim={t("totalsClaim")}
        body={
          <>
            Annos adds up your day and hands you the numbers. No streaks, no badges, no pressure.
            Any coaching is yours to ask your AI for. It&apos;s free, {github("open-source")}, and
            shows no ads.
          </>
        }
      >
        {/* The totals foot stays motionless — arithmetic is not a record
            landing. Labeled like every other specimen fragment. */}
        <div>
          <div className="flex justify-end pb-1">
            <span className="font-mono text-xs text-muted-foreground">
              ({t("specimenExample")})
            </span>
          </div>
          <div className="border-t-2 border-foreground pt-3">
          <div className="pb-1">
            {totalRow(t("totalsEnergy"), "1 830 / 2 100 kcal")}
            <Measure fraction={1830 / 2100} />
          </div>
          <div className="pt-3 pb-1">
            {totalRow(t("totalsProtein"), "142 / 160 g")}
            <Measure fraction={142 / 160} />
          </div>
          <div className="flex items-baseline justify-between pt-4">
            <span className="text-sm text-muted-foreground">{t("totalsRemaining")}</span>
            <span className="tnum font-mono text-sm">270 kcal · 18 g</span>
          </div>
          </div>
        </div>
      </Beat>

      {/* Privacy is a principle, not a footnote: its own ruled aside. */}
      <aside className="mx-auto max-w-2xl border-t-2 border-foreground pt-5 pb-16 lg:pb-24">
        <h2 className="font-mono text-xs font-normal uppercase tracking-wider text-muted-foreground">
          {t("privacyLabel")}
        </h2>
        <p className="mt-3 text-base leading-relaxed lg:text-lg">
          What you track here is health data, so Annos is built to know as little about you as it
          can. Inside the app you&apos;re a generated nickname, your email never touches what you
          log, and nothing is tracked or sold.{" "}
          <Link
            href="/privacy"
            className={`underline underline-offset-2 hover:text-muted-foreground ${FOCUS}`}
          >
            Read how
          </Link>
          .
        </p>
      </aside>

      {/* The close: one big action, then the two how-tos. */}
      <section className="pt-4 lg:pt-8">
        <h2 className="text-4xl font-bold tracking-tight sm:text-5xl">{t("closeTitle")}</h2>
        {/* Both doors, co-equal and full-width. Sign-in leads here (the close
            is where a returning reader looks for it), the secondary in the
            system's outline block; create-account keeps the ochre and the
            visual weight, since acquisition is still the page's job. */}
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link
            href="/sign-in"
            className={`flex min-h-14 flex-1 items-center justify-center border border-input text-base font-bold hover:bg-secondary ${FOCUS}`}
          >
            {t("signIn")}
          </Link>
          <Link
            href="/sign-up"
            className={`flex min-h-14 flex-1 items-center justify-center bg-primary text-base font-bold text-primary-foreground hover:opacity-90 ${FOCUS}`}
          >
            {t("cta")}
          </Link>
        </div>
      </section>

      <div className="mt-16 gap-x-20 lg:grid lg:grid-cols-2">
        <section>
          <h3 className="flex items-center gap-2 border-b-2 border-foreground pb-2 font-mono text-xs uppercase tracking-wider">
            <Plugs size={16} aria-hidden />
            {t("connectTitle")}
          </h3>
          <ol className="list-none">
            <li className="flex gap-4 border-b border-border py-4">
              <span className="font-mono text-sm text-muted-foreground">1</span>
              <span className="text-sm leading-relaxed">{t("connect1")}</span>
            </li>
            <li className="flex gap-4 border-b border-border py-4">
              <span className="font-mono text-sm text-muted-foreground">2</span>
              <span className="min-w-0 text-sm leading-relaxed">
                {t("connect2")}
                <span className="mt-2 flex items-stretch gap-2">
                  <code className="tnum flex min-w-0 flex-1 items-center truncate border border-border px-3 font-mono text-xs">
                    {MCP_URL_DISPLAY}
                  </code>
                  <CopyButton
                    value={MCP_URL_DISPLAY}
                    label={t("copyAddress")}
                    idleText={t("copy")}
                    copiedText={t("copied")}
                  />
                </span>
              </span>
            </li>
            <li className="flex gap-4 border-b border-border py-4">
              <span className="font-mono text-sm text-muted-foreground">3</span>
              <span className="text-sm leading-relaxed">{t("connect3")}</span>
            </li>
          </ol>
          <p className="pt-3 text-xs leading-relaxed text-muted-foreground">{t("connectAny")}</p>
        </section>

        <section className="mt-12 lg:mt-0">
          <h3 className="flex items-center gap-2 border-b-2 border-foreground pb-2 font-mono text-xs uppercase tracking-wider">
            <DeviceMobile size={16} aria-hidden />
            {t("installTitle")}
          </h3>
          <p className="border-b border-border py-4 text-sm leading-relaxed text-muted-foreground">
            {t("installIntro")}
          </p>
          <div className="flex items-baseline gap-4 border-b border-border py-4">
            <span className="w-16 shrink-0 text-sm font-bold">{t("installIos")}</span>
            <span className="text-sm leading-relaxed text-muted-foreground">
              {t("installIosSteps")}
            </span>
          </div>
          <div className="flex items-baseline gap-4 border-b border-border py-4">
            <span className="w-16 shrink-0 text-sm font-bold">{t("installAndroid")}</span>
            <span className="text-sm leading-relaxed text-muted-foreground">
              {t("installAndroidSteps")}
            </span>
          </div>
        </section>
      </div>

      {/* The foot, same as every pre-auth sheet. */}
      <footer className="mt-20 flex justify-center gap-4 border-t border-border pt-5 font-mono text-xs uppercase tracking-wide text-muted-foreground">
        <Link href="/privacy" className={`hover:text-foreground ${FOCUS}`}>
          Privacy
        </Link>
        <Link href="/terms" className={`hover:text-foreground ${FOCUS}`}>
          Terms
        </Link>
      </footer>
    </main>
  );
}

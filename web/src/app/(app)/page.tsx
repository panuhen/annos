"use client";

import {
  CaretLeft,
  CaretRight,
  PersonSimple,
  PersonSimpleRun,
  Plus,
} from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { Skeleton } from "@/components/ui/skeleton";
import { AnnosWordmark } from "@/components/wordmark";
import { MacroLine, MacrosToggle } from "@/components/macros";
import { api } from "@/lib/api/client";
import { $api } from "@/lib/api/hooks";
import {
  addDays,
  clockTime,
  grams,
  isoWeek,
  kcal,
  localeFor,
  rateFigure,
  sheetDate,
  signed,
  sourceCode,
  weekday,
} from "@/lib/format";
import { useProfile } from "@/lib/profile";
import { cn } from "@/lib/utils";

export default function DayPage() {
  return (
    <Suspense fallback={<SheetSkeleton />}>
      <DaySheet />
    </Suspense>
  );
}

function SheetSkeleton() {
  return (
    <div className="pt-6">
      <Skeleton className="mb-4 h-5 w-32" />
      <Skeleton className="mb-6 h-9 w-56" />
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

function DaySheet() {
  const profile = useProfile();
  const params = useSearchParams();
  const t = useTranslations("day");
  const tMeals = useTranslations("meals");
  const tKinds = useTranslations("kinds");
  const tExercise = useTranslations("exerciseForm");
  const kindLabel = (kind: string) =>
    ["deficit", "maintenance", "surplus"].includes(kind) ? tKinds(kind) : kind;
  const date = params.get("date") ?? undefined;
  const stamped = params.get("stamp");
  // Chrome (dates, weekday, labels) follows the app language; only food
  // names follow profile.language, and those arrive pre-resolved.
  const locale = localeFor(useLocale());

  const summary = $api.useQuery("get", "/api/summary/daily", {
    params: { query: date ? { date } : {} },
  });
  const queryClient = useQueryClient();
  const [marking, setMarking] = useState(false);

  if (summary.isPending) return <SheetSkeleton />;
  if (summary.error || !summary.data) {
    return (
      <div className="pt-10">
        <h1 className="text-lg font-bold">{t("loadFailTitle")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("loadFailBody")}</p>
      </div>
    );
  }

  const day = summary.data;
  const today = day.server_time.local_date;
  const isToday = day.date === today;

  // The mark is the user's say and wins over any derivation, in both
  // directions; it applies to the sheet's own date, a day the user is
  // looking at and therefore stating. Marking the already-active type is
  // not a no-op: it turns an assumed rest day into a stated one.
  async function markDay(dayType: "training" | "rest") {
    setMarking(true);
    try {
      const { error } = await api.PUT("/api/days/type", {
        body: { day_type: dayType, date: day.date },
      });
      if (error) throw error;
      await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
    } catch {
      toast.error(t("markFailed"));
    } finally {
      setMarking(false);
    }
  }

  return (
    <>
      <header className="flex items-end justify-between pt-5 pb-2">
        <AnnosWordmark className="text-2xl" />
        <span className="pb-1 font-mono text-xs text-muted-foreground uppercase">
          {t("week")} {isoWeek(day.date)}
        </span>
      </header>

      <div className="border-t-2 border-foreground" />

      {/* The day line: the sheet is always one day, paged like the menu week */}
      <div className="flex items-center justify-between py-3">
        <Link
          href={`/?date=${addDays(day.date, -1)}`}
          aria-label={t("prevDay")}
          className="-ml-2 flex size-11 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <CaretLeft aria-hidden className="size-5" />
        </Link>
        <div className="text-center">
          <h1
            className={cn(
              "text-2xl font-bold uppercase tracking-tight text-balance",
              isToday && "text-primary",
            )}
          >
            {weekday(day.date, locale)}
          </h1>
          <p className="font-mono text-sm text-muted-foreground">
            {sheetDate(day.date, locale)}
            {!isToday && (
              <>
                {" · "}
                <Link href="/" className="text-primary underline underline-offset-2">
                  {t("today")}
                </Link>
              </>
            )}
          </p>
        </div>
        <Link
          href={`/?date=${addDays(day.date, 1)}`}
          aria-label={t("nextDay")}
          className="-mr-2 flex size-11 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <CaretRight aria-hidden className="size-5" />
        </Link>
      </div>

      {day.meals.length > 0 && <MacrosToggle />}

      {day.meals.length === 0 ? (
        <div className="border-t border-border py-10 text-center">
          <p className="font-medium">{isToday ? t("emptyTitleToday") : t("emptyTitlePast")}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {isToday ? t("emptyBodyToday") : t("emptyBodyPast")}
          </p>
        </div>
      ) : (
        <ul>
          {day.meals.map((meal) => (
            <li
              key={meal.log_id}
              className={cn(
                "border-t border-border",
                String(meal.log_id) === stamped && "stamp-in",
              )}
            >
              <Link
                href={`/log/${meal.log_id}?date=${day.date}`}
                className="block py-3 hover:bg-secondary focus-visible:bg-secondary"
              >
                <div className="flex items-baseline gap-3">
                  <span className="min-w-0 flex-1 text-xs font-bold uppercase tracking-wider">
                    {meal.meal ? tMeals(meal.meal) : t("meal")}
                    {meal.planned && (
                      <span className="ml-1.5 font-mono font-normal normal-case text-muted-foreground">
                        {t("planned")}
                      </span>
                    )}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {clockTime(meal.ts, locale, profile.timezone)}
                  </span>
                  {/* Heads the price column: the bare figures below are kcal */}
                  <span className="w-12 text-right font-mono text-xs text-muted-foreground">
                    {t("kcalUnit")}
                  </span>
                </div>
                <ul className="mt-1.5 space-y-1">
                  {meal.items.map((item, i) => (
                    <li key={i}>
                      <div className="flex items-baseline gap-3">
                        <span className={cn("min-w-0 flex-1 truncate", meal.planned && "italic")}>
                          {item.name ?? `#${item.food_id}`}
                          {sourceCode(item.source) && (
                            <span className="ml-1.5 font-mono text-xs text-muted-foreground">
                              ({sourceCode(item.source)})
                            </span>
                          )}
                        </span>
                        <span
                          className="font-mono text-xs text-muted-foreground tnum"
                          title={item.estimated ? t("estimatedPortion") : undefined}
                        >
                          {item.estimated && (
                            <>
                              <span className="sr-only">{t("estimatedPortion")}: </span>
                              {/* Tilde, not ≈: U+2248 isn't in Fragment Mono and
                                  would fall back off the price column. */}
                              <span aria-hidden="true">~</span>
                            </>
                          )}
                          {grams(item.grams)}&#8239;g
                        </span>
                        <span className="tnum w-12 text-right font-mono text-sm">
                          {kcal(item.kcal)}
                        </span>
                      </div>
                      <MacroLine
                        protein={item.protein_g}
                        carbs={item.carbs_g}
                        fat={item.fat_g}
                        fiber={item.fiber_g}
                      />
                    </li>
                  ))}
                </ul>
                {meal.notes && (
                  <p className="mt-1 text-xs text-muted-foreground italic">{meal.notes}</p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}

      {/* The day's training, ruled off from the meals like a menu's side
       * column. Only what happened is printed — the bar below is where you
       * act, so an empty day carries no empty section. */}
      {day.exercise.length > 0 && (
        <div className="mt-2 border-t border-border pt-2">
          <span className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
            {t("exercise")}
          </span>
          <ul className="-mt-1">
            {day.exercise.map((session) => (
              <li key={session.log_id} className={cn(`e${session.log_id}` === stamped && "stamp-in")}>
                <Link
                  href={`/exercise/${session.log_id}?date=${day.date}`}
                  className="flex items-baseline gap-3 py-2 hover:bg-secondary focus-visible:bg-secondary"
                >
                  <span
                    className={cn("min-w-0 flex-1 truncate", session.planned && "italic")}
                  >
                    {session.activity?.name ?? tExercise(session.kind)}
                    {session.planned && (
                      <span className="ml-1.5 font-mono text-xs not-italic text-muted-foreground">
                        {t("planned")}
                      </span>
                    )}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground tnum">
                    {session.sets.length > 0 &&
                      t("setsCount", { count: session.sets.length }) + " · "}
                    {session.duration_min != null && `${grams(session.duration_min)} min`}
                  </span>
                  <span className="tnum w-12 text-right font-mono text-sm">
                    {session.kcal_estimate != null ? kcal(session.kcal_estimate) : "–"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* The foot of the sheet: the day ruled off against its target */}
      <div className="mt-2 border-t-2 border-foreground pt-3">
        <TotalRow
          label={t("energy")}
          value={Math.round(day.totals.kcal)}
          target={day.target?.kcal}
          unit={t("kcalUnit")}
        />
        <TotalRow
          label={t("protein")}
          value={Math.round(day.totals.protein_g)}
          target={day.target?.protein_g}
          unit="g"
        />
        <p className="mt-1.5 font-mono text-xs text-muted-foreground tnum">
          {t("macroLine", {
            carbs: Math.round(day.totals.carbs_g),
            fat: Math.round(day.totals.fat_g),
            fiber: Math.round(day.totals.fiber_g),
          })}
        </p>

        {day.remaining ? (
          <p className="mt-3 text-sm">
            <span className="font-bold">{t("remaining")}</span>{" "}
            <span className="tnum font-mono">{signed(day.remaining.kcal)}</span> {t("kcalUnit")} ·{" "}
            <span className="tnum font-mono">{signed(day.remaining.protein_g)}</span>{" "}
            {t("gProtein")}
          </p>
        ) : null}

        <p className="mt-1 text-xs text-muted-foreground">
          {day.target ? (
            <>
              {day.day_type === "rest" ? t("restTarget") : t("trainingTarget")}
              {/* An unmarked day is an assumption, and the sheet says so —
               * the same honesty as the provenance parentheticals. */}
              {day.day_type_source === "default" && (
                <span className="font-mono"> ({t("assumed")})</span>
              )}
              {" · "}
              {kindLabel(day.target.kind)}
              {day.target.rate_kg_per_week != null && (
                <>
                  {" · "}
                  {rateFigure(day.target.rate_kg_per_week, locale)} {t("kgPerWeek")}
                </>
              )}
            </>
          ) : (
            <>
              {t("noPhase")}{" "}
              <Link href="/goal" className="text-primary underline underline-offset-2">
                {t("setOne")}
              </Link>
            </>
          )}
        </p>
        {day.target && (
          <div role="group" aria-label={t("dayType")} className="mt-1 flex items-center gap-4">
            {(["rest", "training"] as const).map((type) => {
              const active = day.day_type === type;
              const Figure = type === "training" ? PersonSimpleRun : PersonSimple;
              return (
                <button
                  key={type}
                  type="button"
                  disabled={marking}
                  aria-pressed={active}
                  onClick={() => markDay(type)}
                  className={cn(
                    "flex min-h-11 items-center font-mono text-xs uppercase tracking-wider disabled:cursor-not-allowed disabled:opacity-40",
                    active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "flex items-center gap-1 border-b-2 pb-px",
                      active ? "border-foreground" : "border-transparent",
                    )}
                  >
                    <Figure aria-hidden weight={active ? "bold" : "regular"} className="size-4" />
                    {t(type)}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* The bar carries the day's two log actions: meals keep the wide honey
       * press (they happen five times a day), exercise stands beside it as an
       * inked square — the sheet's own training glyph, not a new icon. */}
      <div className="sticky bottom-[4.5rem] lg:bottom-4 mt-6 flex gap-2 bg-background pb-1">
        <Link
          href={isToday ? "/log" : `/log?date=${day.date}`}
          className="flex min-h-12 flex-1 items-center justify-center gap-2 bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Plus aria-hidden weight="bold" className="size-5" />
          {t("logMeal")}
        </Link>
        <Link
          href={isToday ? "/exercise" : `/exercise?date=${day.date}`}
          aria-label={t("logExercise")}
          title={t("logExercise")}
          className="flex min-h-12 w-12 items-center justify-center border border-foreground text-foreground hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <PersonSimpleRun aria-hidden weight="bold" className="size-5" />
        </Link>
      </div>
    </>
  );
}

function TotalRow({
  label,
  value,
  target,
  unit,
}: {
  label: string;
  value: number;
  target: number | undefined;
  unit: string;
}) {
  return (
    <div className="mb-1">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-bold">{label}</span>
        <span className="tnum font-mono text-sm">
          {value}
          {target != null && <span className="text-muted-foreground"> / {target}</span>} {unit}
        </span>
      </div>
      {target != null && target > 0 && <Measure value={value} target={target} />}
    </div>
  );
}

/** Progress as the sheet already draws everything: rule weight. The hairline
 * is the day's full measure, the ink stroke is what's eaten, and past the
 * target the tick shows where the target sat. Decorative to a screen reader —
 * the figures above carry the data — and deliberately monochrome: honey is
 * reserved for actions and today, and this is neither. */
function Measure({ value, target }: { value: number; target: number }) {
  const scale = Math.max(value, target);
  const eaten = Math.max(0, Math.min(1, value / scale));
  const tick = target / scale;
  return (
    <div aria-hidden className="relative mt-1 mb-1.5 h-[3px]">
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
      <div
        className="absolute left-0 top-1/2 h-[3px] -translate-y-1/2 bg-foreground"
        style={{ width: `${eaten * 100}%` }}
      />
      {value > target && (
        <div
          className="absolute top-1/2 h-[7px] w-[2px] -translate-y-1/2 -translate-x-1/2 bg-background"
          style={{ left: `${tick * 100}%` }}
        />
      )}
    </div>
  );
}

"use client";

import { CaretLeft, CaretRight, Plus } from "@phosphor-icons/react";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { AnnosMark } from "@/components/logo";
import { $api } from "@/lib/api/hooks";
import {
  addDays,
  clockTime,
  grams,
  isoWeek,
  kcal,
  localeFor,
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

  return (
    <>
      <header className="flex items-end justify-between pt-5 pb-2">
        <span className="flex items-center gap-2">
          <AnnosMark className="h-8 w-auto" />
          <span className="text-xl font-bold tracking-tight">Annos</span>
        </span>
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
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-xs font-bold uppercase tracking-wider">
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
                </div>
                <ul className="mt-1.5 space-y-1">
                  {meal.items.map((item, i) => (
                    <li key={i} className="flex items-baseline gap-3">
                      <span className={cn("min-w-0 flex-1 truncate", meal.planned && "italic")}>
                        {item.name ?? `#${item.food_id}`}
                        {sourceCode(item.source) && (
                          <span className="ml-1.5 font-mono text-xs text-muted-foreground">
                            ({sourceCode(item.source)})
                          </span>
                        )}
                      </span>
                      <span className="font-mono text-xs text-muted-foreground tnum">
                        {grams(item.grams)}&#8239;g
                      </span>
                      <span className="tnum w-12 text-right font-mono text-sm">
                        {kcal(item.kcal)}
                      </span>
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
              {day.day_type === "rest" ? t("restTarget") : t("trainingTarget")} ·{" "}
              {kindLabel(day.target.kind)}
              {day.target.rate_kg_per_week != null && (
                <>
                  {" · "}
                  {day.target.rate_kg_per_week} {t("kgPerWeek")}
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
      </div>

      <div className="sticky bottom-[4.5rem] lg:bottom-4 mt-6 bg-background pb-1">
        <Link
          href={isToday ? "/log" : `/log?date=${day.date}`}
          className="flex min-h-12 w-full items-center justify-center gap-2 bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Plus aria-hidden weight="bold" className="size-5" />
          {t("logMeal")}
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
    <div className="flex items-baseline justify-between">
      <span className="text-sm font-bold">{label}</span>
      <span className="tnum font-mono text-sm">
        {value}
        {target != null && <span className="text-muted-foreground"> / {target}</span>} {unit}
      </span>
    </div>
  );
}

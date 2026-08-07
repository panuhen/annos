"use client";

import { CaretDown, CaretRight } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { WeightChart } from "@/components/weight-chart";
import { api } from "@/lib/api/client";
import { $api } from "@/lib/api/hooks";
import { isoWeek, localeFor, rateFigure, sheetDate, shortDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The stats sheet: what the logging was for. The morning weigh-in stays the
 * first thing on the page — logging the number and watching the trend answer
 * is the daily loop — then the sheet reads downward in value order: the
 * trend against the phase's rate, the measured TDEE ruled off like a total,
 * the weekly ledger, and the training column. Everything below the form is
 * arithmetic the server already did; this page only prints it. */

const WINDOWS = [
  { days: 28, key: "win4" },
  { days: 84, key: "win12" },
  { days: 365, key: "winAll" },
] as const;

const LEDGER_WEEKS = 8;

export default function StatsPage() {
  const queryClient = useQueryClient();
  const t = useTranslations("stats");
  const tWeight = useTranslations("weight");
  const locale = localeFor(useLocale());

  const [windowDays, setWindowDays] = useState<number>(28);
  const weight = $api.useQuery("get", "/api/logs/weight", {
    params: { query: { days: windowDays } },
  });
  const review = $api.useQuery("get", "/api/stats/review", {
    params: { query: { weeks: LEDGER_WEEKS } },
  });
  const training = $api.useQuery("get", "/api/stats/training", {
    params: { query: { weeks: LEDGER_WEEKS } },
  });

  async function logged() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["get", "/api/logs/weight"] }),
      queryClient.invalidateQueries({ queryKey: ["get", "/api/stats/review"] }),
      queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] }),
    ]);
  }

  const points = weight.data?.points ?? [];
  const weighed = points.filter((p) => p.weight_kg != null);
  const rate = weight.data?.rate_kg_per_week;
  const targetRate = review.data?.active_phase?.rate_target_kg_per_week;
  const nf1 = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });

  return (
    <>
      <header className="border-b-2 border-foreground pt-5 pb-2">
        <h1 className="text-lg font-bold">{t("title")}</h1>
      </header>

      {/* PAINO — the daily action first, the answer right under it */}
      <section className="mt-4">
        <h2 className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
          {tWeight("title")}
        </h2>

        <WeightForm onLogged={logged} />

        <div className="mt-5 flex items-center justify-end" role="group" aria-label={t("windowAria")}>
          <div className="flex gap-4">
            {WINDOWS.map(({ days, key }) => {
              const active = windowDays === days;
              return (
                <button
                  key={days}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setWindowDays(days)}
                  className={cn(
                    "flex min-h-9 items-center font-mono text-xs uppercase tracking-wider",
                    active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "border-b-2 pb-px",
                      active ? "border-foreground" : "border-transparent",
                    )}
                  >
                    {t(key)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {weight.isPending ? (
          <Skeleton className="mt-2 h-40 w-full" />
        ) : weighed.length === 0 ? (
          <div className="mt-2 border-t border-border py-8 text-center">
            <p className="text-sm text-muted-foreground">{t("chartEmpty")}</p>
          </div>
        ) : (
          <>
            <WeightChart
              points={points}
              smoothed={weight.data?.smoothed ?? []}
              locale={locale}
              ariaLabel={t("chartAria", {
                count: weighed.length,
                last: nf1.format(weighed[weighed.length - 1].weight_kg as number),
              })}
            />
            <p className="mt-1 font-mono text-xs text-muted-foreground tnum">
              {rate != null ? (
                <>
                  {t("trend")} {rateFigure(rate, locale)} {t("kgPerWeek")}
                  {targetRate != null &&
                    ` · ${t("trendTarget", { rate: rateFigure(targetRate, locale) })}`}
                </>
              ) : (
                t("trendPending")
              )}
            </p>
          </>
        )}
      </section>

      {/* TDEE — ruled off heavy, the sheet's total */}
      <section className="mt-6 border-t-2 border-foreground pt-3">
        {review.isPending ? (
          <Skeleton className="h-14 w-full" />
        ) : review.data ? (
          <TdeeBlock tdee={review.data.tdee} locale={locale} />
        ) : null}
      </section>

      {/* VIIKOT — the ledger */}
      <section className="mt-6">
        <h2 className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
          {t("weeks")}
        </h2>
        {review.isPending ? (
          <div className="mt-2 space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : (
          <WeeksLedger weeks={review.data?.weeks ?? []} locale={locale} />
        )}
      </section>

      {/* TREENI — printed only when the window holds training */}
      {training.data && training.data.weeks.some((w) => w.sessions > 0) && (
        <TrainingSection data={training.data} locale={locale} />
      )}

      <div className="h-8" />
    </>
  );
}

/** The old weight page, condensed to its daily gesture: two numbers and a
 * button; the date and notes tuck behind a disclosure for the off-day case. */
function WeightForm({ onLogged }: { onLogged: () => Promise<void> }) {
  const t = useTranslations("weight");
  const tStats = useTranslations("stats");
  const locale = localeFor(useLocale());

  const [weightKg, setWeightKg] = useState("");
  const [waist, setWaist] = useState("");
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState(""); // empty = today, server-defined
  const [moreOpen, setMoreOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [logged, setLogged] = useState<{ date: string; weight_kg: number | null } | null>(null);

  const valid = weightKg.trim() !== "" || waist.trim() !== "" || notes.trim() !== "";

  async function submit() {
    setSubmitting(true);
    try {
      const { data, error } = await api.POST("/api/logs/weight", {
        body: {
          weight_kg: weightKg.trim() === "" ? null : parseFloat(weightKg),
          waist_cm: waist.trim() === "" ? null : parseFloat(waist),
          notes: notes.trim() === "" ? null : notes.trim(),
          date: date === "" ? null : date,
        },
      });
      if (error || !data) throw error ?? new Error("no response");
      setLogged({ date: data.date, weight_kg: data.weight_kg });
      setWeightKg("");
      setWaist("");
      setNotes("");
      setDate("");
      await onLogged();
    } catch (err) {
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : undefined;
      toast.error(t("failed"), { description: detail });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      {logged && (
        <p className="stamp-in mt-3 border border-border px-3 py-2 text-sm" role="status">
          {logged.weight_kg != null
            ? t("loggedWith", { weight: logged.weight_kg, date: sheetDate(logged.date, locale) })
            : t("loggedPlain", { date: sheetDate(logged.date, locale) })}{" "}
          {t("replaces")}
        </p>
      )}

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="weight-kg" className="mb-1.5 font-mono text-xs uppercase">
            {t("weightKg")}
          </Label>
          <Input
            id="weight-kg"
            inputMode="decimal"
            value={weightKg}
            onChange={(e) => setWeightKg(e.target.value)}
            className="tnum h-12 text-right font-mono text-base"
          />
        </div>
        <div>
          <Label htmlFor="waist-cm" className="mb-1.5 font-mono text-xs uppercase">
            {t("waistCm")}
          </Label>
          <Input
            id="waist-cm"
            inputMode="decimal"
            value={waist}
            onChange={(e) => setWaist(e.target.value)}
            placeholder={t("optional")}
            className="tnum h-12 text-right font-mono text-base"
          />
        </div>
      </div>

      <button
        type="button"
        aria-expanded={moreOpen}
        onClick={() => setMoreOpen(!moreOpen)}
        className="mt-2 flex min-h-11 items-center gap-1.5 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
      >
        {moreOpen ? (
          <CaretDown aria-hidden className="size-3.5" />
        ) : (
          <CaretRight aria-hidden className="size-3.5" />
        )}
        {tStats("moreFields")}
      </button>

      {moreOpen && (
        <div className="space-y-3 pb-1">
          <div>
            <Label htmlFor="weight-date" className="mb-1.5 font-mono text-xs uppercase">
              {t("day")}
            </Label>
            <Input
              id="weight-date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="tnum h-11 font-mono"
            />
          </div>
          <div>
            <Label htmlFor="weight-notes" className="mb-1.5 font-mono text-xs uppercase">
              {t("notes")}
            </Label>
            <Textarea
              id="weight-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder={t("notesPlaceholder")}
            />
          </div>
        </div>
      )}

      <button
        type="button"
        disabled={!valid || submitting}
        onClick={submit}
        className="mt-2 flex min-h-12 w-full items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
      >
        {submitting ? t("logging") : t("submit")}
      </button>
    </>
  );
}

type Tdee = {
  tdee_kcal: number | null;
  confidence: string | null;
  reasons: string[];
  window: { start: string; end: string; days: number };
  coverage: { logged_days: number; required_days: number; weigh_in_days: number };
};

/** The measured number as a ledger total, never a formula guess: when the
 * data can't carry an estimate the row says what's missing and how far
 * along the window is — the same provenance honesty as the sheet's
 * parentheticals. */
function TdeeBlock({ tdee, locale }: { tdee: Tdee; locale: string }) {
  const t = useTranslations("stats");
  const reasonLabel = (reason: string) => {
    switch (reason) {
      case "new_phase_water_shift":
        return t("reason_new_phase_water_shift");
      case "marginal_logging":
        return t("reason_marginal_logging");
      case "sparse_weigh_ins":
        return t("reason_sparse_weigh_ins");
      default:
        return reason;
    }
  };

  return (
    <>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-bold">
          TDEE{" "}
          <span className="font-mono text-xs font-normal text-muted-foreground">
            ({t("measured")})
          </span>
        </span>
        <span className="tnum font-mono text-2xl">
          {tdee.tdee_kcal != null ? tdee.tdee_kcal : "–"}
          <span className="ml-1 text-sm text-muted-foreground">kcal</span>
        </span>
      </div>

      {tdee.tdee_kcal != null ? (
        <>
          <p className="mt-1 font-mono text-xs text-muted-foreground tnum">
            {t("tdeeLine", {
              logged: tdee.coverage.logged_days,
              days: tdee.window.days,
              start: shortDate(tdee.window.start, locale),
              end: shortDate(tdee.window.end, locale),
            })}
          </p>
          {tdee.confidence === "low" && tdee.reasons.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("lowConfidence")} {tdee.reasons.map(reasonLabel).join(", ")}
            </p>
          )}
        </>
      ) : (
        <>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("tdeePending", {
              required: tdee.coverage.required_days,
              days: tdee.window.days,
            })}
          </p>
          <p className="mt-1 font-mono text-xs text-muted-foreground tnum">
            {t("tdeeProgress", {
              logged: tdee.coverage.logged_days,
              required: tdee.coverage.required_days,
              weighIns: tdee.coverage.weigh_in_days,
            })}
          </p>
        </>
      )}
      <p className="mt-1 text-xs text-muted-foreground">{t("tdeeWhat")}</p>
    </>
  );
}

type ReviewWeek = {
  week_start: string;
  week_end: string;
  partial: boolean;
  days_logged: number;
  days_in_week: number;
  kcal_avg: number | null;
  kcal_target_avg: number | null;
  protein_avg_g: number | null;
  weight_change_kg: number | null;
  sessions: number;
};

/** The weekly ledger: every week judged against the targets that were in
 * force on its own days. Trailing empty weeks (before the first data) stay
 * off the sheet; a quiet "no entries" week inside the story stays, because
 * a gap is part of the story. */
function WeeksLedger({ weeks, locale }: { weeks: ReviewWeek[]; locale: string }) {
  const t = useTranslations("stats");

  const hasContent = (w: ReviewWeek) =>
    w.days_logged > 0 || w.sessions > 0 || w.weight_change_kg != null;
  let lastWithContent = -1;
  weeks.forEach((w, i) => {
    if (hasContent(w)) lastWithContent = i;
  });
  const shown = lastWithContent === -1 ? [] : weeks.slice(0, lastWithContent + 1);

  if (shown.length === 0) {
    return (
      <div className="mt-2 border-t border-border py-8 text-center">
        <p className="text-sm text-muted-foreground">{t("weeksEmpty")}</p>
      </div>
    );
  }

  return (
    <ul className="mt-2">
      {shown.map((week) => {
        const bits: string[] = [];
        if (week.days_logged > 0) {
          bits.push(
            week.kcal_target_avg != null
              ? t("kcalPair", {
                  kcal: Math.round(week.kcal_avg ?? 0),
                  target: Math.round(week.kcal_target_avg),
                })
              : t("kcalOnly", { kcal: Math.round(week.kcal_avg ?? 0) }),
          );
          if (week.protein_avg_g != null)
            bits.push(t("proteinShort", { protein: Math.round(week.protein_avg_g) }));
          bits.push(t("daysLogged", { logged: week.days_logged, days: week.days_in_week }));
        } else {
          bits.push(t("noLogs"));
        }
        if (week.sessions > 0) bits.push(t("sessionsShort", { count: week.sessions }));

        return (
          <li key={week.week_start} className="border-t border-border py-2">
            <div className="flex items-baseline gap-3">
              <span className="text-xs font-bold uppercase tracking-wider">
                {t("weekShort")} {isoWeek(week.week_start)}
                {week.partial && (
                  <span className="ml-1.5 font-mono font-normal normal-case text-muted-foreground">
                    {t("partial")}
                  </span>
                )}
              </span>
              <span className="tnum min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
                {shortDate(week.week_start, locale)}–{shortDate(week.week_end, locale)}
              </span>
              <span className="tnum text-right font-mono text-sm">
                {week.weight_change_kg != null
                  ? `${rateFigure(week.weight_change_kg, locale)} kg`
                  : "–"}
              </span>
            </div>
            <p className="tnum mt-0.5 font-mono text-xs text-muted-foreground">
              {bits.join(" · ")}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

type TrainingData = {
  weeks: {
    week_start: string;
    partial: boolean;
    sessions: number;
    cardio_min: number;
    strength_sets: number;
    strength_volume_kg: number;
  }[];
  exercises: string[];
};

/** The training column: weekly facts, and one movement's load trend on
 * request — the user's own names, sets as they were said, e5RM as the
 * figure that makes progress comparable across rep counts. */
function TrainingSection({ data, locale }: { data: TrainingData; locale: string }) {
  const t = useTranslations("stats");
  const [selected, setSelected] = useState<string | null>(null);

  const movement = $api.useQuery(
    "get",
    "/api/stats/training",
    { params: { query: { exercise: selected ?? "", weeks: 26 } } },
    { enabled: selected != null },
  );

  const nf1 = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  const trainedWeeks = data.weeks.filter((w) => w.sessions > 0);

  return (
    <section className="mt-6">
      <h2 className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
        {t("training")}
      </h2>

      <ul className="mt-2">
        {trainedWeeks.map((week) => {
          const bits: string[] = [t("sessionsShort", { count: week.sessions })];
          if (week.cardio_min > 0)
            bits.push(t("minutesShort", { min: Math.round(week.cardio_min) }));
          if (week.strength_sets > 0)
            bits.push(t("setsShort", { count: week.strength_sets }));
          return (
            <li key={week.week_start} className="border-t border-border py-2">
              <div className="flex items-baseline gap-3">
                <span className="text-xs font-bold uppercase tracking-wider">
                  {t("weekShort")} {isoWeek(week.week_start)}
                  {week.partial && (
                    <span className="ml-1.5 font-mono font-normal normal-case text-muted-foreground">
                      {t("partial")}
                    </span>
                  )}
                </span>
                <span className="tnum min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
                  {bits.join(" · ")}
                </span>
                <span className="tnum text-right font-mono text-sm">
                  {week.strength_volume_kg > 0
                    ? t("volumeShort", { kg: Math.round(week.strength_volume_kg) })
                    : "–"}
                </span>
              </div>
            </li>
          );
        })}
      </ul>

      {data.exercises.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {data.exercises.map((name) => {
            const active = selected === name;
            return (
              <button
                key={name}
                type="button"
                aria-pressed={active}
                onClick={() => setSelected(active ? null : name)}
                className={cn(
                  "inline-flex min-h-11 items-center border px-3 font-mono text-xs hover:bg-secondary",
                  active ? "border-foreground bg-secondary font-bold" : "border-input",
                )}
              >
                {name}
              </button>
            );
          })}
        </div>
      )}

      {selected != null &&
        (movement.isPending ? (
          <Skeleton className="mt-3 h-16 w-full" />
        ) : movement.data?.exercise ? (
          movement.data.exercise.sessions.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">{t("movementEmpty")}</p>
          ) : (
            <ul className="mt-3">
              <li className="flex items-baseline gap-3 pb-1">
                <span className="min-w-0 flex-1" />
                <span className="font-mono text-xs text-muted-foreground">e5RM</span>
              </li>
              {movement.data.exercise.sessions.map((row) => (
                <li
                  key={row.log_id}
                  className="flex items-baseline gap-3 border-t border-border py-2"
                >
                  <span className="tnum font-mono text-xs text-muted-foreground">
                    {shortDate(row.date, locale)}
                  </span>
                  <span className="tnum min-w-0 flex-1 truncate text-sm">
                    {row.top_set != null ? (
                      <>
                        {t("topSet", {
                          reps: row.top_set.reps,
                          kg: nf1.format(row.top_set.weight_kg),
                        })}
                        <span className="ml-1.5 font-mono text-xs text-muted-foreground">
                          · {t("setsShort", { count: row.sets })}
                        </span>
                      </>
                    ) : (
                      <span className="text-muted-foreground italic">{t("bodyweightOnly")}</span>
                    )}
                  </span>
                  <span className="tnum text-right font-mono text-sm">
                    {row.e5rm_kg != null ? nf1.format(row.e5rm_kg) : "–"}
                  </span>
                </li>
              ))}
            </ul>
          )
        ) : null)}
    </section>
  );
}

"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Barbell, MagnifyingGlass, PersonSimpleRun, Sparkle, X } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { localDate, timeValue } from "@/lib/format";
import { useProfile } from "@/lib/profile";
import { cn } from "@/lib/utils";

type Activity = components["schemas"]["ActivityOut"];
type SummaryExercise = components["schemas"]["SummaryExerciseOut"];

const KINDS = ["cardio", "strength", "other"] as const;
type Kind = (typeof KINDS)[number];

const KIND_FIGURES = { cardio: PersonSimpleRun, strength: Barbell, other: Sparkle } as const;

type SetRow = { exercise: string; reps: string; weight: string; rpe: string };

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

const EMPTY_SET: SetRow = { exercise: "", reps: "", weight: "", rpe: "" };

function setsFromLog(log: SummaryExercise): SetRow[] {
  return log.sets.map((s) => ({
    exercise: s.exercise ?? "",
    reps: String(s.reps),
    weight: String(s.weight_kg),
    rpe: s.rpe != null ? String(s.rpe) : "",
  }));
}

type Props =
  | { mode: "new"; date?: string }
  | { mode: "edit"; log: SummaryExercise; date: string };

export function ExerciseForm(props: Props) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const t = useTranslations("exerciseForm");
  const profile = useProfile();
  const editing = props.mode === "edit";
  const backdate = props.mode === "new" ? props.date : undefined;

  const [kind, setKind] = useState<Kind>(
    editing ? (props.log.kind as Kind) : "cardio",
  );
  const [activity, setActivity] = useState<Activity | null>(
    editing ? (props.log.activity ?? null) : null,
  );
  const [duration, setDuration] = useState(
    editing && props.log.duration_min != null ? String(props.log.duration_min) : "",
  );
  const [sets, setSets] = useState<SetRow[]>(editing ? setsFromLog(props.log) : []);
  const [notes, setNotes] = useState(editing ? (props.log.notes ?? "") : "");
  const [planned, setPlanned] = useState(editing ? props.log.planned : false);
  const originalTime = editing ? timeValue(props.log.ts, profile.timezone) : "";
  const [time, setTime] = useState(
    editing ? originalTime : props.mode === "new" && props.date ? "12:00" : "",
  );
  const [query, setQuery] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const debounced = useDebounced(query.trim(), 250);
  const search = useQuery({
    queryKey: ["activity-search", debounced],
    enabled: kind !== "strength" && debounced.length >= 2,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/activities/search", {
        params: { query: { q: debounced, limit: 10 } },
      });
      if (error) throw error;
      return data;
    },
  });

  function pick(a: Activity) {
    setActivity(a);
    setQuery("");
  }

  function switchKind(next: Kind) {
    setKind(next);
    // A strength session takes sets, not a catalog activity — and the other
    // way around. Clearing here keeps the form from submitting a shape the
    // server would refuse.
    if (next === "strength") {
      setActivity(null);
      setQuery("");
      if (sets.length === 0) setSets([{ ...EMPTY_SET }]);
    } else {
      setSets([]);
    }
  }

  function setSet(index: number, patch: Partial<SetRow>) {
    setSets((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addSet() {
    // The next set is usually the same movement again — copy the row and let
    // the lifter change what changed.
    setSets((prev) => [...prev, prev.length ? { ...prev[prev.length - 1] } : { ...EMPTY_SET }]);
  }

  function removeSet(index: number) {
    setSets((prev) => prev.filter((_, i) => i !== index));
  }

  const setComplete = (row: SetRow) =>
    row.exercise.trim() !== "" &&
    parseInt(row.reps) > 0 &&
    row.weight.trim() !== "" &&
    parseFloat(row.weight) >= 0 &&
    (row.rpe === "" || (parseFloat(row.rpe) >= 1 && parseFloat(row.rpe) <= 10));

  const timeValid = backdate ? TIME_RE.test(time) : time === "" || TIME_RE.test(time);
  const durationValid = duration === "" || parseFloat(duration) > 0;
  const saysSomething =
    activity !== null ||
    (duration !== "" && parseFloat(duration) > 0) ||
    sets.length > 0 ||
    notes.trim() !== "";
  const valid =
    timeValid && durationValid && saysSomething && sets.every(setComplete);

  async function submit() {
    setSubmitting(true);
    const payloadSets = sets.map((row) => ({
      exercise: row.exercise.trim(),
      reps: parseInt(row.reps),
      weight_kg: parseFloat(row.weight),
      ...(row.rpe !== "" ? { rpe: parseFloat(row.rpe) } : {}),
    }));
    const base = {
      kind,
      activity_id: activity?.id ?? null,
      duration_min: duration !== "" ? parseFloat(duration) : null,
      sets: kind === "strength" && payloadSets.length ? payloadSets : null,
      notes: notes.trim() === "" ? null : notes.trim(),
    };

    try {
      if (props.mode === "new") {
        const ts = backdate
          ? `${backdate}T${time}`
          : time
            ? `${localDate(profile.timezone)}T${time}`
            : null;
        const { data, error } = await api.POST("/api/logs/exercise", {
          // A form filled by hand is the user stating facts — never a guess.
          body: { ...base, ts, planned, source: "user" },
        });
        if (error || !data) throw error ?? new Error("no response");
        await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
        router.push(`/?date=${data.date}&stamp=e${data.log_id}`);
      } else {
        const { data, error } = await api.PATCH("/api/logs/exercise/{log_id}", {
          params: { path: { log_id: props.log.log_id } },
          body: {
            changes: {
              ...base,
              planned,
              ...(time && time !== originalTime ? { ts: `${props.date}T${time}` } : {}),
            },
          },
        });
        if (error || !data) throw error ?? new Error("no response");
        await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
        router.push(`/?date=${data.date}&stamp=e${data.log_id}`);
      }
    } catch (err) {
      setSubmitting(false);
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : t("noAnswer");
      toast.error(editing ? t("reviseFailed") : t("logFailed"), { description: detail });
    }
  }

  return (
    <div className="flex flex-col gap-5 pt-2">
      {/* What kind of session — everything else follows from this */}
      <div role="group" aria-label={t("kind")} className="flex items-center gap-4">
        {KINDS.map((value) => {
          const active = kind === value;
          const Figure = KIND_FIGURES[value];
          return (
            <button
              key={value}
              type="button"
              aria-pressed={active}
              onClick={() => switchKind(value)}
              className={cn(
                "flex min-h-11 items-center font-mono text-xs uppercase tracking-wider",
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
                {t(value)}
              </span>
            </button>
          );
        })}
      </div>

      {/* The activity, from the English-only MET catalog */}
      {kind !== "strength" && (
        <div>
          <Label htmlFor="activity-search" className="mb-1.5 font-mono text-xs uppercase">
            {t("activity")}
          </Label>
          {activity ? (
            <div className="flex items-center justify-between gap-3 border border-input px-3 py-2">
              <span className="min-w-0 flex-1 truncate text-sm">{activity.name}</span>
              <span className="tnum font-mono text-xs text-muted-foreground">
                {activity.met} MET
              </span>
              <button
                type="button"
                aria-label={t("clearActivity")}
                onClick={() => setActivity(null)}
                className="flex size-11 items-center justify-center text-muted-foreground hover:text-destructive"
              >
                <X aria-hidden className="size-4" />
              </button>
            </div>
          ) : (
            <>
              <div className="relative">
                <MagnifyingGlass
                  aria-hidden
                  className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  id="activity-search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t("activityPlaceholder")}
                  autoComplete="off"
                  className="h-11 pl-9"
                />
              </div>
              {/* The catalog ships no translations — the reader is told, not
               * left to conclude the search is broken. */}
              <p className="mt-1 text-xs text-muted-foreground">{t("activityHint")}</p>
              {debounced.length >= 2 && (
                <div className="border border-t-0 border-input">
                  {search.isPending ? (
                    <p className="px-3 py-3 text-sm text-muted-foreground">{t("searching")}</p>
                  ) : search.error ? (
                    <p className="px-3 py-3 text-sm text-destructive">{t("searchFailed")}</p>
                  ) : search.data && search.data.results.length > 0 ? (
                    <ul>
                      {search.data.results.map((a) => (
                        <li key={a.id} className="border-b border-border last:border-b-0">
                          <button
                            type="button"
                            onClick={() => pick(a)}
                            className="flex min-h-11 w-full items-baseline gap-3 px-3 py-2 text-left hover:bg-secondary focus-visible:bg-secondary"
                          >
                            <span className="min-w-0 flex-1 truncate text-sm">{a.name}</span>
                            <span className="tnum font-mono text-xs text-muted-foreground">
                              {a.met} MET
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="px-3 py-3 text-sm text-muted-foreground">{t("noMatch")}</p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Sets — the strength session's substance */}
      {kind === "strength" && (
        <div>
          <p className="mb-1.5 font-mono text-xs uppercase tracking-wider text-muted-foreground">
            {t("sets")}
          </p>
          {sets.length > 0 && (
            <ul className="flex flex-col gap-3">
              {sets.map((row, index) => (
                <li key={index} className="border-b border-border pb-3">
                  <div className="flex items-center gap-2">
                    <span className="w-6 shrink-0 font-mono text-xs text-muted-foreground tnum">
                      {index + 1}.
                    </span>
                    <Label htmlFor={`set-ex-${index}`} className="sr-only">
                      {t("movementOf", { n: index + 1 })}
                    </Label>
                    <Input
                      id={`set-ex-${index}`}
                      value={row.exercise}
                      onChange={(e) => setSet(index, { exercise: e.target.value })}
                      placeholder={t("movementPlaceholder")}
                      autoComplete="off"
                      className="h-11 flex-1"
                    />
                    <button
                      type="button"
                      aria-label={t("removeSet", { n: index + 1 })}
                      onClick={() => removeSet(index)}
                      className="flex size-11 shrink-0 items-center justify-center text-muted-foreground hover:text-destructive"
                    >
                      <X aria-hidden className="size-4" />
                    </button>
                  </div>
                  <div className="mt-2 ml-8 grid grid-cols-3 gap-2">
                    {/* Gym notation, locale-free: 5 × · 100 kg · 8 RPE */}
                    {(
                      [
                        ["reps", row.reps, (v: string) => setSet(index, { reps: v }), t("reps"), "×"],
                        ["weight", row.weight, (v: string) => setSet(index, { weight: v }), "kg", "kg"],
                        ["rpe", row.rpe, (v: string) => setSet(index, { rpe: v }), "RPE", "RPE"],
                      ] as const
                    ).map(([field, value, onChange, label, suffix]) => (
                      <div key={field} className="relative">
                        <Label htmlFor={`set-${field}-${index}`} className="sr-only">
                          {label}
                        </Label>
                        <Input
                          id={`set-${field}-${index}`}
                          inputMode="decimal"
                          value={value}
                          onChange={(e) => onChange(e.target.value)}
                          className={cn(
                            "tnum h-11 text-right font-mono",
                            suffix === "RPE" ? "pr-10" : "pr-8",
                          )}
                        />
                        <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 font-mono text-xs text-muted-foreground">
                          {suffix}
                        </span>
                      </div>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            onClick={addSet}
            className="mt-2 inline-flex min-h-11 items-center border border-input px-3 font-mono text-xs hover:bg-secondary"
          >
            {t("addSet")}
          </button>
        </div>
      )}

      {/* Duration and time */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="ex-duration" className="mb-1.5 font-mono text-xs uppercase">
            {t("duration")}
          </Label>
          <div className="relative">
            <Input
              id="ex-duration"
              inputMode="decimal"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              aria-invalid={!durationValid}
              className="tnum h-11 pr-11 text-right font-mono"
            />
            <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 font-mono text-xs text-muted-foreground">
              min
            </span>
          </div>
        </div>
        <div>
          <Label htmlFor="ex-time" className="mb-1.5 font-mono text-xs uppercase">
            {backdate ? t("timeOn", { date: backdate }) : editing ? t("time") : t("timeNow")}
          </Label>
          <Input
            id="ex-time"
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            aria-invalid={!timeValid}
            className="tnum h-11 font-mono"
          />
        </div>
      </div>

      {!backdate && !editing && (
        <label className="-mt-2 flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={planned}
            onChange={(e) => setPlanned(e.target.checked)}
            className="size-4 accent-primary"
          />
          {t("plannedToggle")}
        </label>
      )}

      <div>
        <Label htmlFor="ex-notes" className="mb-1.5 font-mono text-xs uppercase">
          {t("notes")}
        </Label>
        <Textarea
          id="ex-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder={t("notesPlaceholder")}
        />
      </div>

      {editing && props.log.planned && (
        <label className="flex min-h-11 items-center gap-2 border border-input px-3 text-sm">
          <input
            type="checkbox"
            checked={!planned}
            onChange={(e) => setPlanned(!e.target.checked)}
            className="size-4 accent-primary"
          />
          {t("markDone")}
        </label>
      )}

      <div className="sticky bottom-[4.5rem] lg:bottom-4 bg-background pb-1">
        <button
          type="button"
          disabled={!valid || submitting}
          onClick={submit}
          className={cn(
            "flex min-h-12 w-full items-center justify-center gap-2 font-bold",
            "bg-primary text-primary-foreground hover:opacity-90",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
            "disabled:cursor-not-allowed disabled:opacity-40",
          )}
        >
          {submitting
            ? editing
              ? t("saving")
              : t("logging")
            : editing
              ? t("saveRevision")
              : t("logExercise")}
        </button>
      </div>
    </div>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

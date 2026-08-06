"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MagnifyingGlass, Minus, Plus, X } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { MEALS, grams as fmtGrams, kcal as fmtKcal, sourceCode } from "@/lib/format";
import { cn } from "@/lib/utils";

type FoodCandidate = components["schemas"]["FoodCandidateOut"];
type SummaryMeal = components["schemas"]["SummaryMealOut"];

type FormItem = {
  food_id: number;
  name: string;
  source: string | null;
  grams: string;
  kcalPer100: number | null;
  units: { code: string; name: string; grams: number }[];
};

type Props =
  | { mode: "new"; date?: string }
  | { mode: "edit"; log: SummaryMeal; date: string };

/** Client-side suggestion only — the server never guesses a meal. */
function suggestMeal(): string {
  const h = new Date().getHours();
  if (h >= 5 && h < 10) return "breakfast";
  if (h >= 10 && h < 15) return "lunch";
  if (h >= 16 && h < 21) return "dinner";
  return "snack";
}

function itemsFromLog(log: SummaryMeal): FormItem[] {
  return log.items.map((item) => ({
    food_id: item.food_id,
    name: item.name ?? `#${item.food_id}`,
    source: item.source,
    grams: fmtGrams(item.grams),
    // Recover per-100g from the snapshot so the preview stays honest.
    kcalPer100: item.kcal != null && item.grams > 0 ? (item.kcal / item.grams) * 100 : null,
    units: [],
  }));
}

export function MealForm(props: Props) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const t = useTranslations("logForm");
  const tMeals = useTranslations("meals");
  const editing = props.mode === "edit";

  const [items, setItems] = useState<FormItem[]>(editing ? itemsFromLog(props.log) : []);
  const [meal, setMeal] = useState<string>(editing ? (props.log.meal ?? "none") : suggestMeal());
  const [notes, setNotes] = useState(editing ? (props.log.notes ?? "") : "");
  const [planned, setPlanned] = useState(editing ? props.log.planned : false);
  const [time, setTime] = useState("12:00");
  const [query, setQuery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const backdate = props.mode === "new" ? props.date : undefined;

  const debounced = useDebounced(query.trim(), 250);
  const search = useQuery({
    queryKey: ["food-search", debounced],
    enabled: debounced.length >= 2,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/foods/search", {
        params: { query: { q: debounced, limit: 10 } },
      });
      if (error) throw error;
      return data;
    },
  });

  const previewKcal = useMemo(() => {
    let sum = 0;
    for (const item of items) {
      const g = parseFloat(item.grams);
      if (item.kcalPer100 != null && g > 0) sum += (item.kcalPer100 * g) / 100;
    }
    return Math.round(sum);
  }, [items]);

  const valid = items.length > 0 && items.every((item) => parseFloat(item.grams) > 0);

  function add(food: FoodCandidate) {
    const unit = food.serving_units[0];
    setItems((prev) => [
      ...prev,
      {
        food_id: food.id,
        name: food.name,
        source: food.source,
        grams: fmtGrams(unit?.grams ?? 100),
        kcalPer100: food.per_100g.kcal,
        units: food.serving_units,
      },
    ]);
    setQuery("");
    searchRef.current?.focus();
  }

  function setGrams(index: number, grams: string) {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, grams } : item)));
  }

  function nudgeGrams(index: number, delta: number) {
    setItems((prev) =>
      prev.map((item, i) => {
        if (i !== index) return item;
        const next = Math.max(0, (parseFloat(item.grams) || 0) + delta);
        return { ...item, grams: fmtGrams(next) };
      }),
    );
  }

  function remove(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }

  async function submit() {
    setSubmitting(true);
    const payloadItems = items.map((item) => ({
      food_id: item.food_id,
      grams: parseFloat(item.grams),
    }));
    const mealValue = meal === "none" ? null : meal;
    const notesValue = notes.trim() === "" ? null : notes.trim();

    try {
      if (props.mode === "new") {
        const { data, error } = await api.POST("/api/logs/meals", {
          body: {
            items: payloadItems,
            meal: mealValue,
            ts: backdate ? `${backdate}T${time}` : null,
            input_mode: planned ? "plan" : "text",
            notes: notesValue,
          },
        });
        if (error || !data) throw error ?? new Error("no response");
        await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
        router.push(
          backdate ? `/?date=${backdate}&stamp=${data.log_id}` : `/?stamp=${data.log_id}`,
        );
      } else {
        const { data, error } = await api.PATCH("/api/logs/meals/{log_id}", {
          params: { path: { log_id: props.log.log_id } },
          body: {
            changes: {
              items: payloadItems,
              meal: mealValue,
              notes: notesValue,
              planned,
            },
          },
        });
        if (error || !data) throw error ?? new Error("no response");
        await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
        router.push(`/?date=${props.date}&stamp=${data.log_id}`);
      }
    } catch (err) {
      setSubmitting(false);
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : t("noAnswer");
      toast.error(editing ? t("reviseFailed") : t("logFailed"), {
        description: detail,
      });
    }
  }

  return (
    <div className="flex flex-col gap-5 pt-2">
      {/* Search — the flow starts here and stays here for most logs */}
      <div>
        <Label htmlFor="food-search" className="sr-only">
          {t("searchLabel")}
        </Label>
        <div className="relative">
          <MagnifyingGlass
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            id="food-search"
            ref={searchRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("searchPlaceholder")}
            autoComplete="off"
            className="h-12 pl-9 text-base"
            autoFocus={!editing}
          />
        </div>

        {debounced.length >= 2 && (
          <div className="border border-t-0 border-input">
            {search.isPending ? (
              <p className="px-3 py-3 text-sm text-muted-foreground">{t("searching")}</p>
            ) : search.error ? (
              <p className="px-3 py-3 text-sm text-destructive">{t("searchFailed")}</p>
            ) : search.data && search.data.results.length > 0 ? (
              <ul>
                {search.data.results.map((food) => (
                  <li key={food.id} className="border-b border-border last:border-b-0">
                    <button
                      type="button"
                      onClick={() => add(food)}
                      className="flex min-h-11 w-full items-baseline gap-3 px-3 py-2 text-left hover:bg-secondary focus-visible:bg-secondary"
                    >
                      <span className="min-w-0 flex-1 truncate">
                        {food.name}
                        {sourceCode(food.source) && (
                          <span className="ml-1.5 font-mono text-xs text-muted-foreground">
                            ({sourceCode(food.source)})
                          </span>
                        )}
                      </span>
                      <span className="tnum font-mono text-xs text-muted-foreground">
                        {fmtKcal(food.per_100g.kcal)} {t("kcalPer100")}
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
      </div>

      {/* The plate so far */}
      {items.length === 0 ? (
        <p className="border-t border-border pt-4 text-sm text-muted-foreground">
          {t("emptyPlate")}
        </p>
      ) : (
        <ul className="border-t-2 border-foreground">
          {items.map((item, index) => (
            <li key={`${item.food_id}-${index}`} className="border-b border-border py-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 flex-1 truncate font-medium">
                  {item.name}
                  {sourceCode(item.source) && (
                    <span className="ml-1.5 font-mono text-xs font-normal text-muted-foreground">
                      ({sourceCode(item.source)})
                    </span>
                  )}
                </span>
                <span className="tnum font-mono text-sm">
                  {item.kcalPer100 != null && parseFloat(item.grams) > 0
                    ? Math.round((item.kcalPer100 * parseFloat(item.grams)) / 100)
                    : "–"}{" "}
                  kcal
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  aria-label={t("less", { name: item.name })}
                  onClick={() => nudgeGrams(index, -10)}
                  className="flex size-11 items-center justify-center border border-input hover:bg-secondary"
                >
                  <Minus aria-hidden className="size-4" />
                </button>
                <div className="relative w-24">
                  <Label htmlFor={`grams-${index}`} className="sr-only">
                    {t("gramsOf", { name: item.name })}
                  </Label>
                  <Input
                    id={`grams-${index}`}
                    inputMode="decimal"
                    value={item.grams}
                    onChange={(e) => setGrams(index, e.target.value)}
                    aria-invalid={!(parseFloat(item.grams) > 0)}
                    className="tnum h-11 pr-7 text-right font-mono"
                  />
                  <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 font-mono text-xs text-muted-foreground">
                    g
                  </span>
                </div>
                <button
                  type="button"
                  aria-label={t("more", { name: item.name })}
                  onClick={() => nudgeGrams(index, 10)}
                  className="flex size-11 items-center justify-center border border-input hover:bg-secondary"
                >
                  <Plus aria-hidden className="size-4" />
                </button>
                <div className="flex-1" />
                <button
                  type="button"
                  aria-label={t("remove", { name: item.name })}
                  onClick={() => remove(index)}
                  className="flex size-11 items-center justify-center text-muted-foreground hover:text-destructive"
                >
                  <X aria-hidden className="size-4" />
                </button>
              </div>
              {item.units.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {item.units.map((unit) => (
                    <button
                      key={unit.code}
                      type="button"
                      onClick={() => nudgeGrams(index, unit.grams)}
                      className="inline-flex min-h-11 items-center border border-input px-3 font-mono text-xs hover:bg-secondary"
                    >
                      +{unit.name} {fmtGrams(unit.grams)}&#8239;g
                    </button>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Details: everything optional, out of the fast path */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="meal-type" className="mb-1.5 font-mono text-xs uppercase">
            {t("meal")}
          </Label>
          <Select value={meal} onValueChange={setMeal}>
            <SelectTrigger id="meal-type" className="h-11 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">{t("unlabelled")}</SelectItem>
              {MEALS.map((value) => (
                <SelectItem key={value} value={value}>
                  {tMeals(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {backdate ? (
          <div>
            <Label htmlFor="log-time" className="mb-1.5 font-mono text-xs uppercase">
              {t("timeOn", { date: backdate })}
            </Label>
            <Input
              id="log-time"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="tnum h-11 font-mono"
            />
          </div>
        ) : (
          <div className="flex items-end">
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={planned}
                onChange={(e) => setPlanned(e.target.checked)}
                className="size-4 accent-primary"
              />
              {t("plannedToggle")}
            </label>
          </div>
        )}
      </div>

      <div>
        <Label htmlFor="log-notes" className="mb-1.5 font-mono text-xs uppercase">
          {t("notes")}
        </Label>
        <Textarea
          id="log-notes"
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
          {t("markEaten")}
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
              : previewKcal > 0
                ? t("logMealKcal", { kcal: previewKcal })
                : t("logMeal")}
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

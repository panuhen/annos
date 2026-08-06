"use client";

import { CaretLeft, MagnifyingGlass, Minus, Plus, X } from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { grams as fmtGrams, kcal as fmtKcal, sourceCode } from "@/lib/format";
import { cn } from "@/lib/utils";

type TemplateOut = components["schemas"]["TemplateOut"];
type FoodCandidate = components["schemas"]["FoodCandidateOut"];

type EditItem = {
  food_id: number;
  name: string;
  grams: string;
};

/** Edit one template: rename, restate items, set or clear the recipe yield,
 * or delete it for good. Same correction vocabulary as a meal log. */
export default function TemplateEditPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("templates");

  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/templates");
      if (error) throw error;
      return data;
    },
  });

  const template = templates.data?.templates.find(
    (candidate) => String(candidate.template_id) === id,
  );

  return (
    <>
      <header className="flex items-center gap-1 border-b-2 border-foreground pt-5 pb-2">
        <Link
          href="/templates"
          aria-label={t("backToList")}
          className="-ml-2 flex size-11 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <CaretLeft aria-hidden className="size-5" />
        </Link>
        <h1 className="text-lg font-bold">{t("editTitle")}</h1>
      </header>

      {templates.isPending ? (
        <div className="pt-4">
          <Skeleton className="mb-2 h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : template ? (
        <TemplateEditor template={template} />
      ) : (
        <div className="pt-6">
          <p className="font-medium">{t("notFound")}</p>
          <Link
            href="/templates"
            className="mt-3 inline-block text-primary underline underline-offset-2"
          >
            {t("backToList")}
          </Link>
        </div>
      )}
    </>
  );
}

function TemplateEditor({ template }: { template: TemplateOut }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const t = useTranslations("templates");
  const tForm = useTranslations("logForm");

  const [name, setName] = useState(template.name);
  const [totalGrams, setTotalGrams] = useState(
    template.total_grams != null ? fmtGrams(template.total_grams) : "",
  );
  const [items, setItems] = useState<EditItem[]>(
    template.items.map((item) => ({
      food_id: item.food_id,
      name: item.name ?? `#${item.food_id}`,
      grams: fmtGrams(item.grams),
    })),
  );
  const [query, setQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [armed, setArmed] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

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

  const valid =
    name.trim() !== "" &&
    items.length > 0 &&
    items.every((item) => parseFloat(item.grams) > 0) &&
    (totalGrams.trim() === "" || parseFloat(totalGrams) > 0);

  function add(food: FoodCandidate) {
    setItems((prev) => [
      ...prev,
      { food_id: food.id, name: food.name, grams: fmtGrams(food.serving_units[0]?.grams ?? 100) },
    ]);
    setQuery("");
    searchRef.current?.focus();
  }

  function setGrams(index: number, grams: string) {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, grams } : item)));
  }

  function nudge(index: number, delta: number) {
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

  async function save() {
    setSaving(true);
    const { data, error } = await api.PATCH("/api/templates/{template_id}", {
      params: { path: { template_id: template.template_id } },
      body: {
        changes: {
          name: name.trim(),
          items: items.map((item) => ({ food_id: item.food_id, grams: parseFloat(item.grams) })),
          total_grams: totalGrams.trim() === "" ? null : parseFloat(totalGrams),
        },
      },
    });
    setSaving(false);
    if (error || !data) {
      const detail =
        typeof error === "object" && error !== null && "detail" in error
          ? String((error as { detail: unknown }).detail)
          : undefined;
      toast.error(t("saveFailed"), { description: detail });
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ["templates"] });
    toast(t("saved", { name: data.name }));
    router.push("/templates");
  }

  async function destroy() {
    if (!armed) {
      setArmed(true);
      return;
    }
    setDeleting(true);
    const { error } = await api.DELETE("/api/templates/{template_id}", {
      params: { path: { template_id: template.template_id } },
    });
    if (error) {
      toast.error(t("deleteFailed"));
      setDeleting(false);
      setArmed(false);
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ["templates"] });
    router.push("/templates");
  }

  return (
    <div className="flex flex-col gap-5 pt-4">
      <div>
        <Label htmlFor="template-name" className="mb-1.5 font-mono text-xs uppercase">
          {tForm("templateName")}
        </Label>
        <Input
          id="template-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoComplete="off"
          className="h-11"
        />
      </div>

      {/* Add foods the same way the meal form does */}
      <div>
        <Label htmlFor="template-food-search" className="sr-only">
          {tForm("searchLabel")}
        </Label>
        <div className="relative">
          <MagnifyingGlass
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            id="template-food-search"
            ref={searchRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={tForm("searchPlaceholder")}
            autoComplete="off"
            className="h-11 pl-9"
          />
        </div>
        {debounced.length >= 2 && (
          <div className="border border-t-0 border-input">
            {search.isPending ? (
              <p className="px-3 py-3 text-sm text-muted-foreground">{tForm("searching")}</p>
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
                        {fmtKcal(food.per_100g.kcal)} {tForm("kcalPer100")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-3 py-3 text-sm text-muted-foreground">{tForm("noMatch")}</p>
            )}
          </div>
        )}
      </div>

      {items.length === 0 ? (
        <p className="border-t border-border pt-4 text-sm text-muted-foreground">
          {tForm("emptyPlate")}
        </p>
      ) : (
        <ul className="border-t-2 border-foreground">
          {items.map((item, index) => (
            <li key={`${item.food_id}-${index}`} className="border-b border-border py-3">
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
                <button
                  type="button"
                  aria-label={tForm("less", { name: item.name })}
                  onClick={() => nudge(index, -10)}
                  className="flex size-11 items-center justify-center border border-input hover:bg-secondary"
                >
                  <Minus aria-hidden className="size-4" />
                </button>
                <div className="relative w-24">
                  <Label htmlFor={`tpl-grams-${index}`} className="sr-only">
                    {tForm("gramsOf", { name: item.name })}
                  </Label>
                  <Input
                    id={`tpl-grams-${index}`}
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
                  aria-label={tForm("more", { name: item.name })}
                  onClick={() => nudge(index, 10)}
                  className="flex size-11 items-center justify-center border border-input hover:bg-secondary"
                >
                  <Plus aria-hidden className="size-4" />
                </button>
                <button
                  type="button"
                  aria-label={tForm("remove", { name: item.name })}
                  onClick={() => remove(index)}
                  className="flex size-11 items-center justify-center text-muted-foreground hover:text-destructive"
                >
                  <X aria-hidden className="size-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div>
        <Label htmlFor="total-grams" className="mb-1.5 font-mono text-xs uppercase">
          {t("totalGrams")}
        </Label>
        <div className="relative w-40">
          <Input
            id="total-grams"
            inputMode="decimal"
            value={totalGrams}
            onChange={(e) => setTotalGrams(e.target.value)}
            placeholder={t("noYield")}
            className="tnum h-11 pr-7 text-right font-mono"
          />
          <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 font-mono text-xs text-muted-foreground">
            g
          </span>
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">{t("yieldNote")}</p>
      </div>

      <div className="sticky bottom-[4.5rem] lg:bottom-4 bg-background pb-1">
        <button
          type="button"
          disabled={!valid || saving}
          onClick={save}
          className={cn(
            "flex min-h-12 w-full items-center justify-center font-bold",
            "bg-primary text-primary-foreground hover:opacity-90",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
            "disabled:cursor-not-allowed disabled:opacity-40",
          )}
        >
          {saving ? t("saving") : t("save")}
        </button>
      </div>

      <div className="border-t border-border pt-1">
        <button
          type="button"
          onClick={destroy}
          disabled={deleting}
          onBlur={() => setArmed(false)}
          className={cn(
            "flex min-h-11 items-center font-mono text-xs uppercase tracking-wider",
            armed ? "font-bold text-destructive" : "text-muted-foreground hover:text-destructive",
            deleting && "cursor-not-allowed opacity-40",
          )}
        >
          {deleting ? t("deleting") : armed ? t("deleteConfirm") : t("deleteTemplate")}
        </button>
      </div>
    </div>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

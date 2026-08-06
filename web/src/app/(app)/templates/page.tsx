"use client";

import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { api } from "@/lib/api/client";
import { grams as fmtGrams, kcal as fmtKcal } from "@/lib/format";

/** The saved templates as a browsable sheet: each one an entry block, tap to
 * edit. Creation stays where the food is — the meal form's save-as-template. */
export default function TemplatesPage() {
  const t = useTranslations("templates");

  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/templates");
      if (error) throw error;
      return data;
    },
  });

  return (
    <>
      <header className="flex items-center gap-1 border-b-2 border-foreground pt-5 pb-2">
        <Link
          href="/log"
          aria-label={t("backToLog")}
          className="-ml-2 flex size-11 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <CaretLeft aria-hidden className="size-5" />
        </Link>
        <h1 className="text-lg font-bold">{t("title")}</h1>
      </header>

      {templates.isPending ? (
        <p className="pt-4 text-sm text-muted-foreground">{t("reading")}</p>
      ) : templates.data && templates.data.templates.length > 0 ? (
        <ul className="pt-1">
          {templates.data.templates.map((template) => (
            <li key={template.template_id} className="border-b border-border">
              <Link
                href={`/templates/${template.template_id}`}
                className="block py-3 hover:bg-secondary focus-visible:bg-secondary"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 flex-1 truncate text-sm font-bold">
                    {template.name}
                    {template.total_grams != null && (
                      <span className="ml-1.5 font-mono text-xs font-normal text-muted-foreground">
                        ({fmtGrams(template.total_grams)}&#8239;g)
                      </span>
                    )}
                  </span>
                  <span className="tnum w-16 text-right font-mono text-sm">
                    {fmtKcal(template.kcal)} kcal
                  </span>
                  <CaretRight aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                </div>
                <ul className="mt-1 space-y-0.5">
                  {template.items.map((item, i) => (
                    <li key={i} className="flex items-baseline gap-3">
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {item.name ?? `#${item.food_id}`}
                      </span>
                      <span className="tnum font-mono text-xs text-muted-foreground">
                        {fmtGrams(item.grams)}&#8239;g
                      </span>
                    </li>
                  ))}
                </ul>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="pt-6">
          <p className="font-medium">{t("emptyTitle")}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t("emptyBody")}</p>
          <Link
            href="/log"
            className="mt-3 inline-block text-primary underline underline-offset-2"
          >
            {t("goLog")}
          </Link>
        </div>
      )}
    </>
  );
}

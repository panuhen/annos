"use client";

import { CaretLeft } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { MealForm } from "@/components/meal-form";
import { Skeleton } from "@/components/ui/skeleton";
import { $api } from "@/lib/api/hooks";

export default function ReviseLogPage() {
  return (
    <Suspense fallback={<Skeleton className="mt-6 h-12 w-full" />}>
      <ReviseLog />
    </Suspense>
  );
}

/** Revision works from the day summary — the log's current contents come
 * from there, so a deep link needs the day too (?date=). Without it we try
 * today. */
function ReviseLog() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const t = useTranslations("revisePage");
  const date = params.get("date") ?? undefined;

  const summary = $api.useQuery("get", "/api/summary/daily", {
    params: { query: date ? { date } : {} },
  });

  const log = summary.data?.meals.find((meal) => String(meal.log_id) === id);
  const day = summary.data?.date ?? date ?? "";

  return (
    <>
      <header className="flex items-center gap-1 border-b-2 border-foreground pt-5 pb-2">
        <Link
          href={day ? `/?date=${day}` : "/"}
          aria-label={t("backToToday")}
          className="-ml-2 flex size-11 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <CaretLeft aria-hidden className="size-5" />
        </Link>
        <h1 className="text-lg font-bold">
          {t("title")}
          {day && (
            <span className="ml-2 font-mono text-sm font-normal text-muted-foreground">{day}</span>
          )}
        </h1>
      </header>

      {summary.isPending ? (
        <div className="pt-4">
          <Skeleton className="mb-2 h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : log ? (
        <MealForm mode="edit" log={log} date={day} />
      ) : (
        <div className="pt-6">
          <p className="font-medium">{date ? t("notOnThat") : t("notOnToday")}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t("hint")}</p>
          <Link href="/" className="mt-3 inline-block text-primary underline underline-offset-2">
            {t("backToToday")}
          </Link>
        </div>
      )}
    </>
  );
}

"use client";

import { CaretLeft } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { MealForm } from "@/components/meal-form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { $api } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

export default function ReviseLogPage() {
  return (
    <Suspense fallback={<Skeleton className="mt-6 h-12 w-full" />}>
      <ReviseLog />
    </Suspense>
  );
}

/** Deletion, not correction: for the log that should never have existed.
 * Two taps — the second is armed in rye red and says it's permanent. */
function DeleteLog({ logId, day }: { logId: number; day: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const t = useTranslations("revisePage");
  const [armed, setArmed] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function run() {
    if (!armed) {
      setArmed(true);
      return;
    }
    setDeleting(true);
    const { error } = await api.DELETE("/api/logs/meals/{log_id}", {
      params: { path: { log_id: logId } },
    });
    if (error) {
      toast.error(t("deleteFailed"));
      setDeleting(false);
      setArmed(false);
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
    router.push(day ? `/?date=${day}` : "/");
  }

  return (
    <div className="mt-8 border-t border-border pt-1">
      <button
        type="button"
        onClick={run}
        disabled={deleting}
        onBlur={() => setArmed(false)}
        className={cn(
          "flex min-h-11 items-center font-mono text-xs uppercase tracking-wider",
          armed
            ? "font-bold text-destructive"
            : "text-muted-foreground hover:text-destructive",
          deleting && "cursor-not-allowed opacity-40",
        )}
      >
        {deleting ? t("deleting") : armed ? t("deleteConfirm") : t("deleteEntry")}
      </button>
    </div>
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
        <>
          <MealForm mode="edit" log={log} date={day} />
          <DeleteLog logId={log.log_id} day={day} />
        </>
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

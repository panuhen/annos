"use client";

import { CaretLeft } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ExerciseForm } from "@/components/exercise-form";
import { Skeleton } from "@/components/ui/skeleton";

export default function ExercisePage() {
  return (
    <Suspense fallback={<Skeleton className="mt-6 h-12 w-full" />}>
      <ExerciseNew />
    </Suspense>
  );
}

function ExerciseNew() {
  const params = useSearchParams();
  const t = useTranslations("exercisePage");
  const date = params.get("date") ?? undefined;

  return (
    <>
      <header className="flex items-center gap-1 border-b-2 border-foreground pt-5 pb-2">
        <Link
          href={date ? `/?date=${date}` : "/"}
          aria-label={t("back")}
          className="-ml-2 flex size-11 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <CaretLeft aria-hidden className="size-5" />
        </Link>
        <h1 className="text-lg font-bold">
          {t("title")}
          {date && (
            <span className="ml-2 font-mono text-sm font-normal text-muted-foreground">
              {date}
            </span>
          )}
        </h1>
      </header>
      <ExerciseForm mode="new" date={date} />
    </>
  );
}

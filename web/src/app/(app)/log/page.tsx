"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { MealForm } from "@/components/meal-form";
import { Skeleton } from "@/components/ui/skeleton";

export default function LogPage() {
  return (
    <Suspense fallback={<Skeleton className="mt-6 h-12 w-full" />}>
      <LogNew />
    </Suspense>
  );
}

function LogNew() {
  const params = useSearchParams();
  const date = params.get("date") ?? undefined;

  return (
    <>
      <header className="flex items-center gap-1 border-b-2 border-foreground pt-5 pb-2">
        <Link
          href={date ? `/?date=${date}` : "/"}
          aria-label="Back to the day"
          className="-ml-2 flex size-11 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft aria-hidden className="size-5" />
        </Link>
        <h1 className="text-lg font-bold">
          Log a meal
          {date && <span className="ml-2 font-mono text-sm font-normal text-muted-foreground">{date}</span>}
        </h1>
      </header>
      <MealForm mode="new" date={date} />
    </>
  );
}

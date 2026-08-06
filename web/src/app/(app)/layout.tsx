"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppNav, DesktopNav } from "@/components/app-nav";
import { FineliFooter } from "@/components/fineli-footer";
import { Skeleton } from "@/components/ui/skeleton";
import { authClient } from "@/lib/auth-client";
import { ProfileProvider, useProfileQuery } from "@/lib/profile";

/** Every page in this group needs a session and a registered profile.
 * Unauthenticated → /sign-in; authenticated but unregistered → /welcome. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const t = useTranslations("gate");
  const { data: session, isPending: sessionPending } = authClient.useSession();
  const profile = useProfileQuery(!!session);

  useEffect(() => {
    if (!sessionPending && !session) router.replace("/sign-in");
  }, [sessionPending, session, router]);

  useEffect(() => {
    if (session && profile.data === null && !profile.isPending) router.replace("/welcome");
  }, [session, profile.data, profile.isPending, router]);

  if (sessionPending || !session || profile.isPending || profile.data === null) {
    return (
      <div className="mx-auto max-w-md px-4 pt-6">
        <Skeleton className="mb-4 h-5 w-32" />
        <Skeleton className="mb-6 h-9 w-56" />
        <Skeleton className="mb-2 h-4 w-full" />
        <Skeleton className="mb-2 h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  if (profile.error) {
    return (
      <div className="mx-auto max-w-md px-4 pt-10">
        <h1 className="text-lg font-bold">{t("errorTitle")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("errorBody")}</p>
      </div>
    );
  }

  return (
    <ProfileProvider value={profile.data}>
      <div className="mx-auto flex min-h-dvh max-w-md flex-col px-4 pb-24 lg:max-w-2xl lg:pb-10">
        <DesktopNav />
        {children}
        <FineliFooter className="mt-auto pt-10 pb-2 font-mono text-[0.625rem] leading-relaxed text-muted-foreground" />
      </div>
      <AppNav />
    </ProfileProvider>
  );
}

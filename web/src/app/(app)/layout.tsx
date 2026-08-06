"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppNav, DesktopNav } from "@/components/app-nav";
import { Skeleton } from "@/components/ui/skeleton";
import { LOCALE_COOKIE, isLocale } from "@/i18n/config";
import { authClient } from "@/lib/auth-client";
import { ProfileProvider, useProfileQuery } from "@/lib/profile";

/** Every page in this group needs a session and a registered profile.
 * Unauthenticated → /sign-in; authenticated but unregistered → /welcome. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const t = useTranslations("gate");
  const locale = useLocale();
  const { data: session, isPending: sessionPending } = authClient.useSession();
  const profile = useProfileQuery(!!session);

  useEffect(() => {
    if (!sessionPending && !session) router.replace("/sign-in");
  }, [sessionPending, session, router]);

  // The chosen app language lives on the profile so it follows the user to
  // any browser; the cookie is only the rendering mechanism. Sync once the
  // profile arrives — after the refresh the two agree and this is a no-op.
  useEffect(() => {
    const pref = profile.data?.ui_language;
    if (isLocale(pref ?? undefined) && pref !== locale) {
      document.cookie = `${LOCALE_COOKIE}=${pref};path=/;max-age=31536000;samesite=lax`;
      router.refresh();
    }
  }, [profile.data?.ui_language, locale, router]);

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
      </div>
      <AppNav />
    </ProfileProvider>
  );
}

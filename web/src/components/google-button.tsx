"use client";

import { useState } from "react";

import { useTranslations } from "next-intl";

import { authClient } from "@/lib/auth-client";

/**
 * Sign in with Google, shown only when the provider is configured
 * (NEXT_PUBLIC_GOOGLE_ENABLED, mirroring the server-side credential gate in
 * auth.ts). New users land on /welcome to draw a nickname exactly like the
 * email flow; returning users go to `callbackURL` — which the sign-in page
 * sets to the OAuth continuation when it is standing in as the MCP login page.
 */
export function GoogleButton({ callbackURL = "/" }: { callbackURL?: string }) {
  const t = useTranslations("auth");
  const [pending, setPending] = useState(false);

  if (process.env.NEXT_PUBLIC_GOOGLE_ENABLED !== "true") return null;

  async function onClick() {
    setPending(true);
    await authClient.signIn.social({
      provider: "google",
      callbackURL,
      newUserCallbackURL: "/welcome",
    });
    // On success the browser has already left for Google; only an immediate
    // failure returns here, so drop the pending state to re-enable the button.
    setPending(false);
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending}
      className="mx-auto flex min-h-11 w-fit items-center justify-center gap-2.5 rounded-full border border-border px-6 text-sm font-medium transition-colors hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
    >
      <svg aria-hidden="true" viewBox="0 0 18 18" className="size-[18px]">
        <path
          fill="#4285F4"
          d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z"
        />
        <path
          fill="#34A853"
          d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z"
        />
        <path
          fill="#FBBC05"
          d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z"
        />
        <path
          fill="#EA4335"
          d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58Z"
        />
      </svg>
      {t("continueWithGoogle")}
    </button>
  );
}

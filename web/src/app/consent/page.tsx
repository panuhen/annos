"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { useTranslations } from "next-intl";

import { AuthSheet } from "@/components/auth-sheet";

/**
 * The OAuth consent interstitial for MCP connections. Better Auth sends the
 * user here after sign-in with consent_code / client_id / scope in the query
 * (see the mcp() oidcConfig.consentPage in lib/auth.ts). Approving POSTs the
 * consent code back and follows the returned redirect to finish the OAuth
 * hand-off; denying returns the client an access_denied error.
 *
 * Its second job is branding: this page's origin, favicon and Annos mark are
 * what the connecting client (Claude.ai) shows for the connector.
 */
function ConsentInner() {
  const t = useTranslations("auth");
  const params = useSearchParams();
  const clientId = params.get("client_id") ?? "";
  const consentCode = params.get("consent_code") ?? "";

  const [clientName, setClientName] = useState<string>(t("consentApp"));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The connecting app's self-reported name, so the sheet can name who it is.
  // A failure just leaves the generic label — never blocks the decision.
  useEffect(() => {
    if (!clientId) return;
    fetch(`/api/auth/mcp/client-info?client_id=${encodeURIComponent(clientId)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.name) setClientName(data.name);
      })
      .catch(() => {});
  }, [clientId]);

  async function decide(accept: boolean) {
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/oauth2/consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept, consent_code: consentCode }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      // A full navigation: the redirect leaves this origin for the OAuth
      // continuation, so hand it to the browser, not the client router.
      if (data.redirectURI) {
        window.location.href = data.redirectURI;
        return;
      }
      throw new Error();
    } catch {
      setError(t("consentError"));
      setPending(false);
    }
  }

  return (
    <AuthSheet title={t("consentTitle")}>
      <p className="text-base">
        {t.rich("consentIntro", {
          client: clientName,
          strong: (chunks) => (
            <span className="font-bold text-foreground">{chunks}</span>
          ),
        })}
      </p>
      <p className="mt-4 text-sm text-muted-foreground">{t("consentGrants")}</p>
      <p className="mt-2 text-sm text-muted-foreground">{t("consentEmail")}</p>

      {error && (
        <p className="mt-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="mt-6 flex flex-col gap-2">
        <button
          type="button"
          onClick={() => decide(true)}
          disabled={pending}
          className="flex min-h-12 items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending ? t("authorizing") : t("allow")}
        </button>
        <button
          type="button"
          onClick={() => decide(false)}
          disabled={pending}
          className="flex min-h-12 items-center justify-center border border-foreground font-bold text-foreground hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {t("deny")}
        </button>
      </div>
    </AuthSheet>
  );
}

export default function ConsentPage() {
  return (
    <Suspense>
      <ConsentInner />
    </Suspense>
  );
}

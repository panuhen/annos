"use client";

import { useTranslations } from "next-intl";

/** The CC BY attribution — mandatory wherever Fineli data can appear. */
export function FineliFooter({ className }: { className?: string }) {
  const t = useTranslations("footer");
  return (
    <footer className={className}>
      {t("prefix")}{" "}
      <a href="https://fineli.fi" rel="license noopener" className="underline">
        Fineli
      </a>
      , {t("institute")},{" "}
      <a
        href="https://creativecommons.org/licenses/by/4.0/"
        rel="license noopener"
        className="underline"
      >
        CC BY 4.0
      </a>
      .
    </footer>
  );
}

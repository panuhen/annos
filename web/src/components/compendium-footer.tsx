"use client";

import { useTranslations } from "next-intl";

/** Attribution for the MET activity catalog — the exercise counterpart to the
 * Fineli credit. Cited wherever the Fineli data is, per the same courtesy;
 * the citation itself stays in English (the Compendium ships English only). */
export function CompendiumFooter({ className }: { className?: string }) {
  const t = useTranslations("footer");
  return (
    <p className={className}>
      {t("activityPrefix")} 2024 Adult Compendium of Physical Activities (Herrmann et al.),{" "}
      <a href="https://pacompendium.com" rel="noopener" className="underline">
        pacompendium.com
      </a>
      .
    </p>
  );
}

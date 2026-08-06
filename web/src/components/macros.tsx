"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api/client";
import { useProfile } from "@/lib/profile";

/** The reading preference lives on the profile beside the language choices,
 * so it follows the account to any device — and one control serves every
 * view that prints the macro lines. */
export function MacrosToggle() {
  const profile = useProfile();
  const queryClient = useQueryClient();
  const t = useTranslations("macros");
  const [saving, setSaving] = useState(false);

  async function toggle() {
    setSaving(true);
    try {
      const { error } = await api.PATCH("/api/profile", {
        body: { changes: { show_item_macros: !profile.show_item_macros } },
      });
      if (error) throw error;
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
    } catch {
      toast.error(t("prefFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex justify-end">
      <button
        type="button"
        disabled={saving}
        onClick={toggle}
        className="-my-1.5 flex min-h-11 items-center font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
      >
        {t(profile.show_item_macros ? "hide" : "show")}
      </button>
    </div>
  );
}

/** One food's macro line in the faded administrative voice. Honors the
 * profile preference itself, so call sites never re-implement the gate.
 * Values are the portion's; a null fiber prints nothing rather than a
 * fabricated zero. */
export function MacroLine({
  protein,
  carbs,
  fat,
  fiber,
}: {
  protein: number | null | undefined;
  carbs: number | null | undefined;
  fat: number | null | undefined;
  fiber: number | null | undefined;
}) {
  const profile = useProfile();
  const t = useTranslations("macros");
  if (!profile.show_item_macros || protein == null || carbs == null || fat == null) return null;
  return (
    <p className="tnum font-mono text-xs text-muted-foreground">
      {t("line", {
        protein: Math.round(protein),
        carbs: Math.round(carbs),
        fat: Math.round(fat),
      })}
      {fiber != null && t("fiber", { fiber: Math.round(fiber) })}
    </p>
  );
}

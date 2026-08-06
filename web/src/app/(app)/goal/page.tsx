"use client";

import { CaretDown, CaretRight } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api/client";
import { $api } from "@/lib/api/hooks";
import { localeFor, rateFigure, sheetDate } from "@/lib/format";

const KINDS = ["deficit", "maintenance", "surplus"] as const;

/** Phases append and close: a new one closes the old the day before it
 * starts, and history is always judged against the phase in force then. */
export default function GoalPage() {
  const queryClient = useQueryClient();
  const t = useTranslations("goal");
  const tKinds = useTranslations("kinds");
  const locale = localeFor(useLocale());

  const summary = $api.useQuery("get", "/api/summary/daily", { params: { query: {} } });
  const target = summary.data?.target;
  // Past phases stay off the sheet until asked for — the active target above
  // is the goal; the ledger is for the "how did I get here" question.
  const [historyOpen, setHistoryOpen] = useState(false);
  const history = $api.useQuery("get", "/api/goals/phases", {}, { enabled: historyOpen });
  // Only closed phases hide behind the chevron — the active phase is the
  // target block above, always on the sheet.
  const phases = (history.data?.phases ?? []).filter((phase) => phase.end_date != null);

  const [kind, setKind] = useState("deficit");
  const [kcalTraining, setKcalTraining] = useState("");
  const [kcalRest, setKcalRest] = useState("");
  const [proteinTraining, setProteinTraining] = useState("");
  const [proteinRest, setProteinRest] = useState("");
  const [rate, setRate] = useState("");
  const [startDate, setStartDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // The open phase is a draft of the future and revisable; closed phases are
  // history. Revising reuses the form, prefilled from the open phase.
  const [revising, setRevising] = useState(false);

  const valid =
    parseInt(kcalTraining) > 0 &&
    parseInt(kcalRest) > 0 &&
    parseInt(proteinTraining) > 0 &&
    parseInt(proteinRest) > 0;

  const kindLabel = (value: string) =>
    (KINDS as readonly string[]).includes(value) ? tKinds(value) : value;

  async function startRevising() {
    const { data } = await api.GET("/api/goals/phases");
    const open = data?.phases.find((phase) => phase.end_date == null);
    if (!open) {
      toast(t("noPhase"));
      return;
    }
    setKind(open.kind);
    setKcalTraining(String(open.kcal_target_training));
    setKcalRest(String(open.kcal_target_rest));
    setProteinTraining(String(open.protein_target_training));
    setProteinRest(String(open.protein_target_rest));
    // The field holds the magnitude; the sign is drawn from the kind.
    setRate(
      open.rate_target_kg_per_week != null ? String(Math.abs(open.rate_target_kg_per_week)) : "",
    );
    setStartDate(open.start_date);
    setNotice(null);
    setRevising(true);
  }

  function stopRevising() {
    setRevising(false);
    setKind("deficit");
    setKcalTraining("");
    setKcalRest("");
    setProteinTraining("");
    setProteinRest("");
    setRate("");
    setStartDate("");
  }

  async function submit() {
    setSubmitting(true);
    try {
      // The user enters a magnitude; the sign is the kind's meaning
      // (deficit loses, surplus gains) and maintenance carries no rate.
      const magnitude = Math.abs(parseFloat(rate));
      const payload = {
        kind,
        kcal_training: parseInt(kcalTraining),
        kcal_rest: parseInt(kcalRest),
        protein_training: parseInt(proteinTraining),
        protein_rest: parseInt(proteinRest),
        rate_target:
          kind === "maintenance" || rate.trim() === "" || !(magnitude > 0)
            ? null
            : kind === "deficit"
              ? -magnitude
              : magnitude,
      };
      const { data, error } = revising
        ? await api.PATCH("/api/goals/phase", {
            body: { changes: { ...payload, ...(startDate ? { start_date: startDate } : {}) } },
          })
        : await api.POST("/api/goals/phase", {
            body: { ...payload, start_date: startDate === "" ? null : startDate },
          });
      if (error || !data) throw error ?? new Error("no response");
      setNotice(
        t(revising ? "revised" : "opened", { date: sheetDate(data.start_date, locale) }),
      );
      if (revising) stopRevising();
      await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
      await queryClient.invalidateQueries({ queryKey: ["get", "/api/goals/phases"] });
    } catch (err) {
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : undefined;
      toast.error(t("failed"), { description: detail });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <header className="border-b-2 border-foreground pt-5 pb-2">
        <h1 className="text-lg font-bold">{t("title")}</h1>
      </header>

      {/* What today is judged against */}
      <div className="mt-4 border-b border-border pb-4">
        {summary.isPending ? (
          <p className="text-sm text-muted-foreground">{t("reading")}</p>
        ) : target ? (
          <>
            <p className="text-sm font-bold">{kindLabel(target.kind)}</p>
            <p className="tnum mt-1 font-mono text-sm">
              {t("targetLine", { kcal: target.kcal, protein: target.protein_g })}
              {target.rate_kg_per_week != null &&
                t("rateSuffix", { rate: rateFigure(target.rate_kg_per_week, locale) })}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("targetToday", {
                dayType: summary.data?.day_type === "rest" ? t("restDay") : t("trainingDay"),
              })}{" "}
              {t("closesOld")}
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noPhase")}</p>
        )}
        {target && !revising && (
          <button
            type="button"
            onClick={startRevising}
            className="mt-1 flex min-h-11 items-center font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
          >
            {t("revisePhase")}
          </button>
        )}
      </div>

      {notice && (
        <p className="stamp-in mt-4 border border-border px-3 py-2 text-sm" role="status">
          {notice}
        </p>
      )}

      <div className="mt-5 flex items-baseline justify-between">
        <h2 className="text-sm font-bold">{t(revising ? "revisePhase" : "newPhase")}</h2>
        {revising && (
          <button
            type="button"
            onClick={stopRevising}
            className="font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
          >
            {t("cancelRevise")}
          </button>
        )}
      </div>

      <div className="mt-3">
        <Label htmlFor="goal-kind" className="mb-1.5 font-mono text-xs uppercase">
          {t("kind")}
        </Label>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger id="goal-kind" className="h-11 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {KINDS.map((value) => (
              <SelectItem key={value} value={value}>
                {tKinds(value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="kcal-rest" className="mb-1.5 font-mono text-xs uppercase">
            {t("kcalRest")}
          </Label>
          <Input
            id="kcal-rest"
            inputMode="numeric"
            value={kcalRest}
            onChange={(e) => setKcalRest(e.target.value)}
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="kcal-training" className="mb-1.5 font-mono text-xs uppercase">
            {t("kcalTraining")}
          </Label>
          <Input
            id="kcal-training"
            inputMode="numeric"
            value={kcalTraining}
            onChange={(e) => setKcalTraining(e.target.value)}
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="protein-rest" className="mb-1.5 font-mono text-xs uppercase">
            {t("proteinRest")}
          </Label>
          <Input
            id="protein-rest"
            inputMode="numeric"
            value={proteinRest}
            onChange={(e) => setProteinRest(e.target.value)}
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="protein-training" className="mb-1.5 font-mono text-xs uppercase">
            {t("proteinTraining")}
          </Label>
          <Input
            id="protein-training"
            inputMode="numeric"
            value={proteinTraining}
            onChange={(e) => setProteinTraining(e.target.value)}
            className="tnum h-11 text-right font-mono"
          />
        </div>
        {/* Maintenance holds weight: no rate to state. For the others the
         * user enters a magnitude and the sign is printed by the kind. */}
        {kind !== "maintenance" && (
          <div>
            <Label htmlFor="rate-target" className="mb-1.5 font-mono text-xs uppercase">
              {t(kind === "deficit" ? "rateLoss" : "rateGain")}
            </Label>
            <div className="relative">
              <span
                aria-hidden
                className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 font-mono text-sm text-muted-foreground"
              >
                {kind === "deficit" ? "−" : "+"}
              </span>
              <Input
                id="rate-target"
                inputMode="decimal"
                value={rate}
                onChange={(e) => setRate(e.target.value.replace(/[+\-−]/g, ""))}
                placeholder={t("optional")}
                className="tnum h-11 pl-7 text-right font-mono"
              />
            </div>
          </div>
        )}
      </div>

      <div className="mt-3">
        <Label htmlFor="start-date" className="mb-1.5 font-mono text-xs uppercase">
          {t(revising ? "startsKeep" : "starts")}
        </Label>
        <Input
          id="start-date"
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="tnum h-11 font-mono"
        />
      </div>

      <p className="mt-3 text-xs text-muted-foreground">{t("restNote")}</p>

      {/* The ledger: phases append and close, so this list is the goal
       * history — kept off the sheet until asked for. */}
      <section className="mt-6">
        <button
          type="button"
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen(!historyOpen)}
          className="flex min-h-11 items-center gap-1.5 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
        >
          {historyOpen ? (
            <CaretDown aria-hidden className="size-3.5" />
          ) : (
            <CaretRight aria-hidden className="size-3.5" />
          )}
          {historyOpen ? t("hidePhases") : t("showPhases")}
        </button>
        {historyOpen &&
          (history.isPending ? (
            <p className="pb-2 text-sm text-muted-foreground">{t("reading")}</p>
          ) : phases.length > 0 ? (
            <ul>
              {phases.map((phase) => (
                <li key={phase.phase_id} className="border-t border-border py-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-sm font-bold">{kindLabel(phase.kind)}</span>
                    <span className="tnum font-mono text-xs text-muted-foreground">
                      {sheetDate(phase.start_date, locale)}
                      {" – "}
                      {phase.end_date ? sheetDate(phase.end_date, locale) : t("ongoing")}
                    </span>
                  </div>
                  <p className="tnum mt-1 font-mono text-xs text-muted-foreground">
                    {t("phaseTargets", {
                      kcalRest: phase.kcal_target_rest,
                      kcalTraining: phase.kcal_target_training,
                      proteinRest: phase.protein_target_rest,
                      proteinTraining: phase.protein_target_training,
                    })}
                    {phase.rate_target_kg_per_week != null &&
                      t("rateSuffix", {
                        rate: rateFigure(phase.rate_target_kg_per_week, locale),
                      })}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="pb-2 text-sm text-muted-foreground">{t("noPhases")}</p>
          ))}
      </section>

      <div className="sticky bottom-[4.5rem] lg:bottom-4 mt-6 bg-background pb-1">
        <button
          type="button"
          disabled={!valid || submitting}
          onClick={submit}
          className="flex min-h-12 w-full items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? t("opening") : t(revising ? "saveRevision" : "submit")}
        </button>
      </div>
    </>
  );
}

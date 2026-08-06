"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import { localeFor, sheetDate } from "@/lib/format";
import { useProfile } from "@/lib/profile";

/** Morning ritual: step on the scale, type one number. Re-logging the same
 * day replaces only the fields sent — waist in the evening keeps the
 * morning's weight. */
export default function WeightPage() {
  const profile = useProfile();
  const queryClient = useQueryClient();
  const locale = localeFor(profile.language);

  const [weight, setWeight] = useState("");
  const [waist, setWaist] = useState("");
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState(""); // empty = today, server-defined
  const [submitting, setSubmitting] = useState(false);
  const [logged, setLogged] = useState<{ date: string; weight_kg: number | null } | null>(null);

  const valid = weight.trim() !== "" || waist.trim() !== "" || notes.trim() !== "";

  async function submit() {
    setSubmitting(true);
    try {
      const { data, error } = await api.POST("/api/logs/weight", {
        body: {
          weight_kg: weight.trim() === "" ? null : parseFloat(weight),
          waist_cm: waist.trim() === "" ? null : parseFloat(waist),
          notes: notes.trim() === "" ? null : notes.trim(),
          date: date === "" ? null : date,
        },
      });
      if (error || !data) throw error ?? new Error("no response");
      setLogged({ date: data.date, weight_kg: data.weight_kg });
      setWeight("");
      setWaist("");
      setNotes("");
      setDate("");
      await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
    } catch (err) {
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : "The kitchen did not answer. Try again.";
      toast.error("Could not log the measurement", { description: detail });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <header className="border-b-2 border-foreground pt-5 pb-2">
        <h1 className="text-lg font-bold">Weight</h1>
      </header>

      {logged && (
        <p className="stamp-in mt-4 border border-border px-3 py-2 text-sm" role="status">
          Logged{logged.weight_kg != null && <> <span className="tnum font-mono">{logged.weight_kg}</span> kg</>} for{" "}
          <span className="font-mono">{sheetDate(logged.date, locale)}</span>. Same day, new
          number? Log again — it replaces.
        </p>
      )}

      <div className="mt-5 grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="weight-kg" className="mb-1.5 font-mono text-xs uppercase">
            Weight, kg
          </Label>
          <Input
            id="weight-kg"
            inputMode="decimal"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
            placeholder=""
            className="tnum h-12 text-right font-mono text-base"
            autoFocus
          />
        </div>
        <div>
          <Label htmlFor="waist-cm" className="mb-1.5 font-mono text-xs uppercase">
            Waist, cm
          </Label>
          <Input
            id="waist-cm"
            inputMode="decimal"
            value={waist}
            onChange={(e) => setWaist(e.target.value)}
            placeholder="optional"
            className="tnum h-12 text-right font-mono text-base"
          />
        </div>
      </div>

      <div className="mt-3">
        <Label htmlFor="weight-date" className="mb-1.5 font-mono text-xs uppercase">
          Day — leave empty for today
        </Label>
        <Input
          id="weight-date"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="tnum h-11 font-mono"
        />
      </div>

      <div className="mt-3">
        <Label htmlFor="weight-notes" className="mb-1.5 font-mono text-xs uppercase">
          Notes
        </Label>
        <Textarea
          id="weight-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Slept badly, salty dinner…"
        />
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        The number is stored as-is. Trends and smoothing come later — a
        single morning is weather, not climate.
      </p>

      <div className="sticky bottom-[4.5rem] lg:bottom-4 mt-6 bg-background pb-1">
        <button
          type="button"
          disabled={!valid || submitting}
          onClick={submit}
          className="flex min-h-12 w-full items-center justify-center gap-2 bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? "Logging…" : "Log measurement"}
        </button>
      </div>
    </>
  );
}

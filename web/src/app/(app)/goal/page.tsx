"use client";

import { useQueryClient } from "@tanstack/react-query";
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
import { $api } from "@/lib/api/hooks";
import { api } from "@/lib/api/client";
import { localeFor, sheetDate } from "@/lib/format";
import { useProfile } from "@/lib/profile";

const KIND_LABELS: Record<string, string> = {
  deficit: "Deficit — losing",
  maintenance: "Maintenance — holding",
  surplus: "Surplus — gaining",
};

/** Phases append and close: a new one closes the old the day before it
 * starts, and history is always judged against the phase in force then. */
export default function GoalPage() {
  const profile = useProfile();
  const queryClient = useQueryClient();
  const locale = localeFor(profile.language);

  const summary = $api.useQuery("get", "/api/summary/daily", { params: { query: {} } });
  const target = summary.data?.target;

  const [kind, setKind] = useState("deficit");
  const [kcalTraining, setKcalTraining] = useState("");
  const [kcalRest, setKcalRest] = useState("");
  const [protein, setProtein] = useState("");
  const [rate, setRate] = useState("");
  const [startDate, setStartDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [opened, setOpened] = useState<{ start_date: string } | null>(null);

  const valid =
    parseInt(kcalTraining) > 0 && parseInt(kcalRest) > 0 && parseInt(protein) > 0;

  async function submit() {
    setSubmitting(true);
    try {
      const { data, error } = await api.POST("/api/goals/phase", {
        body: {
          kind,
          kcal_training: parseInt(kcalTraining),
          kcal_rest: parseInt(kcalRest),
          protein_g: parseInt(protein),
          rate_target: rate.trim() === "" ? null : parseFloat(rate),
          start_date: startDate === "" ? null : startDate,
        },
      });
      if (error || !data) throw error ?? new Error("no response");
      setOpened({ start_date: data.start_date });
      await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
    } catch (err) {
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : "The kitchen did not answer. Try again.";
      toast.error("Could not open the phase", { description: detail });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <header className="border-b-2 border-foreground pt-5 pb-2">
        <h1 className="text-lg font-bold">Goal phase</h1>
      </header>

      {/* What today is judged against */}
      <div className="mt-4 border-b border-border pb-4">
        {summary.isPending ? (
          <p className="text-sm text-muted-foreground">Reading the current phase…</p>
        ) : target ? (
          <>
            <p className="text-sm font-bold">{KIND_LABELS[target.kind] ?? target.kind}</p>
            <p className="tnum mt-1 font-mono text-sm">
              {target.kcal} kcal · {target.protein_g} g protein
              {target.rate_kg_per_week != null && <> · {target.rate_kg_per_week} kg/week</>}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Target for today ({summary.data?.day_type === "rest" ? "rest day" : "training day"}).
              Opening a new phase closes this one the day before the new start — past days keep
              their old target.
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            No phase is open. Days are logged without a target until one starts.
          </p>
        )}
      </div>

      {opened && (
        <p className="stamp-in mt-4 border border-border px-3 py-2 text-sm" role="status">
          Phase opened from <span className="font-mono">{sheetDate(opened.start_date, locale)}</span>.
        </p>
      )}

      <h2 className="mt-5 text-sm font-bold">Open a new phase</h2>

      <div className="mt-3">
        <Label htmlFor="goal-kind" className="mb-1.5 font-mono text-xs uppercase">
          Kind
        </Label>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger id="goal-kind" className="h-11 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(KIND_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="kcal-rest" className="mb-1.5 font-mono text-xs uppercase">
            Rest-day kcal
          </Label>
          <Input
            id="kcal-rest"
            inputMode="numeric"
            value={kcalRest}
            onChange={(e) => setKcalRest(e.target.value)}
            placeholder=""
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="kcal-training" className="mb-1.5 font-mono text-xs uppercase">
            Training-day kcal
          </Label>
          <Input
            id="kcal-training"
            inputMode="numeric"
            value={kcalTraining}
            onChange={(e) => setKcalTraining(e.target.value)}
            placeholder=""
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="protein-g" className="mb-1.5 font-mono text-xs uppercase">
            Protein, g/day
          </Label>
          <Input
            id="protein-g"
            inputMode="numeric"
            value={protein}
            onChange={(e) => setProtein(e.target.value)}
            placeholder=""
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="rate-target" className="mb-1.5 font-mono text-xs uppercase">
            Rate, kg/week
          </Label>
          <Input
            id="rate-target"
            inputMode="decimal"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            placeholder="optional"
            className="tnum h-11 text-right font-mono"
          />
        </div>
      </div>

      <div className="mt-3">
        <Label htmlFor="start-date" className="mb-1.5 font-mono text-xs uppercase">
          Starts — leave empty for today
        </Label>
        <Input
          id="start-date"
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="tnum h-11 font-mono"
        />
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        Until exercise logging exists every day uses the rest-day target, and the
        sheet says so.
      </p>

      <div className="sticky bottom-[4.5rem] lg:bottom-4 mt-6 bg-background pb-1">
        <button
          type="button"
          disabled={!valid || submitting}
          onClick={submit}
          className="flex min-h-12 w-full items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? "Opening…" : "Open phase"}
        </button>
      </div>
    </>
  );
}

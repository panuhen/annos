"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Monitor, Moon, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useState, useSyncExternalStore } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import { clearApiToken } from "@/lib/api/token";
import { authClient } from "@/lib/auth-client";
import { useProfile } from "@/lib/profile";
import { cn } from "@/lib/utils";

const LANGUAGES = [
  { value: "fi", label: "suomi" },
  { value: "sv", label: "svenska" },
  { value: "en", label: "English" },
];

export default function ProfilePage() {
  const profile = useProfile();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [language, setLanguage] = useState(profile.language);
  const [timezone, setTimezone] = useState(profile.timezone);
  const [birthYear, setBirthYear] = useState(profile.birth_year?.toString() ?? "");
  const [height, setHeight] = useState(profile.height_cm?.toString() ?? "");
  const [sex, setSex] = useState(profile.sex ?? "unset");
  const [coachingNotes, setCoachingNotes] = useState(profile.coaching_notes ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    const changes: Record<string, unknown> = {};
    if (language !== profile.language) changes.language = language;
    if (timezone !== profile.timezone) changes.timezone = timezone;
    const by = birthYear.trim() === "" ? null : parseInt(birthYear);
    if (by !== profile.birth_year) changes.birth_year = by;
    const h = height.trim() === "" ? null : parseInt(height);
    if (h !== profile.height_cm) changes.height_cm = h;
    const s = sex === "unset" ? null : sex;
    if (s !== profile.sex) changes.sex = s;
    const notes = coachingNotes.trim() === "" ? null : coachingNotes.trim();
    if (notes !== profile.coaching_notes) changes.coaching_notes = notes;

    if (Object.keys(changes).length === 0) {
      toast("Nothing changed.");
      setSaving(false);
      return;
    }
    try {
      const { data, error } = await api.PATCH("/api/profile", { body: { changes } });
      if (error || !data) throw error ?? new Error("no response");
      await queryClient.invalidateQueries();
      toast("Saved.");
    } catch (err) {
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : "The API did not answer. Try again.";
      toast.error("Could not save", { description: detail });
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    await authClient.signOut();
    clearApiToken();
    queryClient.clear();
    router.replace("/sign-in");
  }

  return (
    <>
      <header className="border-b-2 border-foreground pt-5 pb-2">
        <h1 className="text-lg font-bold">Profile</h1>
      </header>

      <div className="mt-4 flex items-baseline justify-between border-b border-border pb-4">
        <span className="font-mono text-lg font-bold break-all">{profile.nickname}</span>
        <span className="ml-3 shrink-0 font-mono text-xs text-muted-foreground">permanent</span>
      </div>

      <ThemeRow />

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="language" className="mb-1.5 font-mono text-xs uppercase">
            Food names in
          </Label>
          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger id="language" className="h-11 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LANGUAGES.map(({ value, label }) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="timezone" className="mb-1.5 font-mono text-xs uppercase">
            Timezone
          </Label>
          <Input
            id="timezone"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            autoComplete="off"
            className="h-11 font-mono text-sm"
          />
        </div>
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">
        The timezone decides when your day rolls over — a 00:30 snack belongs
        to the new day.
      </p>

      <h2 className="mt-6 text-sm font-bold">Body facts</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Optional. Used for energy arithmetic later; never judged.
      </p>
      <div className="mt-3 grid grid-cols-3 gap-3">
        <div>
          <Label htmlFor="birth-year" className="mb-1.5 font-mono text-xs uppercase">
            Born
          </Label>
          <Input
            id="birth-year"
            inputMode="numeric"
            value={birthYear}
            onChange={(e) => setBirthYear(e.target.value)}
            placeholder=""
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="height-cm" className="mb-1.5 font-mono text-xs uppercase">
            Height cm
          </Label>
          <Input
            id="height-cm"
            inputMode="numeric"
            value={height}
            onChange={(e) => setHeight(e.target.value)}
            placeholder=""
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="sex" className="mb-1.5 font-mono text-xs uppercase">
            Sex
          </Label>
          <Select value={sex} onValueChange={setSex}>
            <SelectTrigger id="sex" className="h-11 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unset">—</SelectItem>
              <SelectItem value="female">female</SelectItem>
              <SelectItem value="male">male</SelectItem>
              <SelectItem value="other">other</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="mt-4">
        <Label htmlFor="coaching-notes" className="mb-1.5 font-mono text-xs uppercase">
          Coaching notes
        </Label>
        <Textarea
          id="coaching-notes"
          value={coachingNotes}
          onChange={(e) => setCoachingNotes(e.target.value)}
          rows={3}
          placeholder="In your own words — your AI reads this with every summary."
        />
      </div>

      <button
        type="button"
        onClick={save}
        disabled={saving}
        className="mt-5 flex min-h-12 w-full items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
      >
        {saving ? "Saving…" : "Save changes"}
      </button>

      <button
        type="button"
        onClick={signOut}
        className="mt-3 flex min-h-12 w-full items-center justify-center border border-input font-bold hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        Sign out
      </button>
    </>
  );
}

/** Both themes are first-class; the toggle is three-way with system default. */
const emptySubscribe = () => () => {};

function ThemeRow() {
  const { theme, setTheme } = useTheme();
  // Theme is unknowable server-side; render the toggle neutral until hydrated.
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const options = [
    { value: "light", label: "Light", icon: Sun },
    { value: "system", label: "System", icon: Monitor },
    { value: "dark", label: "Dark", icon: Moon },
  ] as const;

  return (
    <div className="mt-4">
      <span className="mb-1.5 block font-mono text-xs uppercase text-muted-foreground">
        Theme
      </span>
      <div role="radiogroup" aria-label="Theme" className="flex border border-input">
        {options.map(({ value, label, icon: Icon }) => {
          const active = mounted && theme === value;
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setTheme(value)}
              className={cn(
                "flex min-h-11 flex-1 items-center justify-center gap-1.5 text-sm",
                active
                  ? "bg-foreground font-bold text-background"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              <Icon aria-hidden className="size-4" />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

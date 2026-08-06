"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CaretDown, CaretRight, Monitor, Moon, Sun } from "@phosphor-icons/react";
import { useLocale, useTranslations } from "next-intl";
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
import { LOCALE_COOKIE, LOCALES } from "@/i18n/config";
import { api } from "@/lib/api/client";
import { $api } from "@/lib/api/hooks";
import { clearApiToken } from "@/lib/api/token";
import { authClient } from "@/lib/auth-client";
import { clockTime, localeFor, sheetDate } from "@/lib/format";
import { useProfile } from "@/lib/profile";
import { cn } from "@/lib/utils";

/** Language names stay in their own language — a Finn lost in a Swedish UI
 * still finds "suomi". */
const LANGUAGE_NAMES: Record<string, string> = {
  fi: "suomi",
  sv: "svenska",
  en: "English",
};

export default function ProfilePage() {
  const profile = useProfile();
  const router = useRouter();
  const queryClient = useQueryClient();
  const t = useTranslations("profile");
  const appLocale = useLocale();

  const [foodLanguage, setFoodLanguage] = useState(profile.language);
  const [timezone, setTimezone] = useState(profile.timezone);
  const [birthYear, setBirthYear] = useState(profile.birth_year?.toString() ?? "");
  const [height, setHeight] = useState(profile.height_cm?.toString() ?? "");
  const [sex, setSex] = useState(profile.sex ?? "unset");
  const [coachingNotes, setCoachingNotes] = useState(profile.coaching_notes ?? "");
  const [saving, setSaving] = useState(false);

  /** App language persists on the profile (`ui_language`) so it follows the
   * user across devices, and applies immediately via the cookie the server
   * renders from. Food-name language is `language` — saved with the form,
   * shared with the MCP surface. */
  async function setAppLanguage(locale: string) {
    document.cookie = `${LOCALE_COOKIE}=${locale};path=/;max-age=31536000;samesite=lax`;
    router.refresh();
    const { data } = await api.PATCH("/api/profile", {
      body: { changes: { ui_language: locale } },
    });
    if (data) {
      queryClient.setQueryData(["profile"], data);
    } else {
      // The cookie already switched this browser; only persistence failed.
      toast.error(t("saveFailed"), { description: t("apiNoAnswer") });
    }
  }

  async function save() {
    setSaving(true);
    const changes: Record<string, unknown> = {};
    if (foodLanguage !== profile.language) changes.language = foodLanguage;
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
      toast(t("nothingChanged"));
      setSaving(false);
      return;
    }
    try {
      const { data, error } = await api.PATCH("/api/profile", { body: { changes } });
      if (error || !data) throw error ?? new Error("no response");
      await queryClient.invalidateQueries();
      toast(t("saved"));
    } catch (err) {
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : t("apiNoAnswer");
      toast.error(t("saveFailed"), { description: detail });
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
        <h1 className="text-lg font-bold">{t("title")}</h1>
      </header>

      <div className="mt-4 flex items-baseline justify-between border-b border-border pb-4">
        <span className="font-mono text-lg font-bold break-all">{profile.nickname}</span>
        <span className="ml-3 shrink-0 font-mono text-xs text-muted-foreground">
          {t("permanent")}
        </span>
      </div>

      <ThemeRow />

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="app-language" className="mb-1.5 font-mono text-xs uppercase">
            {t("appLanguage")}
          </Label>
          <Select value={appLocale} onValueChange={setAppLanguage}>
            <SelectTrigger id="app-language" className="h-11 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOCALES.map((value) => (
                <SelectItem key={value} value={value}>
                  {LANGUAGE_NAMES[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="food-language" className="mb-1.5 font-mono text-xs uppercase">
            {t("foodLanguage")}
          </Label>
          <Select value={foodLanguage} onValueChange={setFoodLanguage}>
            <SelectTrigger id="food-language" className="h-11 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOCALES.map((value) => (
                <SelectItem key={value} value={value}>
                  {LANGUAGE_NAMES[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="mt-3">
        <Label htmlFor="timezone" className="mb-1.5 font-mono text-xs uppercase">
          {t("timezone")}
        </Label>
        <Input
          id="timezone"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          autoComplete="off"
          className="h-11 font-mono text-sm"
        />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{t("tzNote")}</p>

      <h2 className="mt-6 text-sm font-bold">{t("bodyFacts")}</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">{t("bodyNote")}</p>
      <div className="mt-3 grid grid-cols-3 gap-3">
        <div>
          <Label htmlFor="birth-year" className="mb-1.5 font-mono text-xs uppercase">
            {t("born")}
          </Label>
          <Input
            id="birth-year"
            inputMode="numeric"
            value={birthYear}
            onChange={(e) => setBirthYear(e.target.value)}
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="height-cm" className="mb-1.5 font-mono text-xs uppercase">
            {t("height")}
          </Label>
          <Input
            id="height-cm"
            inputMode="numeric"
            value={height}
            onChange={(e) => setHeight(e.target.value)}
            className="tnum h-11 text-right font-mono"
          />
        </div>
        <div>
          <Label htmlFor="sex" className="mb-1.5 font-mono text-xs uppercase">
            {t("sex")}
          </Label>
          <Select value={sex} onValueChange={setSex}>
            <SelectTrigger id="sex" className="h-11 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unset">—</SelectItem>
              <SelectItem value="female">{t("female")}</SelectItem>
              <SelectItem value="male">{t("male")}</SelectItem>
              <SelectItem value="other">{t("other")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="mt-4">
        <Label htmlFor="coaching-notes" className="mb-1.5 font-mono text-xs uppercase">
          {t("coachingNotes")}
        </Label>
        <Textarea
          id="coaching-notes"
          value={coachingNotes}
          onChange={(e) => setCoachingNotes(e.target.value)}
          rows={3}
          placeholder={t("coachingPlaceholder")}
        />
        <CoachingHistory />
      </div>

      <button
        type="button"
        onClick={save}
        disabled={saving}
        className="mt-5 flex min-h-12 w-full items-center justify-center bg-primary font-bold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-40"
      >
        {saving ? t("saving") : t("save")}
      </button>

      <button
        type="button"
        onClick={signOut}
        className="mt-3 flex min-h-12 w-full items-center justify-center border border-input font-bold hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        {t("signOut")}
      </button>
    </>
  );
}

/** The notes' past versions, fetched only when asked for — history never
 * rides along with the profile by default, on either surface. */
function CoachingHistory() {
  const profile = useProfile();
  const t = useTranslations("profile");
  const locale = localeFor(useLocale());
  const [open, setOpen] = useState(false);

  const history = $api.useQuery(
    "get",
    "/api/profile/coaching-history",
    {},
    { enabled: open },
  );

  return (
    <div className="mt-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex min-h-11 items-center gap-1.5 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
      >
        {open ? (
          <CaretDown aria-hidden className="size-3.5" />
        ) : (
          <CaretRight aria-hidden className="size-3.5" />
        )}
        {open ? t("hideNotesHistory") : t("showNotesHistory")}
      </button>
      {open &&
        (history.isPending ? (
          <p className="pb-2 text-sm text-muted-foreground">{t("historyReading")}</p>
        ) : history.data && history.data.revisions.length > 0 ? (
          <ul>
            {history.data.revisions.map((revision, i) => (
              <li key={i} className="border-t border-border py-2">
                <p className="font-mono text-xs text-muted-foreground tnum">
                  {sheetDate(revision.set_at.slice(0, 10), locale)}{" "}
                  {clockTime(revision.set_at, locale, profile.timezone)}
                </p>
                {revision.notes ? (
                  <p className="mt-0.5 text-sm">{revision.notes}</p>
                ) : (
                  <p className="mt-0.5 text-sm italic text-muted-foreground">
                    {t("notesCleared")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="pb-2 text-sm text-muted-foreground">{t("historyEmpty")}</p>
        ))}
    </div>
  );
}

const emptySubscribe = () => () => {};

/** Both themes are first-class; the toggle is three-way with system default. */
function ThemeRow() {
  const { theme, setTheme } = useTheme();
  const t = useTranslations("profile");
  // Theme is unknowable server-side; render the toggle neutral until hydrated.
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const options = [
    { value: "light", label: t("light"), icon: Sun },
    { value: "system", label: t("system"), icon: Monitor },
    { value: "dark", label: t("dark"), icon: Moon },
  ] as const;

  return (
    <div className="mt-4">
      <span className="mb-1.5 block font-mono text-xs uppercase text-muted-foreground">
        {t("theme")}
      </span>
      <div role="radiogroup" aria-label={t("theme")} className="flex border border-input">
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

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CaretDown, CaretRight } from "@phosphor-icons/react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { InfoTip } from "@/components/ui/info-tip";
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
import { $api } from "@/lib/api/hooks";
import { clearApiToken } from "@/lib/api/token";
import { authClient } from "@/lib/auth-client";
import { clockTime, localeFor, sheetDate } from "@/lib/format";
import { useProfile } from "@/lib/profile";

/** Closed lists instead of free text: the values are validated by being the
 * only ones offered. Ranges mirror the server's own checks. */
const CURRENT_YEAR = new Date().getFullYear();
const BIRTH_YEARS = Array.from({ length: CURRENT_YEAR - 1900 + 1 }, (_, i) =>
  String(CURRENT_YEAR - i),
);
const HEIGHTS_CM = Array.from({ length: 231 - 100 }, (_, i) => String(230 - i));

export default function ProfilePage() {
  const profile = useProfile();
  const router = useRouter();
  const queryClient = useQueryClient();
  const t = useTranslations("profile");

  const [birthYear, setBirthYear] = useState(profile.birth_year?.toString() ?? "");
  const [height, setHeight] = useState(profile.height_cm?.toString() ?? "");
  const [sex, setSex] = useState(profile.sex ?? "unset");
  const [coachingNotes, setCoachingNotes] = useState(profile.coaching_notes ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    const changes: Record<string, unknown> = {};
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

      <div className="mt-4 flex items-center justify-between border-b border-border pb-2">
        <span className="min-w-0 font-mono text-lg font-bold break-all">{profile.nickname}</span>
        <span className="ml-3 flex shrink-0 items-center gap-0.5 font-mono text-xs text-muted-foreground">
          {t("permanent")}
          {/* Why the name is nonsense — behind the glyph, where the
           * question arises but off the sheet until asked. */}
          <InfoTip label={t("nicknameWhy")}>{t("nicknameNote")}</InfoTip>
        </span>
      </div>

      <h2 className="mt-6 text-sm font-bold">{t("bodyFacts")}</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">{t("bodyNote")}</p>
      <div className="mt-3 grid grid-cols-3 gap-3">
        <div>
          <Label htmlFor="birth-year" className="mb-1.5 font-mono text-xs uppercase">
            {t("born")}
          </Label>
          <Select
            value={birthYear === "" ? "unset" : birthYear}
            onValueChange={(value) => setBirthYear(value === "unset" ? "" : value)}
          >
            <SelectTrigger id="birth-year" className="tnum h-11 w-full font-mono">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unset">—</SelectItem>
              {BIRTH_YEARS.map((year) => (
                <SelectItem key={year} value={year} className="tnum font-mono">
                  {year}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="height-cm" className="mb-1.5 font-mono text-xs uppercase">
            {t("height")}
          </Label>
          <Select
            value={height === "" ? "unset" : height}
            onValueChange={(value) => setHeight(value === "unset" ? "" : value)}
          >
            <SelectTrigger id="height-cm" className="tnum h-11 w-full font-mono">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unset">—</SelectItem>
              {HEIGHTS_CM.map((cm) => (
                <SelectItem key={cm} value={cm} className="tnum font-mono">
                  {cm}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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

      <DeleteAccount />
    </>
  );
}

/** The end of the account, off the sheet until asked for. Two confirmations,
 * each verified by the side it protects: the typed nickname is checked by
 * the API before it erases the Annos data, the password by Better Auth
 * before it removes the sign-in. The API goes first — its route only accepts
 * the web's own credential shape — and Better Auth's user row cascades the
 * sessions and OAuth grants when it falls. */
function DeleteAccount() {
  const profile = useProfile();
  const t = useTranslations("profile");
  const [open, setOpen] = useState(false);
  const [nickname, setNickname] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  // The Annos wipe succeeded but the sign-in still stands (wrong password):
  // don't wipe again on retry, and say plainly what state things are in.
  const [dataErased, setDataErased] = useState(false);

  const armed = nickname.trim() === profile.nickname && password !== "";

  async function destroy() {
    setBusy(true);
    try {
      if (!dataErased) {
        const { error } = await api.DELETE("/api/account", {
          body: { nickname: nickname.trim() },
        });
        if (error) throw error;
        setDataErased(true);
      }
      const { error } = await authClient.deleteUser({ password });
      if (error) {
        toast.error(t("deleteWrongPassword"));
        return;
      }
      clearApiToken();
      window.location.href = "/sign-in";
    } catch (err) {
      const detail =
        typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : undefined;
      toast.error(t("deleteFailed"), { description: detail });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-8 border-t border-border pt-1 pb-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex min-h-11 items-center gap-1.5 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-destructive"
      >
        {open ? (
          <CaretDown aria-hidden className="size-3.5" />
        ) : (
          <CaretRight aria-hidden className="size-3.5" />
        )}
        {t("deleteTitle")}
      </button>

      {open && (
        <div className="mt-1 space-y-3">
          <p className="text-xs text-muted-foreground">{t("deleteWarning")}</p>
          {dataErased && (
            <p className="border border-destructive px-3 py-2 text-xs text-destructive" role="alert">
              {t("deleteWrongPassword")}
            </p>
          )}
          <div>
            <Label htmlFor="delete-nickname" className="mb-1.5 font-mono text-xs uppercase">
              {t("deleteNicknameLabel")}
            </Label>
            <Input
              id="delete-nickname"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              placeholder={profile.nickname}
              autoComplete="off"
              className="h-11 font-mono"
            />
          </div>
          <div>
            <Label htmlFor="delete-password" className="mb-1.5 font-mono text-xs uppercase">
              {t("deletePasswordLabel")}
            </Label>
            <Input
              id="delete-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="h-11"
            />
          </div>
          <button
            type="button"
            disabled={!armed || busy}
            onClick={destroy}
            className="flex min-h-12 w-full items-center justify-center bg-destructive font-bold text-white hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-destructive disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? t("deleting") : t("deleteConfirm")}
          </button>
        </div>
      )}
    </div>
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
            {history.data.revisions.map((revision, i) => {
              // The newest revision is usually what's in force, but notes set
              // before history existed have no revision row — so the tag only
              // appears when the row really is the live text.
              const isCurrent =
                i === 0 && revision.notes === (profile.coaching_notes ?? null);
              return (
                <li key={i} className="border-t border-border py-2">
                  <p className="flex items-baseline justify-between font-mono text-xs text-muted-foreground tnum">
                    <span>
                      {sheetDate(revision.set_at.slice(0, 10), locale)}{" "}
                      {clockTime(revision.set_at, locale, profile.timezone)}
                    </span>
                    {isCurrent && <span className="ml-3 shrink-0">{t("currentNote")}</span>}
                  </p>
                  {revision.notes ? (
                    <p className="mt-0.5 text-sm">{revision.notes}</p>
                  ) : (
                    <p className="mt-0.5 text-sm italic text-muted-foreground">
                      {t("notesCleared")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="pb-2 text-sm text-muted-foreground">{t("historyEmpty")}</p>
        ))}
    </div>
  );
}


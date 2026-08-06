"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Monitor, Moon, Sun } from "@phosphor-icons/react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useState, useSyncExternalStore } from "react";
import { toast } from "sonner";

import { FineliFooter } from "@/components/fineli-footer";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LOCALE_COOKIE, LOCALES } from "@/i18n/config";
import { api } from "@/lib/api/client";
import { useProfile } from "@/lib/profile";
import { cn } from "@/lib/utils";

/** Language names stay in their own language — a Finn lost in a Swedish UI
 * still finds "Suomi". */
const LANGUAGE_NAMES: Record<string, string> = {
  fi: "Suomi",
  sv: "Svenska",
  en: "English",
};

/** The MCP endpoint is the API's public origin, which only deploy config
 * knows — the rewrite the web app uses internally is not the public URL. */
const MCP_URL = process.env.NEXT_PUBLIC_MCP_URL ?? "http://localhost:8000/mcp/";

/** "GMT+3" for Europe/Helsinki in summer — the current offset, DST included,
 * from the browser's own tz database. */
function gmtOffset(zone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en", {
      timeZone: zone,
      timeZoneName: "shortOffset",
    }).formatToParts(new Date());
    return parts.find((part) => part.type === "timeZoneName")?.value ?? "";
  } catch {
    return "";
  }
}

/** Computed once per page load: ~450 zones × formatToParts is too much work
 * to redo on every render. */
let tzOptionsCache: { zone: string; offset: string }[] | null = null;

function timezoneOptions(current: string): { zone: string; offset: string }[] {
  if (tzOptionsCache && tzOptionsCache.some((option) => option.zone === current)) {
    return tzOptionsCache;
  }
  let zones: string[];
  try {
    zones = Intl.supportedValuesOf("timeZone");
  } catch {
    zones = [];
  }
  if (!zones.includes(current)) zones = [current, ...zones];
  tzOptionsCache = zones.map((zone) => ({ zone, offset: gmtOffset(zone) }));
  return tzOptionsCache;
}

export default function SettingsPage() {
  const t = useTranslations("settings");

  return (
    <>
      <header className="border-b-2 border-foreground pt-5 pb-2">
        <h1 className="text-lg font-bold">{t("title")}</h1>
      </header>

      <section className="mt-4">
        <h2 className="text-sm font-bold">{t("preferences")}</h2>
        <ThemeRow />
        <LanguagesRow />
        <TimezoneRow />
      </section>

      <section className="mt-8 border-t border-border pt-4">
        <h2 className="text-sm font-bold">{t("mcpTitle")}</h2>
        <McpSection />
      </section>

      <section className="mt-8 border-t border-border pt-4 pb-4">
        <h2 className="text-sm font-bold">{t("aboutTitle")}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t("aboutBody")}</p>
        <FineliFooter className="mt-3 text-sm leading-relaxed text-muted-foreground" />
      </section>
    </>
  );
}

const emptySubscribe = () => () => {};

/** Both themes are first-class; the toggle is three-way with system default. */
function ThemeRow() {
  const { theme, setTheme } = useTheme();
  const t = useTranslations("settings");
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
    <div className="mt-3">
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

/** The two languages stay a deliberate pair: app chrome and food names are
 * separate settings — an English app can still show foods as ruisleipä.
 * Both apply on change. App language persists on the profile (`ui_language`)
 * and switches immediately via the cookie the server renders from; food-name
 * language is `language`, shared with the MCP surface. */
function LanguagesRow() {
  const t = useTranslations("settings");
  const appLocale = useLocale();
  const router = useRouter();
  const queryClient = useQueryClient();
  const profile = useProfile();

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
      toast.error(t("saveFailed"));
    }
  }

  async function setFoodLanguage(locale: string) {
    const { data, error } = await api.PATCH("/api/profile", {
      body: { changes: { language: locale } },
    });
    if (error || !data) {
      toast.error(t("saveFailed"));
      return;
    }
    queryClient.setQueryData(["profile"], data);
    // Food names resolve at read time everywhere — refetch the lot.
    await queryClient.invalidateQueries();
    toast(t("saved"));
  }

  return (
    <div className="mt-3 grid grid-cols-2 gap-3">
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
        <Select value={profile.language} onValueChange={setFoodLanguage}>
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
  );
}

/** Applies on change, like the other settings — no batch save here. The
 * summary invalidates too: the timezone decides where a day begins. */
function TimezoneRow() {
  const t = useTranslations("settings");
  const profile = useProfile();
  const queryClient = useQueryClient();

  async function setTimezone(zone: string) {
    const { data, error } = await api.PATCH("/api/profile", {
      body: { changes: { timezone: zone } },
    });
    if (error || !data) {
      toast.error(t("saveFailed"));
      return;
    }
    queryClient.setQueryData(["profile"], data);
    await queryClient.invalidateQueries({ queryKey: ["get", "/api/summary/daily"] });
    toast(t("saved"));
  }

  return (
    <div className="mt-3">
      <Label htmlFor="timezone" className="mb-1.5 font-mono text-xs uppercase">
        {t("timezone")}
      </Label>
      <Select value={profile.timezone} onValueChange={setTimezone}>
        <SelectTrigger id="timezone" className="h-11 w-full font-mono text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {timezoneOptions(profile.timezone).map(({ zone, offset }) => (
            <SelectItem key={zone} value={zone} className="font-mono text-sm">
              {zone}
              {offset && <span className="ml-2 text-xs text-muted-foreground">{offset}</span>}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="mt-1.5 text-xs text-muted-foreground">{t("tzNote")}</p>
    </div>
  );
}

/** Connect an AI client to Annos over MCP: the same account, the same data,
 * the tools acting as you. The web UI and the MCP surface are full peers. */
function McpSection() {
  const t = useTranslations("settings");

  const config = JSON.stringify(
    { mcpServers: { annos: { type: "http", url: MCP_URL } } },
    null,
    2,
  );

  return (
    <div className="mt-2 flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">{t("mcpIntro")}</p>

      <div>
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-xs uppercase text-muted-foreground">
            {t("mcpEndpoint")}
          </span>
          <CopyButton value={MCP_URL} label={t("copyEndpoint")} />
        </div>
        <code className="tnum mt-1.5 block truncate border border-input px-3 py-2 font-mono text-xs">
          {MCP_URL}
        </code>
        <p className="mt-1.5 text-xs text-muted-foreground">{t("mcpClaudeNote")}</p>
      </div>

      <div>
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-xs uppercase text-muted-foreground">
            {t("mcpConfig")}
          </span>
          <CopyButton value={config} label={t("copyConfig")} />
        </div>
        <pre className="mt-1.5 overflow-x-auto border border-input px-3 py-2 font-mono text-xs leading-relaxed">
          {config}
        </pre>
        <p className="mt-1.5 text-xs text-muted-foreground">{t("mcpConfigNote")}</p>
      </div>

      <div>
        <span className="font-mono text-xs uppercase text-muted-foreground">
          {t("mcpHow")}
        </span>
        <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          <li>{t("mcpStep1")}</li>
          <li>{t("mcpStep2")}</li>
          <li>{t("mcpStep3")}</li>
        </ol>
      </div>
    </div>
  );
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const t = useTranslations("settings");
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => {
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="flex min-h-11 items-center gap-1 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
    >
      {copied ? (
        <Check aria-hidden className="size-3.5" />
      ) : (
        <Copy aria-hidden className="size-3.5" />
      )}
      {copied ? t("copied") : t("copy")}
    </button>
  );
}

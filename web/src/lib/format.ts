/** Presentation helpers for the sheet. The server owns time and totals;
 * everything here is formatting. */

const LOCALES: Record<string, string> = {
  fi: "fi-FI",
  sv: "sv-SE",
  en: "en-GB",
};

export function localeFor(language: string | undefined): string {
  return LOCALES[language ?? "fi"] ?? "fi-FI";
}

/** "keskiviikko" → "KESKIVIIKKO" happens in CSS; this returns the weekday
 * in the reader's language. */
export function weekday(dateISO: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "long",
    timeZone: "UTC",
  }).format(new Date(`${dateISO}T00:00:00Z`));
}

/** Numeric date the way the menu sheet prints it: 6.8.2026 */
export function sheetDate(dateISO: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${dateISO}T00:00:00Z`));
}

/** ISO 8601 week number — the sheet's letterhead. */
export function isoWeek(dateISO: string): number {
  const d = new Date(`${dateISO}T00:00:00Z`);
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day + 3);
  const firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  const firstDay = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDay + 3);
  return 1 + Math.round((d.getTime() - firstThursday.getTime()) / (7 * 86400000));
}

export function addDays(dateISO: string, days: number): string {
  const d = new Date(`${dateISO}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Clock time of a log in the profile timezone the API already applied —
 * `ts` arrives timezone-aware. */
export function clockTime(tsISO: string, locale: string, timeZone: string): string {
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(new Date(tsISO));
}

export function kcal(value: number | null | undefined): string {
  if (value == null) return "–";
  return String(Math.round(value));
}

export function grams(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function signed(value: number): string {
  return value < 0 ? `−${Math.abs(Math.round(value))}` : String(Math.round(value));
}

/** A rate like −0.4, in the reader's locale with a true minus sign. */
export function rateFigure(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value).replace("-", "−");
}

/** Provenance rides in parentheses after a dish name, the way allergen
 * codes do on the printed menu. Measured sources go unmarked; the codes
 * flag what is estimated or user-entered. */
export function sourceCode(source: string | null | undefined): string | null {
  switch (source) {
    case "ai_estimate":
      return "AI";
    case "user":
      return "own";
    case "label":
      return "label";
    default:
      return null; // fineli, verified — measured data is the sheet's default
  }
}

/** The server's meal_type enum, in menu order. Labels live in the message
 * catalogues (`meals.*`). */
export const MEALS = ["breakfast", "lunch", "dinner", "snack"] as const;

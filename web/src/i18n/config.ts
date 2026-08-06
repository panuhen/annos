/** Shared between the server request config and client components —
 * keep free of server-only imports. */
export const LOCALES = ["fi", "sv", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_COOKIE = "annos-lang";

export function isLocale(value: string | undefined): value is Locale {
  return !!value && (LOCALES as readonly string[]).includes(value);
}

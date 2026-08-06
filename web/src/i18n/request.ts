import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";

import { LOCALE_COOKIE, isLocale, type Locale } from "./config";

/** One language, one switch: `user_profile.language` is the truth, mirrored
 * into a cookie by the app gate so server rendering (and the pre-auth pages,
 * which have no profile) can resolve it. Before any cookie exists the
 * browser's Accept-Language decides, defaulting to Finnish — the audience. */
export default getRequestConfig(async () => {
  const cookie = (await cookies()).get(LOCALE_COOKIE)?.value;
  let locale: Locale;
  if (isLocale(cookie)) {
    locale = cookie;
  } else {
    const accept = (await headers()).get("accept-language") ?? "";
    const preferred = accept
      .split(",")
      .map((part) => part.split(";")[0]!.trim().slice(0, 2).toLowerCase())
      .find(isLocale);
    locale = preferred ?? "fi";
  }
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});

import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";

/**
 * The front door decides by cookie: a visitor with no session sees the letter
 * (/hello rewritten under the / URL — no redirect flash, no login form as the
 * first impression), while a signed-in user falls through to the day sheet.
 * Cookie presence is only routing, never authentication — the (app) gate still
 * verifies the session and bounces a stale cookie to /sign-in exactly as
 * before. getSessionCookie handles the __Secure- prefix production adds.
 * (proxy.ts is Next 16's name for the middleware file; the export must be
 * named `proxy`.)
 */
export function proxy(request: NextRequest) {
  if (!getSessionCookie(request)) {
    return NextResponse.rewrite(new URL("/hello", request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: "/" };

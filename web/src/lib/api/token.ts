/**
 * The API accepts a Better Auth JWT, fetched from the `jwt` plugin's
 * /api/auth/token off the session cookie. Cached in memory until shortly
 * before `exp` — never persisted, so signing out orphans nothing.
 */
let cached: { token: string; exp: number } | null = null;

export async function apiToken(): Promise<string> {
  if (cached && cached.exp - 30 > Date.now() / 1000) return cached.token;
  const res = await fetch("/api/auth/token");
  if (!res.ok) throw new Error("not signed in");
  const { token } = (await res.json()) as { token: string };
  const { exp } = JSON.parse(atob(token.split(".")[1])) as { exp: number };
  cached = { token, exp };
  return token;
}

export function clearApiToken() {
  cached = null;
}

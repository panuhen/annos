import { headers } from "next/headers";

/**
 * The app's public origin, resolved at REQUEST time. Metadata, the share card,
 * robots and the sitemap all build absolute URLs from this — never a build-time
 * constant, which would bake in localhost (the Docker build has no runtime
 * host) and send crawlers to the wrong place. BETTER_AUTH_URL is the origin the
 * browser already uses; the forwarded-host headers are the fallback behind the
 * Cloudflare/Coolify proxy, and localhost is the dev default.
 */
export async function getBaseUrl(): Promise<string> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto =
    h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  return process.env.APP_URL ?? process.env.BETTER_AUTH_URL ?? `${proto}://${host}`;
}

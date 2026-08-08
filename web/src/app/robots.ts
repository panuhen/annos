import type { MetadataRoute } from "next";

import { getBaseUrl } from "@/lib/base-url";

// The app is behind sign-in and holds personal health data, so only the public
// entry and legal pages should be crawled. Everything under the gate redirects
// anonymous visitors anyway; listing those paths (and the API proxy and the
// OAuth consent interstitial) makes the intent explicit rather than relying on
// the redirect.
export default async function robots(): Promise<MetadataRoute.Robots> {
  const base = await getBaseUrl();
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/api/",
        "/annos/",
        "/consent",
        "/welcome",
        "/log",
        "/exercise",
        "/stats",
        "/goal",
        "/templates",
        "/profile",
        "/settings",
      ],
    },
    sitemap: `${base}/sitemap.xml`,
    host: base,
  };
}

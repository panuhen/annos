import type { MetadataRoute } from "next";

import { getBaseUrl } from "@/lib/base-url";

// Only the public pages: the two entry points and the two legal pages. The day
// sheet and every other route sit behind the gate and carry personal data, so
// they stay out of the sitemap (and out of robots).
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = await getBaseUrl();
  const now = new Date();
  return [
    { url: `${base}/`, lastModified: now, changeFrequency: "monthly", priority: 1.0 },
    { url: `${base}/sign-up`, lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/sign-in`, lastModified: now, changeFrequency: "monthly", priority: 0.5 },
    { url: `${base}/privacy`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${base}/terms`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
  ];
}

import type { Metadata, Viewport } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { Fragment_Mono, Playwrite_CU, Schibsted_Grotesk } from "next/font/google";
import { ThemeProvider } from "next-themes";

import "./globals.css";

import { Toaster } from "@/components/ui/sonner";
import { getBaseUrl } from "@/lib/base-url";

import { Providers } from "./providers";

const grotesk = Schibsted_Grotesk({
  variable: "--font-schibsted",
  subsets: ["latin"],
});

const mono = Fragment_Mono({
  weight: "400",
  variable: "--font-fragment-mono",
  subsets: ["latin"],
});

// The wordmark face: Playwrite Cuba, a Cuban school-cursive hand. Google
// ships it without subsets, so next/font can't preload it — it's one word on
// the page, not body text, so the late swap is invisible.
const wordmark = Playwrite_CU({
  variable: "--font-playwrite",
});

const DESCRIPTION =
  "Food, exercise and weight tracking — over MCP and on the web.";

// Built at REQUEST time, not module load, so the share-card URL is absolute and
// correct wherever the app is served. A build-time base would bake in
// localhost (the Docker build has no runtime host), and crawlers would then
// fetch localhost and silently drop the card. BETTER_AUTH_URL is the origin the
// browser already uses; the forwarded-host headers are the fallback behind the
// proxy.
export async function generateMetadata(): Promise<Metadata> {
  const base = await getBaseUrl();
  const card = {
    url: `${base}/og-card.png`,
    width: 1200,
    height: 630,
    alt: "Annos — food, exercise and weight tracking, over MCP and on the web",
  };
  return {
    metadataBase: new URL(base),
    title: { default: "Annos", template: "%s · Annos" },
    description: DESCRIPTION,
    applicationName: "Annos",
    // Launch standalone from the home screen on iOS (no Safari chrome); Android
    // reads the same intent from the web manifest.
    appleWebApp: { capable: true, title: "Annos", statusBarStyle: "default" },
    openGraph: {
      type: "website",
      siteName: "Annos",
      title: "Annos",
      description: DESCRIPTION,
      images: [card],
    },
    twitter: {
      card: "summary_large_image",
      title: "Annos",
      description: DESCRIPTION,
      images: [card],
    },
  };
}

// The status-bar / browser-chrome tint of the installed app, matched to the
// sheet in each theme (light: sheet-white; dark: night-sheet).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#1a1a1a" },
  ],
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={`${grotesk.variable} ${mono.variable} ${wordmark.variable}`}
    >
      <body className="antialiased">
        <NextIntlClientProvider>
          <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
            <Providers>{children}</Providers>
            <Toaster position="top-center" />
          </ThemeProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

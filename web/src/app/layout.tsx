import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { Fragment_Mono, Playwrite_CU, Schibsted_Grotesk } from "next/font/google";
import { ThemeProvider } from "next-themes";

import "./globals.css";

import { Toaster } from "@/components/ui/sonner";

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

export const metadata: Metadata = {
  title: "Annos",
  description: "Food, exercise and weight tracking — over MCP and on the web.",
};

const contract = `<!--
THESIS: Your day is a menu of the day — the Finnish canteen ruokalista as a
working interface; refuses the tracker-app arrangement of rings, cards and a
floating add button.
OWN-WORLD: Pure-white sheet (near-black in dark), warm ink, 1px rules with
2px day/total rules, honey-ochre (hue 80) reserved for actions and today;
Schibsted Grotesk + Fragment Mono numerals; sharp corners.
STORY: Glance at the sheet, read today like a menu, see totals ruled off
against the target, stamp a new meal in seconds.
FIRST VIEWPORT: Week + weekday/date header, meals listed as dishes with
right-aligned mono kcal, provenance codes in parentheses, totals ruled off at
the foot, ochre "Log a meal" within thumb reach.
FORM: Ruokalista — candidate 4 of 7 by resonance; seed 6aaff5db.
FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, and DESIGN.md
-->`;

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
        <span hidden dangerouslySetInnerHTML={{ __html: contract }} />
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

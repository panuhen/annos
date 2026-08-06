"use client";

import { CircleUserRound, ClipboardList, Crosshair, Weight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/", label: "Today", icon: ClipboardList },
  { href: "/weight", label: "Weight", icon: Weight },
  { href: "/goal", label: "Goal", icon: Crosshair },
  { href: "/profile", label: "Profile", icon: CircleUserRound },
] as const;

/** The sheet's foot on a phone: a heavy rule with the app's four places
 * under it. On wide screens the places dock into the letterhead instead. */
export function AppNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t-2 border-foreground bg-background pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      <div className="mx-auto flex max-w-md">
        {TABS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-12 flex-1 flex-col items-center justify-center gap-0.5 py-1.5",
                "font-mono text-[0.625rem] uppercase tracking-wider",
                active ? "text-primary" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon aria-hidden strokeWidth={active ? 2.25 : 1.75} className="size-5" />
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

/** The wide-screen letterhead row: the four places as a quiet line of
 * mono labels, no bar chrome. */
export function DesktopNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="hidden justify-end gap-6 pt-4 lg:flex">
      {TABS.map(({ href, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "font-mono text-xs uppercase tracking-wider",
              active
                ? "font-bold text-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

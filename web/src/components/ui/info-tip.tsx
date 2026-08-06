"use client";

import { Info } from "@phosphor-icons/react";
import { Popover as PopoverPrimitive } from "radix-ui";

/** A tooltip that also works on touch: a small info glyph that opens a quiet
 * floating note on tap, hover users get it on click too (Radix Tooltip never
 * opens on touch, which disqualifies it for a mobile-first sheet). Styled to
 * the sheet: square, hairline border, no shadow. */
export function InfoTip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>
        <button
          type="button"
          aria-label={label}
          className="flex size-11 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <Info aria-hidden className="size-4" />
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          side="bottom"
          align="end"
          sideOffset={2}
          className="z-50 max-w-72 border border-input bg-popover px-3 py-2 text-xs text-popover-foreground"
        >
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

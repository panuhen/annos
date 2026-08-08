"use client";

import { Check, Copy } from "@phosphor-icons/react";
import { useState } from "react";

/**
 * Copy-to-clipboard affordance shared by Settings and the landing page. The
 * copy/copied strings are passed in rather than read from a fixed namespace,
 * so each surface labels it in its own catalogue. The icon flips to a check
 * for 1.5s on success; failure leaves the idle state (nothing to undo).
 */
export function CopyButton({
  value,
  label,
  idleText,
  copiedText,
}: {
  value: string;
  label: string;
  idleText: string;
  copiedText: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => {
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="flex min-h-11 items-center gap-1 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground"
    >
      {copied ? (
        <Check aria-hidden className="size-3.5" />
      ) : (
        <Copy aria-hidden className="size-3.5" />
      )}
      {copied ? copiedText : idleText}
    </button>
  );
}

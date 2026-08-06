import { cn } from "@/lib/utils";

/** The Annos wordmark: the name set in Playwrite Cuba, a Cuban school-cursive
 * hand. It replaces the faceted-A mark — the word is the logo now. Size and
 * colour come from the caller via `className`; the face is fixed. */
export function AnnosWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-display leading-none", className)}>Annos</span>
  );
}

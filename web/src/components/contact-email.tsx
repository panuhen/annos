"use client";

import { useSyncExternalStore } from "react";

/**
 * The contact address, assembled client-side from its parts so it isn't sitting
 * in the server-rendered HTML as plaintext for scrapers. Before hydration it
 * shows a "user [at] domain" span; after, a real mailto link. The hydration
 * check uses useSyncExternalStore — the same idiom as the settings theme
 * toggle — rather than a setState-in-effect.
 */
const emptySubscribe = () => () => {};

export function ContactEmail({ user = "panu", domain = "rapu.ai" }: { user?: string; domain?: string }) {
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  if (!mounted) {
    return (
      <span>
        {user} [at] {domain}
      </span>
    );
  }
  const address = `${user}@${domain}`;
  return <a href={`mailto:${address}`}>{address}</a>;
}

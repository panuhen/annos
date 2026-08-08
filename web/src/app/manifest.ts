import type { MetadataRoute } from "next";

// Web App Manifest — makes Annos installable (the browser's install button and
// iOS/Android "Add to Home Screen"), launching standalone with no browser
// chrome. Next serves this at /manifest.webmanifest and injects the
// <link rel="manifest"> automatically. Icons: the theme-adaptive SVG first,
// then the black-A-on-white rasters; the maskable pair carries safe-zone
// padding so an OS circle/squircle crop never clips the mark. No service
// worker — this is an installable shell, not an offline cache.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Annos",
    short_name: "Annos",
    description: "Food, exercise and weight tracking — over MCP and on the web.",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#ffffff",
    icons: [
      { src: "/icon.svg", type: "image/svg+xml", sizes: "any" },
      { src: "/icon-192.png", type: "image/png", sizes: "192x192", purpose: "any" },
      { src: "/icon-512.png", type: "image/png", sizes: "512x512", purpose: "any" },
      { src: "/icon-192-maskable.png", type: "image/png", sizes: "192x192", purpose: "maskable" },
      { src: "/icon-512-maskable.png", type: "image/png", sizes: "512x512", purpose: "maskable" },
      { src: "/apple-icon.png", type: "image/png", sizes: "180x180" },
    ],
  };
}

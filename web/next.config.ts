import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin();

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image.
  output: "standalone",
  devIndicators: false,
  // The browser talks only to this origin; /annos/* is proxied to the API
  // server-side. Same-origin by construction, so no CORS configuration
  // exists to drift. ANNOS_API_URL is the in-network address (compose:
  // http://api:8000); the localhost default serves `npm run dev` on the host.
  async rewrites() {
    const api = process.env.ANNOS_API_URL ?? "http://localhost:8000";
    return [{ source: "/annos/:path*", destination: `${api}/:path*` }];
  },
};

export default withNextIntl(nextConfig);

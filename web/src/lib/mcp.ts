// The MCP endpoint is the API's own public origin — known only to deploy
// config (NEXT_PUBLIC_MCP_URL, baked at build time). The /annos rewrite the web
// app uses internally is not this public URL. A real build always carries the
// baked value; the fallback is the production origin rather than localhost,
// because both consumers are served from the deployed site and localhost is
// never the right thing to show a visitor.
export const MCP_URL = process.env.NEXT_PUBLIC_MCP_URL ?? "https://mcp.annos.app/mcp/";

// Display form drops the trailing slash; both spellings serve the same endpoint.
export const MCP_URL_DISPLAY = MCP_URL.replace(/\/$/, "");

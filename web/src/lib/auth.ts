import { betterAuth } from "better-auth";
import { jwt, mcp } from "better-auth/plugins";
import { Pool } from "pg";

/**
 * Better Auth is the identity system and the OAuth 2.1 authorization server.
 * The Python API is only a resource server; it validates opaque OAuth access
 * tokens via /oauth2/userinfo and web-UI JWTs offline against /jwks.
 *
 * It shares the API's Postgres under its own default table names, connecting
 * as the owner role. The API's restricted role has no SELECT on these tables —
 * that grant is the email quarantine.
 */
export const auth = betterAuth({
  database: new Pool({ connectionString: process.env.DATABASE_URL }),
  emailAndPassword: {
    enabled: true,
  },
  plugins: [
    jwt({
      jwt: {
        // Default is the entire user object — which would carry the email to
        // any service that can read the token. The subject claim is all the
        // API is ever allowed to learn.
        definePayload: () => ({}),
        issuer: process.env.BETTER_AUTH_URL,
        audience: process.env.BETTER_AUTH_URL,
      },
    }),
    mcp({
      loginPage: "/sign-in",
      oidcConfig: {
        loginPage: "/sign-in",
        // Remote MCP clients (Claude.ai among them) self-register via
        // RFC 7591; without this the whole MCP surface is unreachable.
        allowDynamicClientRegistration: true,
        storeClientSecret: "hashed",
      },
    }),
  ],
});

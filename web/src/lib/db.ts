import { Pool } from "pg";

/**
 * The one Postgres pool for the Next.js layer. Better Auth manages the identity
 * tables through it (owner role, so it can read its own `oauthApplication` /
 * `user` tables — the API's restricted role cannot, which is the email
 * quarantine). Anything else that needs a raw query — the OAuth consent page's
 * client-name lookup — reuses this pool rather than opening a second one.
 */
export const pool = new Pool({ connectionString: process.env.DATABASE_URL });

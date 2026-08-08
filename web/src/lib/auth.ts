import { betterAuth } from "better-auth";
import { jwt, mcp } from "better-auth/plugins";

import { pool } from "@/lib/db";
import { sendPasswordResetEmail, sendVerificationEmail } from "@/lib/emails";

// BETTER_AUTH_SECRET signs session cookies and OAuth artifacts; a weak or
// public value means any session can be forged. The dev default is fine on
// http://localhost, catastrophic on a real origin — so refuse to start when the
// public origin is https and the secret is missing or still the dev placeholder.
// A loud boot failure beats a silent takeover surface. See compose.yaml.
const DEV_SECRET_PLACEHOLDER = "dev-only-secret-change-in-production-0000";
const authUrl = process.env.BETTER_AUTH_URL ?? "";
const authSecret = process.env.BETTER_AUTH_SECRET ?? "";
if (
  authUrl.startsWith("https://") &&
  (authSecret === "" || authSecret === DEV_SECRET_PLACEHOLDER)
) {
  throw new Error(
    "BETTER_AUTH_SECRET must be set to a real secret when BETTER_AUTH_URL is https",
  );
}

/**
 * Better Auth is the identity system and the OAuth 2.1 authorization server.
 * The Python API is only a resource server; it validates opaque OAuth access
 * tokens via /oauth2/userinfo and web-UI JWTs offline against /jwks.
 *
 * It shares the API's Postgres under its own default table names, connecting
 * as the owner role. The API's restricted role has no SELECT on these tables —
 * that grant is the email quarantine.
 */
// Google sign-in, offered only when its credentials are configured (so local
// dev without them simply doesn't advertise it). Google returns the user's
// real name and photo; Annos stores neither — `mapProfileToUser` blanks both
// so only the quarantined email lands, and the generated nickname stays the
// only display identity. Google-verified emails satisfy requireEmailVerification
// on their own, so social sign-ups send no confirmation mail.
const socialProviders =
  process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET
    ? {
        google: {
          clientId: process.env.GOOGLE_CLIENT_ID,
          clientSecret: process.env.GOOGLE_CLIENT_SECRET,
          // Empty strings, not omitted: an omitted field lets the default
          // mapping keep Google's name/picture — we must actively blank them.
          mapProfileToUser: () => ({ name: "", image: "" }),
        },
      }
    : undefined;

export const auth = betterAuth({
  database: pool,
  socialProviders,
  emailAndPassword: {
    enabled: true,
    // No usable account until the address is confirmed: kills typo/junk
    // sign-ups and proves the one datum Annos keeps (email, for recovery) is
    // real before it enters the quarantine. Sign-in returns EMAIL_NOT_VERIFIED
    // until then; the sign-up page shows a "check your mail" state instead of
    // sending the browser to /welcome (that redirect now happens on the
    // verification click, via autoSignInAfterVerification below).
    requireEmailVerification: true,
    // Length is the honest floor (NIST favours it over complexity theatre);
    // it's the only rule Better Auth enforces server-side. Client inputs
    // mirror the 12 so the browser rejects short passwords before the round
    // trip.
    minPasswordLength: 12,
    maxPasswordLength: 128,
    sendResetPassword: async ({ user, url }) => {
      await sendPasswordResetEmail(user.email, url);
    },
  },
  account: {
    // Same email via both password and Google is one person, so link them
    // instead of the default account_not_linked refusal. Trusting Google is
    // safe: it verifies email ownership, and requireLocalEmailVerified (on by
    // default) still requires the existing password account to be verified
    // before Google's claim is accepted — no pre-registration hijack.
    // updateUserInfoOnLink stays at its default (false), so linking never
    // copies Google's real name or photo onto the account: the quarantine and
    // the generated-nickname-only rule survive the link untouched.
    accountLinking: {
      enabled: true,
      trustedProviders: ["google"],
    },
  },
  emailVerification: {
    sendOnSignUp: true,
    // The verification click yields a session and lands on the callbackURL the
    // sign-up passes (/welcome), so the nickname roll runs exactly where it
    // always did — just triggered by the click instead of the sign-up.
    autoSignInAfterVerification: true,
    sendVerificationEmail: async ({ user, url }) => {
      await sendVerificationEmail(user.email, url);
    },
  },
  user: {
    // Account deletion is two-sided: the profile page first has the API
    // erase every Annos row (nickname-confirmed, web-credential-only), then
    // calls deleteUser with the password — Better Auth verifies it before
    // touching anything, then removes the user and its sessions. The two
    // schemas share no foreign key, so each side deletes its own.
    deleteUser: {
      enabled: true,
      // deleteUser cascades sessions, accounts and OAuth grants, but not the
      // `verification` table (no FK to user). Its rows carry no email — email
      // verification is a stateless signed token, and a password-reset row is
      // keyed by a random token with the user id as its value — but a pending
      // reset token still points at the now-deleted user until it expires.
      // Clear those so nothing outlives the account.
      afterDelete: async (user) => {
        await pool.query('DELETE FROM "verification" WHERE value = $1', [user.id]);
      },
    },
  },
  databaseHooks: {
    session: {
      // Better Auth stamps the client IP and user-agent onto every session row
      // by default, for the whole life of the session — more than a pseudonymous
      // tracker should retain. Blank them before the row is written (and on
      // refresh). Rate limiting still sees the real IP: getIp runs on the
      // request, independent of what the session row stores, so brute-force
      // protection is untouched. See db/grants.sql for the email quarantine that
      // keeps even this blanked row out of the API's reach.
      create: {
        before: async (session) => ({
          data: { ...session, ipAddress: "", userAgent: "" },
        }),
      },
      update: {
        before: async (session) => ({
          data: { ...session, ipAddress: "", userAgent: "" },
        }),
      },
    },
  },
  // Brute-force protection. Better Auth's own limiter, persisted to Postgres
  // (a `rateLimit` table it owns like its others — re-run `npx @better-auth/cli
  // migrate` as the owner to create it), so the limit survives deploys and
  // holds across instances — unlike an in-memory Map. Active in production
  // only by default (dev is never throttled). Cloudflare still fronts this in
  // prod as an edge layer. The custom rules tighten the sensitive credential
  // and recovery paths well below the 100-req global default.
  rateLimit: {
    // Left at the default (production-only): dev is never throttled, and the
    // Postgres-backed store is only consulted where the `rateLimit` table
    // exists — created by the CLI migrate that runs before deploy.
    storage: "database",
    customRules: {
      "/sign-in/email": { window: 60, max: 5 },
      "/sign-up/email": { window: 60, max: 5 },
      "/request-password-reset": { window: 60, max: 3 },
      "/reset-password": { window: 60, max: 5 },
      "/send-verification-email": { window: 60, max: 3 },
    },
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
        // The branded interstitial the connecting client (Claude.ai among
        // them) is sent to after sign-in. Without it Better Auth auto-approves
        // silently; with it the user sees the Annos mark and names the app
        // they're about to connect — and it is this page's origin, favicon and
        // mark that Claude.ai shows for the connector. Better Auth redirects
        // here with consent_code / client_id / scope in the query.
        consentPage: "/consent",
        // Remote MCP clients (Claude.ai among them) self-register via
        // RFC 7591; without this the whole MCP surface is unreachable.
        allowDynamicClientRegistration: true,
        storeClientSecret: "hashed",
      },
    }),
  ],
});

import { Resend } from "resend";

/**
 * The one place email ever leaves Annos — and it lives here, in the identity
 * layer that already holds the address, never in the Python API. That keeps
 * the email quarantine intact (see the Auth note in re:call): the API still
 * has no way to reach an address.
 *
 * Two transactional mails only — verification and password reset — because
 * those are the sole reasons Annos needs an address at all (auth + recovery).
 * No name and no nickname appears in either: the name field is always empty,
 * and the nickname is Annos-domain data that must not cross into this seam.
 *
 * English only, by decision: these two system mails are not localised the way
 * the trilingual UI is — the identity layer doesn't hold a language, and
 * reaching into the profile to find one would cross the quarantine seam.
 */

let client: Resend | null = null;

function resend(): Resend {
  if (!client) client = new Resend(process.env.RESEND_API_KEY);
  return client;
}

type Copy = { subject: string; heading: string; body: string; action: string; footer: string };

const VERIFY: Copy = {
  subject: "Confirm your email — Annos",
  heading: "Confirm your email",
  body: "Finish setting up your Annos account by confirming this address. The link is valid for one hour.",
  action: "Confirm email",
  footer: "If you didn't create an Annos account, you can ignore this message.",
};

const RESET: Copy = {
  subject: "Reset your password — Annos",
  heading: "Reset your password",
  body: "Follow this link to choose a new password. The link is valid for one hour.",
  action: "Reset password",
  footer:
    "If you didn't request a password reset, you can ignore this message — your password stays as it is.",
};

// Literal hex, not the app's oklch tokens: mail clients understand neither CSS
// variables nor oklch. Warm ink on paper white, the one honey accent — the
// Ruokalista palette, flattened.
// The wordmark ships as a hosted PNG, not text: web fonts and SVG are both
// stripped by Gmail/Outlook, but an <img> renders everywhere images load and
// degrades to the alt text "Annos" where they're blocked. Served from the app
// origin at /wordmark-email.png.
const ORIGIN = process.env.BETTER_AUTH_URL ?? "";

const INK = "#2a2620";
const HONEY = "#8a6d1f";
const MUTED = "#6b6355";
const RULE = "#e4dfd6";

function renderHtml(copy: Copy, url: string): string {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
  </head>
  <body style="margin:0;padding:0;background:#ffffff;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;">
      <tr>
        <td align="center" style="padding:40px 20px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:420px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:${INK};">
            <tr><td style="padding-bottom:16px;"><img src="${ORIGIN}/wordmark-email.png" alt="Annos" width="155" height="50" style="display:block;width:155px;height:50px;border:0;outline:none;text-decoration:none;" /></td></tr>
            <tr><td style="border-top:2px solid ${INK};font-size:0;line-height:0;">&nbsp;</td></tr>
            <tr><td style="font-size:22px;font-weight:700;padding:24px 0 8px;">${copy.heading}</td></tr>
            <tr><td style="font-size:15px;line-height:1.5;color:${INK};padding-bottom:24px;">${copy.body}</td></tr>
            <tr>
              <td style="padding-bottom:24px;">
                <a href="${url}" style="display:inline-block;background:${HONEY};color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;padding:14px 22px;">${copy.action}</a>
              </td>
            </tr>
            <tr><td style="border-top:1px solid ${RULE};font-size:0;line-height:0;">&nbsp;</td></tr>
            <tr><td style="font-size:12px;line-height:1.5;color:${MUTED};padding-top:16px;">${copy.footer}</td></tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>`;
}

function renderText(copy: Copy, url: string): string {
  return `${copy.heading}\n\n${copy.body}\n\n${url}\n\n${copy.footer}`;
}

async function send(to: string, copy: Copy, url: string): Promise<void> {
  // No key configured → dev. Log the link (never the address) so a developer
  // can complete the flow from `docker compose logs web` without Resend.
  if (!process.env.RESEND_API_KEY) {
    console.log(`[email] ${copy.subject} — dev link: ${url}`);
    return;
  }
  // Until a domain is verified in the Resend account, EMAIL_FROM is unset and
  // Resend's shared testing sender is used — it only delivers to the account's
  // own address. Set EMAIL_FROM to a verified-domain sender for real users.
  const from = process.env.EMAIL_FROM || "Annos <onboarding@resend.dev>";
  const { error } = await resend().emails.send({
    from,
    to,
    subject: copy.subject,
    html: renderHtml(copy, url),
    text: renderText(copy, url),
  });
  // Log the failure without the recipient — the structlog allowlist rule holds
  // on this side of the boundary too: an address never reaches a log line.
  if (error) console.error(`[email] send failed (${copy.subject}):`, error);
}

export function sendVerificationEmail(to: string, url: string) {
  return send(to, VERIFY, url);
}

export function sendPasswordResetEmail(to: string, url: string) {
  return send(to, RESET, url);
}

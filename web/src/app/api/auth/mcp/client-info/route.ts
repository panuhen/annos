import { NextResponse } from "next/server";

import { pool } from "@/lib/db";

/**
 * The connecting OAuth client's self-reported name, for the consent page to
 * show "{name} wants to connect" instead of an opaque client_id. Better Auth
 * stores it at registration (RFC 7591) in its own `oauthApplication` table;
 * this reads only the display name by client_id — never a secret, never user
 * data. A static segment, so it resolves ahead of the /api/auth/[...all]
 * catch-all rather than being swallowed by it.
 */
export async function GET(request: Request) {
  const clientId = new URL(request.url).searchParams.get("client_id");
  if (!clientId) {
    return NextResponse.json({ name: null }, { status: 400 });
  }
  try {
    const result = await pool.query(
      'SELECT name FROM "oauthApplication" WHERE "clientId" = $1 LIMIT 1',
      [clientId],
    );
    return NextResponse.json({ name: result.rows[0]?.name ?? null });
  } catch {
    // A missing name only costs the page its friendly label; it must never
    // block the consent flow. Fall back to null and let the page say "an
    // application".
    return NextResponse.json({ name: null });
  }
}

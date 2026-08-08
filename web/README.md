# Annos — web

The Next.js app: the web UI **and** the identity layer. [Better Auth](https://better-auth.com) runs here as the OAuth 2.1 authorization server, so this app is on the MCP critical path — the Python API validates tokens against it.

This app is not meant to run standalone. Bring up the whole stack (Postgres + API + web) from the repo root — see the [top-level README](../README.md):

```bash
docker compose up -d
```

The dev stack runs this app with the source bind-mounted and hot reload on, at <http://localhost:3000>.

## Working on the client contract

The typed API client is generated from the FastAPI OpenAPI schema, so a contract change surfaces as a type error rather than a runtime bug. After changing a REST response or request shape, with the API running:

```bash
npm run gen:api          # regenerate src/lib/api/schema.d.ts
npx tsc --noEmit         # let the compiler surface any fallout
npm run lint
```

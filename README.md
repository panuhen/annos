# Annos

**The food diary that lives in your AI chat.** Tell your assistant what you ate; Annos resolves the foods, logs them, and keeps the day's numbers. Free, open-source, and pseudonymous by design — it never asks for your real name.

→ **[annos.app](https://annos.app)**

## Two ways in, one behaviour

Annos is usable from a web app and from any AI client that speaks [MCP](https://modelcontextprotocol.io). The two surfaces are kept at parity: anything you can do over MCP you can also do in the web UI. Logic lives once in a shared domain layer, with the MCP tools and the REST API as thin adapters over it, so the two can't drift on the things that matter — day boundaries, macro snapshots, goal targets.

- **Web** — a day sheet you read like a menu: meals, totals ruled off against your target, weight and goal phases.
- **MCP** — connect an AI client and log by chatting. Food resolution, portions in grams, and the day's totals come back on every call.

Registration and account deletion are web-only on purpose, so a hallucinating client can't create or destroy an account.

## Privacy stance

What you track here is health data, so Annos is built to know as little as it can. You are a generated nickname, never a real name. Your email lives only in the sign-in system and is walled off from everything you log by a database permission — not just a promise. There is no analytics, tracking, or advertising anywhere in the app. See the in-app privacy policy for the full account.

## Running it

You need Docker. From the repo root:

```bash
cp .env.example .env      # dev defaults work out of the box; no secrets needed locally
docker compose up -d      # brings up Postgres, the API, and the web app
```

The web app is then at <http://localhost:3000> and the API at <http://localhost:8000>. The dev stack hot-reloads the web source; `.env.example` documents the handful of variables (email, Google sign-in, production secrets) you'd set for a real deployment.

Backend tests run against real Postgres in Docker:

```bash
docker compose up -d db
cd api && uv run pytest
```

## Stack

FastAPI + FastMCP (Python 3.12), SQLAlchemy 2.0 async on Postgres, and a Next.js + Tailwind web app. Identity and OAuth are handled by [Better Auth](https://better-auth.com) inside the web app; the Python service is only a resource server.

## Data and attribution

- Food and nutrient data is from **[Fineli](https://fineli.fi)**, the Finnish Institute for Health and Welfare, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Activity energy costs are from the **2024 Adult Compendium of Physical Activities** (Herrmann et al.), [pacompendium.com](https://pacompendium.com).

## License

[MIT](LICENSE).

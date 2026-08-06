import createClient from "openapi-fetch";

import type { paths } from "./schema";
import { apiToken } from "./token";

/**
 * Typed client over the FastAPI OpenAPI schema (`npm run gen:api`), so
 * contract drift is a type error rather than a runtime bug. Requests go
 * same-origin to /annos/* and a Next.js rewrite proxies them to the API —
 * no CORS surface anywhere.
 */
export const api = createClient<paths>({ baseUrl: "/annos" });

api.use({
  async onRequest({ request }) {
    request.headers.set("Authorization", `Bearer ${await apiToken()}`);
    return request;
  },
});

import createReactQueryClient from "openapi-react-query";

import { api } from "./client";
import type { paths } from "./schema";

/** Typed TanStack Query hooks over the generated client:
 *  `$api.useQuery("get", "/api/summary/daily", …)`. */
export const $api = createReactQueryClient<paths>(api);

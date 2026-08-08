FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_* are inlined into the client bundle at build time, so they must
# be present now, not just at runtime. Defaults keep a plain `docker build`
# working for local use; Coolify passes the production values as build args
# (see compose.yaml web.build.args).
ARG NEXT_PUBLIC_MCP_URL=http://localhost:8000/mcp/
ARG NEXT_PUBLIC_GOOGLE_ENABLED=false
ENV NEXT_PUBLIC_MCP_URL=${NEXT_PUBLIC_MCP_URL} \
    NEXT_PUBLIC_GOOGLE_ENABLED=${NEXT_PUBLIC_GOOGLE_ENABLED}
RUN npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]

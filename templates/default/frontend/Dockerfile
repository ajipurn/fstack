# syntax=docker/dockerfile:1
FROM oven/bun:1 AS build
WORKDIR /web
COPY package.json bun.lock* pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then npm i -g pnpm && pnpm install --frozen-lockfile; else bun install --frozen-lockfile; fi
COPY . .
RUN bun run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1

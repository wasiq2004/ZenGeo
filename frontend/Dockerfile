# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Stage 1 - build the SPA
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /app

# Dependencies first so edits to src/ reuse the cached install layer.
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 - serve the static build
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Run as the unprivileged nginx user; give it the paths it needs to write.
RUN touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html

USER nginx

EXPOSE 80

# 127.0.0.1, not localhost. The image's 10-listen-on-ipv6-by-default.sh cannot
# patch the config from the unprivileged `nginx` user, so nginx binds IPv4 only
# - while `localhost` resolves to ::1 first. busybox wget tries that single
# address and gives up, so the container reports unhealthy while serving every
# real request perfectly.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:80/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]

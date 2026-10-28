# syntax=docker/dockerfile:1.7
# =============================================================================
# TruthLens frontend — React/Vite build served by nginx (+ /api reverse proxy)
#   docker build -t truthlens-frontend ./frontend
# =============================================================================

# ---- Stage 1: build the SPA --------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; \
    else npm install --no-audit --no-fund; fi

COPY . .
# The app always calls relative /api URLs, so no API base URL is baked in.
RUN npm run build

# ---- Stage 2: serve with nginx -----------------------------------------------
FROM nginx:1.27-alpine AS runtime

ENV BACKEND_UPSTREAM=backend:8000 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

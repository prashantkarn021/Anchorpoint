# Build the Vite app, then serve the static files with Caddy (SPA fallback in ./Caddyfile).
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_API_MODE: auto (live API, fixture fallback per endpoint) | live | fixtures
ARG VITE_API_MODE=auto
ENV VITE_API_MODE=$VITE_API_MODE
RUN npm run build

FROM caddy:2
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /usr/share/caddy

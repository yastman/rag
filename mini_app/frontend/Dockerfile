# syntax=docker/dockerfile:1
# Mini App React frontend — Node build + nginx serve

# ====== BUILD STAGE ======
FROM node:20-slim AS builder

WORKDIR /app

# Deps layer
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# Source layer
COPY . .

RUN npm run build

# ====== RUNTIME STAGE ======
FROM nginx:1.29-alpine AS runtime

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/app.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/health || exit 1

CMD ["nginx", "-g", "daemon off;"]

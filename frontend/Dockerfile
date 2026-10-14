# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS build
WORKDIR /app

# Keep npm downloads in a BuildKit cache. Source-code edits no longer invalidate
# the dependency layer.
COPY package.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --prefer-offline --no-audit --no-fund

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN rm -rf /usr/share/nginx/html/*
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

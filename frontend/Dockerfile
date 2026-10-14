FROM node:24-alpine AS build
WORKDIR /app

ARG VITE_GOONG_MAPTILES_KEY
ARG VITE_API_BASE_URL=
ENV VITE_GOONG_MAPTILES_KEY=$VITE_GOONG_MAPTILES_KEY
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
ARG VITE_GOONG_MAPTILES_KEY
ARG VITE_API_BASE_URL
ENV BACKEND_UPSTREAM=backend:8000
ENV NGINX_ENVSUBST_FILTER="^BACKEND_UPSTREAM$"
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/ /usr/share/nginx/html/

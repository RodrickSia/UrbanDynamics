FROM node:24-alpine AS build
WORKDIR /app

ARG VITE_GOONG_MAPTILES_KEY
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_GOONG_MAPTILES_KEY=$VITE_GOONG_MAPTILES_KEY
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
ARG VITE_GOONG_MAPTILES_KEY
ARG VITE_API_BASE_URL
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/

FROM nginx:alpine
ARG VITE_GOONG_MAPTILES_KEY
ARG VITE_API_BASE_URL
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY public/ /usr/share/nginx/html/

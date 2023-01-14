FROM nginx:1.23-alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d

COPY cert.pem /etc/ssl/certs/cert.pem
COPY key.pem /etc/ssl/certs/key.pem

FROM nginx:alpine

# Create directory for self-signed certificate
RUN mkdir -p /etc/nginx/ssl

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Generate self-signed certificate
RUN apk add --no-cache openssl && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/server.key -out /etc/nginx/ssl/server.crt \
    -subj "/CN=localhost" && \
    chmod 644 /etc/nginx/ssl/server.key

# Expose TLS ports
EXPOSE 9001 9002 9003 
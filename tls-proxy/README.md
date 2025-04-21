# TLS Proxy for M2M RSP Services

This directory contains an Nginx-based TLS proxy that adds HTTPS support to the M2M RSP services without modifying their code.

## Architecture

- Original HTTP services run on:
  - SM-DP: http://localhost:8001
  - SM-SR: http://localhost:8002
  - eUICC: http://localhost:8003

- The TLS proxy exposes HTTPS endpoints:
  - SM-DP: https://localhost:9001
  - SM-SR: https://localhost:9002
  - eUICC: https://localhost:9003

## Setup

1. Make sure Docker and Docker Compose are installed on your system.
2. The TLS proxy automatically generates self-signed certificates.

## Running the TLS Proxy

1. Start your M2M RSP services first:
   ```
   python main.py
   ```

2. In a separate terminal, start the TLS proxy:
   ```
   cd tls-proxy
   docker-compose up --build
   ```

3. Test the HTTPS endpoints:
   ```
   python test_endpoints.py
   ```

## Using with M2M RSP Application

To use the secure endpoints in your application, simply:

1. Change `http://localhost:800X` URLs to `https://localhost:900X`
2. Add `verify=False` to your requests (since we're using self-signed certificates)

For example:
```python
# Original HTTP request
response = requests.get("http://localhost:8001/status")

# HTTPS request with TLS proxy
response = requests.get("https://localhost:9001/status", verify=False)
```

## Security Notes

- This proxy uses self-signed certificates for development/testing
- In production, you should use proper certificates from a trusted CA
- The `verify=False` parameter should not be used in production code 
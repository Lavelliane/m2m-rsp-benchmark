# M2M RSP with TLS

This project provides a Mobile to Mobile Remote SIM Provisioning (M2M RSP) implementation with TLS security using an Nginx proxy.

## Architecture

The system consists of three main components:

1. **M2M RSP Services**: The backend services that communicate over HTTP internally:
   - SM-DP: SIM Profile Data Preparation (port 8001)
   - SM-SR: SIM Profile Secure Routing (port 8002)
   - eUICC: Embedded Universal Integrated Circuit Card (port 8003)

2. **TLS Proxy**: An Nginx proxy in Docker that adds HTTPS support:
   - SM-DP: https://localhost:9001 → http://localhost:8001
   - SM-SR: https://localhost:9002 → http://localhost:8002
   - eUICC: https://localhost:9003 → http://localhost:8003

## Prerequisites

- Docker and Docker Compose
- Python 3.6+
- Required Python packages: `requests`, `twisted`, `klein`

## Getting Started

1. First, make sure Docker is running on your system.

2. Run the system with TLS:
   ```
   python run_with_tls.py
   ```
   This will:
   - Start the TLS proxy using Docker
   - Start the M2M RSP backend services
   - Run the demo automatically 

3. Alternatively, you can start components separately:
   
   a. Start the TLS proxy:
   ```
   cd tls-proxy
   docker-compose up --build -d
   cd ..
   ```

   b. Start the backend services:
   ```
   python main.py
   ```

   c. Use the TLS client to interact with the services:
   ```
   python tls_client.py  # Check status
   python tls_client.py demo  # Run a manual demo
   ```

## Using the TLS Endpoints

The TLS proxy exposes secure HTTPS endpoints that you can use in your code:

```python
import requests

# Disable SSL verification warnings (self-signed certificate)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SM-DP via HTTPS
response = requests.get("https://localhost:9001/status", verify=False)
print(response.json())

# SM-SR via HTTPS
response = requests.get("https://localhost:9002/status", verify=False)
print(response.json())

# eUICC via HTTPS
response = requests.get("https://localhost:9003/status", verify=False)
print(response.json())
```

## Security Notes

- The TLS proxy uses a self-signed certificate for development and testing
- In production, you would use proper certificates from a trusted Certificate Authority
- The `verify=False` parameter should not be used in production code

## Directory Structure

- `main.py` - Main M2M RSP system script
- `run_with_tls.py` - Script to run the system with TLS
- `tls_client.py` - Client script for HTTPS interactions
- `entities/` - M2M RSP component implementations
- `tls-proxy/` - TLS proxy configuration files
  - `nginx.conf` - Nginx configuration
  - `Dockerfile` - Docker image definition
  - `docker-compose.yml` - Docker Compose configuration 
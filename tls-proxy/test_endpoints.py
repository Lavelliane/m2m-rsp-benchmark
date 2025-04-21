#!/usr/bin/env python3
import requests
import json
import time
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Suppress warnings for self-signed certificates
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def test_endpoint(url, entity):
    try:
        print(f"Testing {entity} endpoint: {url}")
        response = requests.get(url, verify=False, timeout=5)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            print(f"{entity} endpoint is accessible via HTTPS\n")
            return True
        else:
            print(f"Error: Received status code {response.status_code}\n")
            return False
    except Exception as e:
        print(f"Error connecting to {entity}: {str(e)}\n")
        return False

def main():
    print("Testing TLS proxy endpoints...")
    endpoints = [
        ("https://localhost:9001/status", "SM-DP"),
        ("https://localhost:9002/status", "SM-SR"),
        ("https://localhost:9003/status", "eUICC")
    ]

    time.sleep(2)  # Give services time to start
    
    success_count = 0
    for url, entity in endpoints:
        if test_endpoint(url, entity):
            success_count += 1
    
    if success_count == len(endpoints):
        print("✅ All endpoints are accessible via HTTPS")
    else:
        print(f"⚠️ Only {success_count}/{len(endpoints)} endpoints are accessible")

if __name__ == "__main__":
    main() 
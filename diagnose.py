#!/usr/bin/env python3
"""
M2M RSP System Diagnostics Tool

This script checks the status of all M2M RSP system components
and provides a detailed report on their health.
"""

import requests
import socket
import json
import time
import sys
from urllib3.exceptions import InsecureRequestWarning

# Suppress only the single InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

def check_connectivity(host="localhost", ports=[8001, 8002, 8003]):
    """
    Check if the specified ports are open and services are responsive.
    
    Args:
        host (str): The host to check
        ports (list): List of ports to check
        
    Returns:
        dict: Results of the connectivity checks
    """
    results = {}
    
    for port in ports:
        results[port] = {
            "tcp_connect": False,
            "http_response": None,
            "response_time": None,
            "error": None
        }
        
        # Check TCP connectivity
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            start_time = time.time()
            s.connect((host, port))
            results[port]["tcp_connect"] = True
            
            # Try HTTP request if TCP is successful
            protocol = "https" if port in [8001, 8002] else "http"
            url = f"{protocol}://{host}:{port}/status"
            
            try:
                verify = False if protocol == "https" else None
                response = requests.get(url, verify=verify, timeout=3)
                results[port]["http_response"] = response.status_code
                results[port]["response_time"] = time.time() - start_time
                
                # Try to get JSON from response
                try:
                    results[port]["response_data"] = response.json()
                except:
                    results[port]["response_data"] = "Non-JSON response"
                    
            except requests.exceptions.RequestException as e:
                results[port]["error"] = f"HTTP error: {str(e)}"
                
        except socket.error as e:
            results[port]["error"] = f"Socket error: {str(e)}"
        finally:
            s.close()
    
    return results

def print_connectivity_report(results):
    """
    Print a formatted connectivity report
    
    Args:
        results (dict): Results from check_connectivity
    """
    print("\n=== CONNECTIVITY REPORT ===")
    
    all_services_up = True
    
    for port, data in results.items():
        service = "Unknown"
        if port == 8001:
            service = "SM-DP"
        elif port == 8002:
            service = "SM-SR"
        elif port == 8003:
            service = "eUICC"
        
        status = "✓ ONLINE" if data["tcp_connect"] and data["http_response"] == 200 else "✗ OFFLINE"
        if status == "✗ OFFLINE":
            all_services_up = False
            
        print(f"\n{service} (Port {port}): {status}")
        
        if data["tcp_connect"]:
            print(f"  TCP Connection: Success")
            if data["http_response"]:
                print(f"  HTTP Response: {data['http_response']}")
                print(f"  Response Time: {data['response_time']:.3f}s")
                if "response_data" in data:
                    if isinstance(data["response_data"], dict):
                        print(f"  Response Data: {json.dumps(data['response_data'], indent=2)}")
                    else:
                        print(f"  Response Data: {data['response_data']}")
            else:
                print(f"  HTTP Response: Failed - {data['error']}")
        else:
            print(f"  Error: {data['error']}")
    
    print("\n===========================")
    
    if all_services_up:
        print("\nAll services are running correctly!")
    else:
        print("\nSome services are not responding correctly. Check the details above.")

def test_profile_transmission():
    """Test the profile preparation and transmission flow"""
    print("\n=== TESTING PROFILE PREPARATION/TRANSMISSION ===")
    try:
        start_time = time.time()
        print("Sending profile preparation request to SM-DP...")
        
        response = requests.post(
            "https://localhost:8001/profile/prepare",
            json={
                "profileType": "test",
                "iccid": "89012345678901234567",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            },
            verify=False,
            timeout=10
        )
        
        elapsed = time.time() - start_time
        print(f"Request completed in {elapsed:.3f} seconds")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Status: {result.get('status', 'unknown')}")
            
            if result.get('status') == 'success':
                print("Profile preparation and transmission successful!")
                if 'sm_sr_response' in result:
                    print(f"SM-SR Response: {json.dumps(result['sm_sr_response'], indent=2)}")
            else:
                print(f"Error: {result.get('message', 'Unknown error')}")
                
        else:
            print(f"Error: HTTP {response.status_code}")
            print(response.text)
            
    except requests.exceptions.Timeout:
        print("Error: Request timed out")
    except Exception as e:
        print(f"Error: {str(e)}")
        
    print("\n=============================================")

def main():
    print("M2M RSP System Diagnostics Tool")
    print("===============================")
    
    # Check basic connectivity
    results = check_connectivity()
    print_connectivity_report(results)
    
    # Test specific features
    choice = input("\nDo you want to test profile transmission? (y/n): ").strip().lower()
    if choice == 'y':
        test_profile_transmission()
    
    print("\nDiagnostics completed!")

if __name__ == "__main__":
    main() 
import requests
import socket
import json
import time

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
    for port, data in results.items():
        service = "Unknown"
        if port == 8001:
            service = "SM-DP"
        elif port == 8002:
            service = "SM-SR"
        elif port == 8003:
            service = "eUICC"
        
        status = "✓ ONLINE" if data["tcp_connect"] else "✗ OFFLINE"
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

def diagnose_system(return_results=False):
    """
    Run a full diagnostic on the M2M RSP system
    
    Args:
        return_results (bool): If True, return the diagnostics results instead of just printing them
        
    Returns:
        dict: Results of the diagnostics if return_results is True, otherwise None
    """
    print("Running M2M RSP system diagnostics...")
    
    # Check basic connectivity
    results = check_connectivity()
    
    # Only print the report if not just returning results
    if not return_results:
        print_connectivity_report(results)
    
    # Additional checks could be added here
    
    if return_results:
        return results
    return None

if __name__ == "__main__":
    # Can be run standalone for diagnostics
    diagnose_system() 
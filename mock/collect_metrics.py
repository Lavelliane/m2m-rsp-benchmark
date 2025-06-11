#!/usr/bin/env python3
"""
Script to run RSP load test and collect CPU/Memory metrics in CSV format.
This script will:
1. Start the mock server (if not already running)
2. Run the k6 load test
3. Collect metrics and save to CSV
4. Generate summary report
"""

import subprocess
import time
import requests
import json
import sys
import os
from datetime import datetime

BASE_URL = "http://localhost:8080"

def check_server_running():
    """Check if the mock server is running"""
    try:
        response = requests.get(f"{BASE_URL}/status/smsr", timeout=5)
        return response.status_code == 200
    except:
        return False

def start_server():
    """Start the mock server"""
    print("Starting mock server...")
    # Start server in background
    process = subprocess.Popen([
        sys.executable, "mock.py"
    ], cwd=".", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for server to start
    for i in range(30):  # Wait up to 30 seconds
        if check_server_running():
            print("Mock server started successfully!")
            return process
        time.sleep(1)
        print(f"Waiting for server to start... ({i+1}/30)")
    
    print("Failed to start server")
    return None

def clear_metrics():
    """Clear existing metrics data"""
    try:
        response = requests.post(f"{BASE_URL}/metrics/clear")
        if response.status_code == 200:
            print("Metrics cleared successfully")
            return True
    except Exception as e:
        print(f"Failed to clear metrics: {e}")
    return False

def run_k6_test():
    """Run the k6 load test"""
    print("Running k6 load test...")
    
    try:
        # Run k6 test
        result = subprocess.run([
            "k6", "run", "--quiet", "k6-load-test.js"
        ], capture_output=True, text=True, timeout=300)  # 5 minute timeout
        
        if result.returncode == 0:
            print("k6 test completed successfully!")
            print("k6 Summary:")
            print(result.stdout)
            return True
        else:
            print(f"k6 test failed with return code {result.returncode}")
            print("Error output:")
            print(result.stderr)
            return False
    except subprocess.TimeoutExpired:
        print("k6 test timed out")
        return False
    except FileNotFoundError:
        print("k6 not found. Please install k6 first: https://k6.io/docs/getting-started/installation/")
        return False
    except Exception as e:
        print(f"Error running k6 test: {e}")
        return False

def collect_csv_metrics(filename=None):
    """Collect metrics and save to CSV"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rsp_metrics_{timestamp}.csv"
    
    print(f"Collecting metrics and saving to {filename}...")
    
    try:
        # Save metrics to CSV file
        response = requests.post(f"{BASE_URL}/metrics/save-csv", 
                               json={"filename": filename})
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"✅ Metrics saved successfully!")
                print(f"📁 File: {result['filename']}")
                print(f"📊 Records: {result['records_count']}")
                print(f"🔧 Operations tracked: {', '.join(result['operations_tracked'])}")
                return result['filename']
            else:
                print(f"❌ Failed to save metrics: {result.get('message')}")
                return None
        else:
            print(f"❌ HTTP error {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error collecting metrics: {e}")
        return None

def get_flow_summary():
    """Get RSP flow summary"""
    try:
        response = requests.get(f"{BASE_URL}/metrics/rsp-flow")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error getting flow summary: {e}")
    return None

def print_summary(flow_data):
    """Print a summary of the RSP flow metrics"""
    if not flow_data:
        return
    
    print("\n" + "="*60)
    print("RSP FLOW PERFORMANCE SUMMARY")
    print("="*60)
    
    flow_metrics = flow_data.get('rsp_flow_metrics', {})
    summary = flow_data.get('summary', {})
    
    print(f"📈 Total Operations: {summary.get('total_operations', 0)}")
    print(f"💻 Total CPU Usage: {summary.get('total_cpu_usage', 0):.2f}%")
    print(f"🧠 Total Memory Usage: {summary.get('total_memory_usage', 0):.2f} MB")
    print(f"⏱️  Total Execution Time: {summary.get('total_execution_time', 0):.2f} ms")
    print()
    
    # RSP operations in order
    rsp_operations = [
        'register_euicc',
        'create_isdp', 
        'key_establishment',
        'prepare_profile',
        'install_profile',
        'enable_profile'
    ]
    
    print("OPERATION BREAKDOWN:")
    print("-" * 60)
    
    for operation in rsp_operations:
        if operation in flow_metrics:
            data = flow_metrics[operation]
            if data.get('count', 0) > 0:
                cpu_stats = data.get('cpu_stats', {})
                memory_stats = data.get('memory_stats', {})
                exec_stats = data.get('execution_time_stats', {})
                
                print(f"🔄 {operation.replace('_', ' ').title()}:")
                print(f"   Count: {data['count']}")
                print(f"   CPU: avg={cpu_stats.get('avg', 0):.2f}% min={cpu_stats.get('min', 0):.2f}% max={cpu_stats.get('max', 0):.2f}%")
                print(f"   Memory: avg={memory_stats.get('avg', 0):.2f}MB min={memory_stats.get('min', 0):.2f}MB max={memory_stats.get('max', 0):.2f}MB")
                print(f"   Time: avg={exec_stats.get('avg', 0):.2f}ms min={exec_stats.get('min', 0):.2f}ms max={exec_stats.get('max', 0):.2f}ms")
                print()
            else:
                print(f"❌ {operation.replace('_', ' ').title()}: No data")
        else:
            print(f"⚠️  {operation.replace('_', ' ').title()}: Not executed")

def main():
    """Main function"""
    print("🚀 RSP Metrics Collection Tool")
    print("=" * 50)
    
    # Check if server is running, start if needed
    if not check_server_running():
        print("Mock server not running, starting it...")
        server_process = start_server()
        if not server_process:
            print("❌ Failed to start server. Exiting.")
            return 1
    else:
        print("✅ Mock server is already running")
        server_process = None
    
    try:
        # Clear existing metrics
        clear_metrics()
        
        # Run k6 test
        if not run_k6_test():
            print("❌ Load test failed. Exiting.")
            return 1
        
        # Wait a moment for metrics to be fully collected
        time.sleep(2)
        
        # Collect CSV metrics
        csv_file = collect_csv_metrics()
        if not csv_file:
            print("❌ Failed to collect metrics. Exiting.")
            return 1
        
        # Get and print summary
        flow_data = get_flow_summary()
        print_summary(flow_data)
        
        print(f"\n✅ Metrics collection completed!")
        print(f"📁 CSV file saved as: {csv_file}")
        print(f"📊 You can now analyze the data in {csv_file}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1
    finally:
        # Clean up server process if we started it
        if server_process:
            print("Stopping mock server...")
            server_process.terminate()
            server_process.wait(timeout=5)

if __name__ == "__main__":
    sys.exit(main()) 
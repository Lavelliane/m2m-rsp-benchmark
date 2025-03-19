#!/usr/bin/env python3
"""
M2M RSP Benchmark and Report Generator
Runs the M2M RSP demo, captures timing data, and generates a PDF report
"""

import sys
import os
import time
import subprocess
import threading
import warnings
import json
import datetime
from urllib3.exceptions import InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

# Function to run the main.py in a separate process
def run_demo(timeout=120):
    """Run the M2M RSP demo and return its output"""
    print("Starting M2M RSP demo...")
    
    try:
        # First, kill any existing processes that might be using our ports
        try:
            if os.name == 'nt':  # Windows
                # Find processes using ports 8001, 8002, 8003
                for port in [8001, 8002, 8003]:
                    os.system(f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{port}\') do taskkill /F /PID %a 2>nul')
            else:  # Linux/Mac
                for port in [8001, 8002, 8003]:
                    os.system(f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true")
        except Exception as e:
            print(f"Warning: Could not kill existing processes: {e}")
        
        # Start the demo
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        output = []
        start_time = time.time()
        
        # Create a threading.Event for communication
        stop_event = threading.Event()
        
        # Define a function for the reader thread
        def reader_thread_func():
            try:
                for line in process.stdout:
                    output.append(line)
                    print(line, end="")  # Echo output to console
                    if "Demo process finished" in line or "Press Ctrl+C to exit" in line:
                        stop_event.set()  # Signal that we're done
            except Exception as e:
                print(f"Error in reader thread: {e}")
        
        # Start reader thread
        reader_thread = threading.Thread(target=reader_thread_func)
        reader_thread.daemon = True
        reader_thread.start()
        
        # Wait for either timeout or completion
        while not stop_event.is_set() and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        # If we're still going after timeout, kill the process
        if not stop_event.is_set():
            print(f"Demo timed out after {timeout} seconds. Stopping...")
            if os.name == 'nt':  # Windows
                # On Windows, we need to kill the process group
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])
            else:
                process.kill()
        
        # Wait for process to finish
        process.wait(timeout=5)
        print("Demo execution completed.")
        
        return "\n".join(output)
        
    except Exception as e:
        print(f"Error running demo: {e}")
        return f"ERROR: {str(e)}"

# Function to extract timing information from the demo output
def extract_timing_data(output):
    """Extract timing information from the demo output"""
    if not output:
        return {}
        
    timing_data = {}
    lines = output.split("\n")
    
    # List of processes in the correct order
    expected_processes = [
        "eUICC Registration Process",
        "ISD-P Creation Process",
        "ECDH Key Establishment Process",
        "Profile Preparation Process",
        "Profile Download and Installation Process",
        "Profile Enabling Process"
    ]
    
    for line in lines:
        if ":" in line and "seconds" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                process_name = parts[0].strip()
                time_part = parts[1].strip()
                
                if "seconds" in time_part:
                    time_value = time_part.split("seconds")[0].strip()
                    try:
                        timing_data[process_name] = float(time_value)
                    except ValueError:
                        pass
    
    # Also include root infrastructure setup times
    setup_processes = ["Root CA Setup", "SM-DP Setup", "SM-SR Setup", "eUICC Setup"]
    for process in setup_processes:
        if process in timing_data:
            print(f"Including setup process: {process} - {timing_data[process]:.3f} seconds")
    
    # Print the main process times in order
    print("\nMain M2M RSP Process Timing Data:")
    for process in expected_processes:
        if process in timing_data:
            print(f"  - {process}: {timing_data[process]:.3f} seconds")
    
    return timing_data

# Function to generate the PDF report
def generate_report(timing_data=None):
    """Generate the PDF report using the generate_report.py script"""
    print("Generating PDF report...")
    
    # Save the timing data to a JSON file for the report generator to use
    if timing_data:
        with open("timing_data.json", "w") as f:
            json.dump(timing_data, f, indent=2)
    
    # Run the generate_report.py script
    try:
        subprocess.run([sys.executable, "generate_report.py"], check=True)
        print("Report generation successful!")
    except subprocess.CalledProcessError as e:
        print(f"Error generating report: {e}")

# Main function
def main():
    print("=== M2M RSP Benchmark and Report Generator ===")
    print(f"Started at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run the demo and capture output
    output = run_demo(timeout=60)
    
    if output:
        print("Demo execution completed.")
        
        # Extract timing data
        timing_data = extract_timing_data(output)
        
        if timing_data:
            print(f"Extracted timing data for {len(timing_data)} processes:")
            for process, time_value in timing_data.items():
                print(f"  - {process}: {time_value:.3f} seconds")
        else:
            print("No timing data found in the output.")
        
        # Generate the report
        generate_report(timing_data)
    else:
        print("Demo execution failed or produced no output.")
        # Generate report with default timing data
        generate_report()
    
    print(f"Process completed at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("You can find the PDF report in the current directory: m2m_rsp_report.pdf")

if __name__ == "__main__":
    main() 
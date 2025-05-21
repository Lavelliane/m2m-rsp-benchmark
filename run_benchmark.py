import subprocess
import time
import os
import signal
import sys
import argparse
from datetime import datetime

def run_benchmark(num_clients=10, concurrent_clients=5, ramp_up=0, monitor_interval=0.5):
    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"output/benchmark_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    
    # Start the monitor in a separate process
    monitor_output = os.path.join(output_dir, "server_metrics.json")
    monitor_cmd = [
        "python", "monitor.py",
        "--interval", str(monitor_interval),
        "--output", monitor_output
    ]
    
    print("Starting server monitor...")
    monitor_process = subprocess.Popen(monitor_cmd)
    
    try:
        # Give the monitor a moment to start
        time.sleep(2)
        
        # Run the load test
        print("\nStarting load test...")
        load_test_cmd = [
            "python", "load_test.py",
            "--clients", str(num_clients),
            "--concurrency", str(concurrent_clients),
            "--ramp-up", str(ramp_up)
        ]
        
        load_test_process = subprocess.run(load_test_cmd)
        
        if load_test_process.returncode != 0:
            print("Load test failed!")
            return False
            
        # Wait a moment to ensure all metrics are collected
        time.sleep(2)
        
        # Stop the monitor
        print("\nStopping server monitor...")
        monitor_process.terminate()
        monitor_process.wait(timeout=5)
        
        # Generate bottleneck analysis
        print("\nAnalyzing bottlenecks...")
        load_test_file = f"output/load_tests/load_test_{timestamp}.json"
        analyze_cmd = [
            "python", "analyze_bottlenecks.py",
            "--load-test", load_test_file,
            "--metrics", monitor_output,
            "--output", os.path.join(output_dir, "analysis")
        ]
        
        subprocess.run(analyze_cmd)
        
        print(f"\nBenchmark completed successfully!")
        print(f"Results saved in: {output_dir}")
        return True
        
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user!")
        return False
    except Exception as e:
        print(f"\nError during benchmark: {e}")
        return False
    finally:
        # Ensure monitor is stopped
        if monitor_process.poll() is None:
            monitor_process.terminate()
            try:
                monitor_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                monitor_process.kill()

def main():
    parser = argparse.ArgumentParser(description="Run M2M RSP benchmark with monitoring")
    parser.add_argument("--clients", type=int, default=10, help="Number of clients to simulate")
    parser.add_argument("--concurrency", type=int, default=5, help="Maximum concurrent clients")
    parser.add_argument("--ramp-up", type=float, default=0, help="Ramp-up time in seconds")
    parser.add_argument("--monitor-interval", type=float, default=0.5, help="Monitoring interval in seconds")
    
    args = parser.parse_args()
    
    success = run_benchmark(
        num_clients=args.clients,
        concurrent_clients=args.concurrency,
        ramp_up=args.ramp_up,
        monitor_interval=args.monitor_interval
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 
import json
import os
import glob
import argparse
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

def load_test_results(load_test_file):
    """Load results from a load test file"""
    with open(load_test_file, 'r') as f:
        return json.load(f)

def load_metrics(metrics_file):
    """Load metrics from a server monitoring file"""
    with open(metrics_file, 'r') as f:
        return json.load(f)

def analyze_bottlenecks(load_test_file, metrics_file, output_dir="output/analysis"):
    """Analyze bottlenecks and correlate with resource usage"""
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Load data
    load_results = load_test_results(load_test_file)
    metrics = load_metrics(metrics_file)
    
    # Extract bottlenecks
    bottlenecks = load_results.get("bottlenecks", [])
    
    # Prepare report
    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "load_test_file": load_test_file,
        "metrics_file": metrics_file,
        "bottlenecks": bottlenecks,
        "analysis": []
    }
    
    # Generate timing distribution charts
    operations = load_results.get("operations", {})
    if operations:
        plt.figure(figsize=(14, 8))
        
        # Sort operations by average time
        sorted_ops = sorted(operations.items(), key=lambda x: x[1]["avg"], reverse=True)
        
        # Plot average times
        names = [op[0] for op in sorted_ops]
        avgs = [op[1]["avg"] for op in sorted_ops]
        
        # Create bar chart
        plt.bar(range(len(names)), avgs, color='skyblue')
        plt.xticks(range(len(names)), names, rotation=45, ha="right")
        plt.xlabel('Operations')
        plt.ylabel('Average Time (seconds)')
        plt.title('Operation Average Times')
        plt.grid(axis='y', alpha=0.3)
        
        # Add threshold line
        plt.axhline(y=5.0, color='r', linestyle='-', label='Bottleneck Threshold (5s)')
        plt.legend()
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/operation_times.png")
        plt.close()
        
        # Generate resource usage during bottlenecks
        if bottlenecks and metrics["metrics"]:
            # Extract timestamps for metrics
            metric_timestamps = [m["timestamp"] for m in metrics["metrics"]]
            cpu_usage = [m["cpu_percent"] for m in metrics["metrics"]]
            memory_usage = [m["memory_percent"] for m in metrics["metrics"]]
            
            plt.figure(figsize=(14, 8))
            plt.plot(metric_timestamps, cpu_usage, 'b-', label='CPU %')
            plt.plot(metric_timestamps, memory_usage, 'r-', label='Memory %')
            
            # Mark bottleneck thresholds
            plt.axhline(y=80, color='orange', linestyle='--', label='Resource Warning (80%)')
            plt.axhline(y=90, color='red', linestyle='--', label='Resource Critical (90%)')
            
            plt.xlabel('Time (seconds)')
            plt.ylabel('Percentage')
            plt.title('Resource Usage During Load Test')
            plt.legend()
            plt.grid(True)
            plt.tight_layout()
            plt.savefig(f"{output_dir}/resource_usage.png")
            
            # Generate analysis report
            for bottleneck in bottlenecks:
                name = bottleneck["name"]
                avg_time = bottleneck["avg_time"]
                
                # Find if there were resource spikes during this operation
                cpu_spikes = [i for i, cpu in enumerate(cpu_usage) if cpu > 80]
                mem_spikes = [i for i, mem in enumerate(memory_usage) if mem > 80]
                
                report["analysis"].append({
                    "bottleneck": name,
                    "avg_time": avg_time,
                    "cpu_spikes": len(cpu_spikes),
                    "memory_spikes": len(mem_spikes),
                    "recommendation": generate_recommendation(name, avg_time, len(cpu_spikes), len(mem_spikes))
                })
    
    # Save analysis report
    output_file = f"{output_dir}/bottleneck_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Analysis completed. Report saved to {output_file}")
    print(f"Charts saved to {output_dir}/")
    
    # Print summary to console
    print("\n=== BOTTLENECK ANALYSIS ===")
    for analysis in report["analysis"]:
        print(f"\nBottleneck: {analysis['bottleneck']}")
        print(f"  Average Time: {analysis['avg_time']:.2f}s")
        print(f"  CPU Spikes: {analysis['cpu_spikes']}")
        print(f"  Memory Spikes: {analysis['memory_spikes']}")
        print(f"  Recommendation: {analysis['recommendation']}")
    
    return report

def generate_recommendation(operation, avg_time, cpu_spikes, mem_spikes):
    """Generate a recommendation based on the bottleneck and resource usage"""
    if "Profile Preparation" in operation:
        if cpu_spikes > 5:
            return "CPU-bound bottleneck in Profile Preparation. Consider optimizing cryptographic operations and data encoding."
        elif mem_spikes > 5:
            return "Memory-bound bottleneck in Profile Preparation. Check for large object allocations and implement more efficient data structures."
        else:
            return "Bottleneck in Profile Preparation with no resource spikes. Likely I/O or network related."
    elif "Profile Enabling" in operation:
        if cpu_spikes > 5:
            return "CPU-bound bottleneck in Profile Enabling. Optimize encryption/decryption operations."
        else:
            return "Bottleneck in Profile Enabling with no significant resource spikes. May be network or protocol related."
    elif "Key Establishment" in operation:
        return "Bottleneck in Key Establishment. This is typically CPU-bound due to cryptographic operations. Consider optimizing ECDH implementation."
    elif "Installation" in operation:
        return "Bottleneck in Profile Installation. Check for excessive I/O operations or network latency."
    else:
        return f"Bottleneck in {operation}. Investigate the specific operation implementation."

def main():
    parser = argparse.ArgumentParser(description="Analyze load test bottlenecks")
    parser.add_argument("--load-test", type=str, required=True, help="Load test results file")
    parser.add_argument("--metrics", type=str, required=True, help="Server metrics file")
    parser.add_argument("--output", type=str, default="output/analysis", help="Output directory")
    
    args = parser.parse_args()
    
    analyze_bottlenecks(args.load_test, args.metrics, args.output)

if __name__ == "__main__":
    main()
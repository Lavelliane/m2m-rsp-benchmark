#!/usr/bin/env python3
"""
Script to extract CSV metrics from k6 load test output logs.
Parses console output and generates a clean CSV file with the requested headers:
vus, iterations, cpu_percent, memory_percent, time
"""

import sys
import re
import csv
import argparse
from datetime import datetime

def extract_metrics_from_log(log_file_path, output_csv_path):
    """
    Extract metrics from k6 log output and save to CSV file.
    
    Args:
        log_file_path: Path to the k6 log file
        output_csv_path: Path to save the CSV output
    """
    
    metrics_data = []
    header_written = False
    
    try:
        with open(log_file_path, 'r') as log_file:
            for line in log_file:
                # Look for our metrics CSV lines
                if 'METRICS_CSV,' in line:
                    # Extract the CSV data after METRICS_CSV,
                    match = re.search(r'METRICS_CSV,(.+)', line)
                    if match:
                        csv_data = match.group(1).strip()
                        parts = csv_data.split(',')
                        
                        if len(parts) >= 5:
                            try:
                                vus = int(parts[0])
                                iterations = int(parts[1])
                                cpu_percent = float(parts[2])
                                memory_percent = float(parts[3])
                                time = parts[4]
                                
                                metrics_data.append({
                                    'vus': vus,
                                    'iterations': iterations,
                                    'cpu_percent': cpu_percent,
                                    'memory_percent': memory_percent,
                                    'time': time
                                })
                            except (ValueError, IndexError) as e:
                                print(f"Warning: Could not parse line: {line.strip()} - {e}")
                                continue
        
        # Write to CSV file
        if metrics_data:
            with open(output_csv_path, 'w', newline='') as csv_file:
                fieldnames = ['vus', 'iterations', 'cpu_percent', 'memory_percent', 'time']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                
                writer.writeheader()
                for row in metrics_data:
                    writer.writerow(row)
            
            print(f"Successfully extracted {len(metrics_data)} metric records to {output_csv_path}")
            
            # Print some statistics
            if metrics_data:
                cpu_values = [r['cpu_percent'] for r in metrics_data]
                memory_values = [r['memory_percent'] for r in metrics_data]
                
                print(f"\nMetrics Summary:")
                print(f"  Total records: {len(metrics_data)}")
                print(f"  CPU usage - Min: {min(cpu_values):.2f}%, Max: {max(cpu_values):.2f}%, Avg: {sum(cpu_values)/len(cpu_values):.2f}%")
                print(f"  Memory usage - Min: {min(memory_values):.2f}%, Max: {max(memory_values):.2f}%, Avg: {sum(memory_values)/len(memory_values):.2f}%")
                print(f"  VUs range: {min(r['vus'] for r in metrics_data)} - {max(r['vus'] for r in metrics_data)}")
        else:
            print("No metrics data found in log file")
            
    except FileNotFoundError:
        print(f"Error: Log file not found: {log_file_path}")
        return False
    except Exception as e:
        print(f"Error processing log file: {e}")
        return False
    
    return len(metrics_data) > 0

def main():
    parser = argparse.ArgumentParser(description='Extract CSV metrics from k6 load test logs')
    parser.add_argument('log_file', help='Path to the k6 log file')
    parser.add_argument('-o', '--output', default='smdp_metrics.csv', 
                       help='Output CSV file path (default: smdp_metrics.csv)')
    
    args = parser.parse_args()
    
    print(f"Extracting metrics from: {args.log_file}")
    print(f"Output CSV file: {args.output}")
    
    success = extract_metrics_from_log(args.log_file, args.output)
    
    if success:
        print(f"\nCSV file ready: {args.output}")
        print("You can now analyze the data or import it into your preferred analysis tool.")
    else:
        print("Failed to extract metrics data.")
        sys.exit(1)

if __name__ == "__main__":
    main() 
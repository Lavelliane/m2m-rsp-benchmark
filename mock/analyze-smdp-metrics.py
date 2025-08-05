#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
import sys
import os
from datetime import datetime
import argparse

def analyze_smdp_metrics(csv_file):
    """Analyze SM-DP metrics from CSV file"""
    
    print(f"🔍 Analyzing SM-DP metrics from: {csv_file}")
    print("=" * 50)
    
    try:
        # Load CSV data
        df = pd.read_csv(csv_file)
        
        # Basic statistics
        print("📊 Basic Statistics:")
        print(f"   Total data points: {len(df)}")
        print(f"   Test duration: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        print(f"   Max VUs: {df['vus'].max()}")
        print(f"   Total iterations: {df['iterations'].max()}")
        print()
        
        # CPU and Memory statistics
        print("🖥️  CPU & Memory Statistics:")
        print(f"   CPU Usage - Min: {df['cpu_percent'].min():.2f}% | Max: {df['cpu_percent'].max():.2f}% | Avg: {df['cpu_percent'].mean():.2f}%")
        print(f"   Memory Usage - Min: {df['mem_percent'].min():.2f}% | Max: {df['mem_percent'].max():.2f}% | Avg: {df['mem_percent'].mean():.2f}%")
        print(f"   Memory (MB) - Min: {df['memory_mb'].min():.2f} MB | Max: {df['memory_mb'].max():.2f} MB | Avg: {df['memory_mb'].mean():.2f} MB")
        print()
        
        # Peak usage analysis
        print("⚡ Peak Usage Analysis:")
        peak_cpu_idx = df['cpu_percent'].idxmax()
        peak_mem_idx = df['mem_percent'].idxmax()
        
        print(f"   Peak CPU usage: {df.loc[peak_cpu_idx, 'cpu_percent']:.2f}% (VUs: {df.loc[peak_cpu_idx, 'vus']}, Iterations: {df.loc[peak_cpu_idx, 'iterations']})")
        print(f"   Peak Memory usage: {df.loc[peak_mem_idx, 'mem_percent']:.2f}% (VUs: {df.loc[peak_mem_idx, 'vus']}, Iterations: {df.loc[peak_mem_idx, 'iterations']})")
        print()
        
        # Correlations
        print("📈 Performance Correlations:")
        cpu_vu_corr = df['cpu_percent'].corr(df['vus'])
        mem_vu_corr = df['mem_percent'].corr(df['vus'])
        
        print(f"   CPU vs VUs correlation: {cpu_vu_corr:.3f}")
        print(f"   Memory vs VUs correlation: {mem_vu_corr:.3f}")
        print()
        
        # Create visualizations
        create_visualizations(df, csv_file)
        
        return df
        
    except Exception as e:
        print(f"❌ Error analyzing metrics: {e}")
        return None

def create_visualizations(df, csv_file):
    """Create visualization plots"""
    
    print("📊 Creating visualizations...")
    
    # Create figure with subplots
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle('SM-DP Performance Metrics Analysis', fontsize=16)
    
    # Convert timestamp to datetime for plotting
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Plot 1: CPU and Memory usage over time
    ax1 = axes[0, 0]
    ax1.plot(df['timestamp'], df['cpu_percent'], label='CPU %', color='blue', linewidth=2)
    ax1.plot(df['timestamp'], df['mem_percent'], label='Memory %', color='red', linewidth=2)
    ax1.set_title('CPU & Memory Usage Over Time')
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Usage (%)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis='x', rotation=45)
    
    # Plot 2: VUs vs CPU usage
    ax2 = axes[0, 1]
    ax2.scatter(df['vus'], df['cpu_percent'], alpha=0.6, color='blue')
    ax2.set_title('VUs vs CPU Usage')
    ax2.set_xlabel('Virtual Users (VUs)')
    ax2.set_ylabel('CPU Usage (%)')
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: VUs vs Memory usage
    ax3 = axes[1, 0]
    ax3.scatter(df['vus'], df['mem_percent'], alpha=0.6, color='red')
    ax3.set_title('VUs vs Memory Usage')
    ax3.set_xlabel('Virtual Users (VUs)')
    ax3.set_ylabel('Memory Usage (%)')
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Memory usage in MB over time
    ax4 = axes[1, 1]
    ax4.plot(df['timestamp'], df['memory_mb'], color='green', linewidth=2)
    ax4.set_title('Memory Usage (MB) Over Time')
    ax4.set_xlabel('Time')
    ax4.set_ylabel('Memory (MB)')
    ax4.grid(True, alpha=0.3)
    ax4.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    
    # Save the plot
    plot_file = csv_file.replace('.csv', '_analysis.png')
    plt.savefig(plot_file, dpi=300, bbox_inches='tight')
    print(f"   📊 Visualization saved: {plot_file}")
    
    # Show the plot
    plt.show()

def main():
    parser = argparse.ArgumentParser(description='Analyze SM-DP performance metrics from CSV file')
    parser.add_argument('csv_file', nargs='?', help='Path to CSV file to analyze')
    
    args = parser.parse_args()
    
    if args.csv_file:
        csv_file = args.csv_file
    else:
        # Find the most recent CSV file
        csv_files = [f for f in os.listdir('.') if f.startswith('smdp_metrics_') and f.endswith('.csv')]
        if not csv_files:
            print("❌ No SM-DP metrics CSV files found in current directory")
            print("   Run the test first using: ./run-smdp-metrics-test.sh")
            sys.exit(1)
        
        csv_file = sorted(csv_files)[-1]  # Get the most recent file
        print(f"📁 Using most recent CSV file: {csv_file}")
    
    if not os.path.exists(csv_file):
        print(f"❌ CSV file not found: {csv_file}")
        sys.exit(1)
    
    # Analyze the metrics
    df = analyze_smdp_metrics(csv_file)
    
    if df is not None:
        print("✅ Analysis complete!")
        print(f"   Data analyzed from: {csv_file}")
        print(f"   Visualization saved as: {csv_file.replace('.csv', '_analysis.png')}")
    else:
        print("❌ Analysis failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 
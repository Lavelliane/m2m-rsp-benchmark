"""
Enhanced plot CPU and memory usage metrics with detailed analysis.

This script provides comprehensive visualizations of CPU and memory usage
for each M2M RSP operation including:
- Time series plots showing usage over time
- Distribution histograms
- Box plots showing quartiles and outliers
- Summary statistics
- Performance bottleneck analysis
"""

import argparse
import os
from typing import Dict, List, Any
import numpy as np
import requests
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import matplotlib.dates as mdates

# Set style for better-looking plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")

def fetch_metrics(base_url: str) -> Dict[str, List[dict]]:
    """Fetch JSON metrics from the running mock server."""
    print("Fetching metrics from server...")
    resp = requests.get(base_url.rstrip('/') + '/metrics', timeout=60)
    resp.raise_for_status()
    return resp.json()

def create_comprehensive_plots(metrics: Dict[str, List[dict]], out_dir: str) -> None:
    """Create comprehensive CPU and memory analysis plots."""
    
    if not metrics:
        print("No metrics returned – did you run any tests?")
        return

    os.makedirs(out_dir, exist_ok=True)
    
    # Filter out unwanted operations
    excluded_ops = ['get_metrics', 'status_verification']
    filtered_metrics = {k: v for k, v in metrics.items() 
                       if k not in excluded_ops and v}  # Also exclude empty lists
    
    if not filtered_metrics:
        print("No valid metrics data found after filtering.")
        return
    
    print(f"Analyzing {len(filtered_metrics)} operations: {list(filtered_metrics.keys())}")
    
    # Prepare data for analysis
    all_data = []
    for operation, records in filtered_metrics.items():
        if not records:
            continue
        df = pd.DataFrame(records)
        df['operation'] = operation.replace('_', ' ').title()
        df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='s')
        
        # Handle cases where execution_time_ms might not exist in older data
        if 'execution_time_ms' not in df.columns:
            df['execution_time_ms'] = 0.0
            
        all_data.append(df)
    
    if not all_data:
        print("No valid metrics data found.")
        return
    
    combined_df = pd.concat(all_data, ignore_index=True)
    
    # 1. Time Series Analysis
    create_time_series_plots(combined_df, out_dir)
    
    # 2. Distribution Analysis
    create_distribution_plots(combined_df, out_dir)
    
    # 3. Box Plot Analysis
    create_box_plots(combined_df, out_dir)
    
    # 4. Summary Statistics
    create_summary_table(combined_df, out_dir)
    
    # 5. Performance Bottleneck Analysis
    create_bottleneck_analysis(combined_df, out_dir)
    
    # 6. Load vs Performance Analysis
    create_load_performance_analysis(combined_df, out_dir)
    
    # 7. Execution Time Analysis
    create_execution_time_analysis(combined_df, out_dir)

def create_time_series_plots(df: pd.DataFrame, out_dir: str) -> None:
    """Create time series plots showing CPU and memory usage over time."""
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
    
    # CPU Usage over time
    for operation in df['operation'].unique():
        op_data = df[df['operation'] == operation]
        ax1.plot(op_data['timestamp_dt'], op_data['cpu_percent'], 
                label=operation, alpha=0.7, linewidth=1.5)
    
    ax1.set_title('CPU Usage Over Time by Operation', fontsize=14, fontweight='bold')
    ax1.set_ylabel('CPU Percentage (%)', fontsize=12)
    ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    
    # Memory Usage over time
    for operation in df['operation'].unique():
        op_data = df[df['operation'] == operation]
        ax2.plot(op_data['timestamp_dt'], op_data['memory_mb'], 
                label=operation, alpha=0.7, linewidth=1.5)
    
    ax2.set_title('Memory Usage Over Time by Operation', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax2.set_xlabel('Time', fontsize=12)
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'time_series_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print(f'Saved {os.path.join(out_dir, "time_series_analysis.png")}')

def create_distribution_plots(df: pd.DataFrame, out_dir: str) -> None:
    """Create histogram distributions for CPU and memory usage."""
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # CPU Distribution by Operation
    operations = df['operation'].unique()
    colors = sns.color_palette("husl", len(operations))
    
    for i, operation in enumerate(operations):
        op_data = df[df['operation'] == operation]['cpu_percent']
        ax1.hist(op_data, alpha=0.7, label=operation, color=colors[i], bins=30)
    
    ax1.set_title('CPU Usage Distribution by Operation', fontsize=14, fontweight='bold')
    ax1.set_xlabel('CPU Percentage (%)', fontsize=12)
    ax1.set_ylabel('Frequency', fontsize=12)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Memory Distribution by Operation
    for i, operation in enumerate(operations):
        op_data = df[df['operation'] == operation]['memory_mb']
        ax2.hist(op_data, alpha=0.7, label=operation, color=colors[i], bins=30)
    
    ax2.set_title('Memory Usage Distribution by Operation', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Memory Usage (MB)', fontsize=12)
    ax2.set_ylabel('Frequency', fontsize=12)
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Combined CPU violin plot
    sns.violinplot(data=df, x='operation', y='cpu_percent', ax=ax3)
    ax3.set_title('CPU Usage Distribution (Violin Plot)', fontsize=14, fontweight='bold')
    ax3.set_ylabel('CPU Percentage (%)', fontsize=12)
    ax3.set_xlabel('Operation', fontsize=12)
    ax3.tick_params(axis='x', rotation=45)
    
    # Combined Memory violin plot
    sns.violinplot(data=df, x='operation', y='memory_mb', ax=ax4)
    ax4.set_title('Memory Usage Distribution (Violin Plot)', fontsize=14, fontweight='bold')
    ax4.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax4.set_xlabel('Operation', fontsize=12)
    ax4.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'distribution_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print(f'Saved {os.path.join(out_dir, "distribution_analysis.png")}')

def create_box_plots(df: pd.DataFrame, out_dir: str) -> None:
    """Create box plots showing quartiles and outliers."""
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    
    # CPU Box Plot
    sns.boxplot(data=df, x='operation', y='cpu_percent', ax=ax1)
    ax1.set_title('CPU Usage Box Plot by Operation', fontsize=14, fontweight='bold')
    ax1.set_ylabel('CPU Percentage (%)', fontsize=12)
    ax1.set_xlabel('Operation', fontsize=12)
    ax1.tick_params(axis='x', rotation=45)
    ax1.grid(True, alpha=0.3)
    
    # Memory Box Plot
    sns.boxplot(data=df, x='operation', y='memory_mb', ax=ax2)
    ax2.set_title('Memory Usage Box Plot by Operation', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax2.set_xlabel('Operation', fontsize=12)
    ax2.tick_params(axis='x', rotation=45)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'box_plot_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print(f'Saved {os.path.join(out_dir, "box_plot_analysis.png")}')

def create_summary_table(df: pd.DataFrame, out_dir: str) -> None:
    """Create and save summary statistics table."""
    
    # Calculate summary statistics
    summary_stats = []
    
    for operation in df['operation'].unique():
        op_data = df[df['operation'] == operation]
        
        cpu_stats = op_data['cpu_percent'].describe()
        mem_stats = op_data['memory_mb'].describe()
        exec_stats = op_data['execution_time_ms'].describe()
        
        summary_stats.append({
            'Operation': operation,
            'CPU_Mean': f"{cpu_stats['mean']:.2f}%",
            'CPU_Std': f"{cpu_stats['std']:.2f}%",
            'CPU_P95': f"{np.percentile(op_data['cpu_percent'], 95):.2f}%",
            'Memory_Mean': f"{mem_stats['mean']:.2f} MB",
            'Memory_Std': f"{mem_stats['std']:.2f} MB",
            'Memory_P95': f"{np.percentile(op_data['memory_mb'], 95):.2f} MB",
            'Exec_Time_Mean': f"{exec_stats['mean']:.2f} ms",
            'Exec_Time_P95': f"{np.percentile(op_data['execution_time_ms'], 95):.2f} ms",
            'Sample_Count': int(cpu_stats['count'])
        })
    
    summary_df = pd.DataFrame(summary_stats)
    
    # Save as CSV
    csv_path = os.path.join(out_dir, 'performance_summary.csv')
    summary_df.to_csv(csv_path, index=False)
    print(f'Saved {csv_path}')
    
    # Create a visual table
    fig, ax = plt.subplots(figsize=(22, 8))
    ax.axis('tight')
    ax.axis('off')
    
    table = ax.table(cellText=summary_df.values, colLabels=summary_df.columns,
                    cellLoc='center', loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.2, 1.5)
    
    # Style the table
    for (i, j), cell in table.get_celld().items():
        if i == 0:  # Header row
            cell.set_text_props(weight='bold')
            cell.set_facecolor('#40466e')
            cell.set_text_props(color='white')
        else:
            cell.set_facecolor('#f1f1f2')
    
    plt.title('Performance Summary Statistics', fontsize=16, fontweight='bold', pad=20)
    plt.savefig(os.path.join(out_dir, 'performance_summary_table.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print(f'Saved {os.path.join(out_dir, "performance_summary_table.png")}')

def create_bottleneck_analysis(df: pd.DataFrame, out_dir: str) -> None:
    """Identify and visualize performance bottlenecks."""
    
    # Calculate resource efficiency metrics
    efficiency_data = []
    
    for operation in df['operation'].unique():
        op_data = df[df['operation'] == operation]
        
        cpu_mean = op_data['cpu_percent'].mean()
        cpu_p95 = np.percentile(op_data['cpu_percent'], 95)
        mem_mean = op_data['memory_mb'].mean()
        mem_p95 = np.percentile(op_data['memory_mb'], 95)
        
        # Calculate efficiency score (lower is better)
        cpu_efficiency = cpu_p95 / max(cpu_mean, 0.1)  # Avoid division by zero
        mem_efficiency = mem_p95 / max(mem_mean, 0.1)
        
        efficiency_data.append({
            'Operation': operation,
            'CPU_Mean': cpu_mean,
            'CPU_P95': cpu_p95,
            'CPU_Efficiency': cpu_efficiency,
            'Memory_Mean': mem_mean,
            'Memory_P95': mem_p95,
            'Memory_Efficiency': mem_efficiency,
            'Total_Score': (cpu_efficiency + mem_efficiency) / 2
        })
    
    efficiency_df = pd.DataFrame(efficiency_data)
    efficiency_df = efficiency_df.sort_values('Total_Score', ascending=False)
    
    # Create bottleneck visualization
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # CPU Bottleneck Analysis
    ax1.barh(efficiency_df['Operation'], efficiency_df['CPU_Mean'], 
             alpha=0.7, label='Average CPU', color='lightblue')
    ax1.barh(efficiency_df['Operation'], efficiency_df['CPU_P95'], 
             alpha=0.7, label='95th Percentile CPU', color='darkblue')
    ax1.set_title('CPU Usage: Average vs 95th Percentile', fontsize=14, fontweight='bold')
    ax1.set_xlabel('CPU Percentage (%)', fontsize=12)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Memory Bottleneck Analysis
    ax2.barh(efficiency_df['Operation'], efficiency_df['Memory_Mean'], 
             alpha=0.7, label='Average Memory', color='lightgreen')
    ax2.barh(efficiency_df['Operation'], efficiency_df['Memory_P95'], 
             alpha=0.7, label='95th Percentile Memory', color='darkgreen')
    ax2.set_title('Memory Usage: Average vs 95th Percentile', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Memory Usage (MB)', fontsize=12)
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Efficiency Scores
    colors = ['red' if score > 2 else 'orange' if score > 1.5 else 'green' 
              for score in efficiency_df['Total_Score']]
    ax3.barh(efficiency_df['Operation'], efficiency_df['Total_Score'], color=colors)
    ax3.set_title('Performance Efficiency Score (Lower is Better)', fontsize=14, fontweight='bold')
    ax3.set_xlabel('Efficiency Score', fontsize=12)
    ax3.grid(True, alpha=0.3)
    
    # Resource utilization scatter
    scatter = ax4.scatter(efficiency_df['CPU_Mean'], efficiency_df['Memory_Mean'], 
                         s=100, c=efficiency_df['Total_Score'], cmap='RdYlGn_r', alpha=0.7)
    for i, operation in enumerate(efficiency_df['Operation']):
        ax4.annotate(operation, (efficiency_df.iloc[i]['CPU_Mean'], efficiency_df.iloc[i]['Memory_Mean']),
                    xytext=(5, 5), textcoords='offset points', fontsize=8)
    ax4.set_title('CPU vs Memory Usage by Operation', fontsize=14, fontweight='bold')
    ax4.set_xlabel('Average CPU Usage (%)', fontsize=12)
    ax4.set_ylabel('Average Memory Usage (MB)', fontsize=12)
    ax4.grid(True, alpha=0.3)
    plt.colorbar(scatter, ax=ax4, label='Efficiency Score')
    
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'bottleneck_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print(f'Saved {os.path.join(out_dir, "bottleneck_analysis.png")}')

def create_load_performance_analysis(df: pd.DataFrame, out_dir: str) -> None:
    """Analyze how performance changes with load over time."""
    
    # Add time-based buckets to analyze performance trends
    df = df.copy()
    df['time_bucket'] = pd.cut(df['timestamp'], bins=10, labels=[f'T{i+1}' for i in range(10)])
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # Performance over time buckets - CPU
    time_cpu_data = df.groupby(['time_bucket', 'operation'])['cpu_percent'].mean().reset_index()
    pivot_cpu = time_cpu_data.pivot(index='time_bucket', columns='operation', values='cpu_percent')
    pivot_cpu.plot(kind='bar', ax=ax1, rot=45)
    ax1.set_title('Average CPU Usage Over Time', fontsize=14, fontweight='bold')
    ax1.set_ylabel('CPU Percentage (%)', fontsize=12)
    ax1.set_xlabel('Time Period', fontsize=12)
    ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # Performance over time buckets - Memory
    time_mem_data = df.groupby(['time_bucket', 'operation'])['memory_mb'].mean().reset_index()
    pivot_mem = time_mem_data.pivot(index='time_bucket', columns='operation', values='memory_mb')
    pivot_mem.plot(kind='bar', ax=ax2, rot=45)
    ax2.set_title('Average Memory Usage Over Time', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax2.set_xlabel('Time Period', fontsize=12)
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.grid(True, alpha=0.3)
    
    # Load correlation analysis
    for operation in df['operation'].unique():
        op_data = df[df['operation'] == operation]
        if len(op_data) > 1:
            # Use timestamp as proxy for load (later timestamps = higher load)
            ax3.scatter(op_data['timestamp'], op_data['cpu_percent'], 
                       label=operation, alpha=0.6)
    ax3.set_title('CPU Usage vs Time (Load Progression)', fontsize=14, fontweight='bold')
    ax3.set_ylabel('CPU Percentage (%)', fontsize=12)
    ax3.set_xlabel('Timestamp', fontsize=12)
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # Memory progression
    for operation in df['operation'].unique():
        op_data = df[df['operation'] == operation]
        if len(op_data) > 1:
            ax4.scatter(op_data['timestamp'], op_data['memory_mb'], 
                       label=operation, alpha=0.6)
    ax4.set_title('Memory Usage vs Time (Load Progression)', fontsize=14, fontweight='bold')
    ax4.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax4.set_xlabel('Timestamp', fontsize=12)
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'load_performance_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print(f'Saved {os.path.join(out_dir, "load_performance_analysis.png")}')

def create_execution_time_analysis(df: pd.DataFrame, out_dir: str) -> None:
    """Analyze execution time distribution and correlation with CPU and memory usage."""
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
    
    # Execution Time Distribution
    sns.histplot(df['execution_time_ms'], ax=ax1, kde=True)
    ax1.set_title('Execution Time Distribution', fontsize=14, fontweight='bold')
    ax1.set_xlabel('Execution Time (ms)', fontsize=12)
    ax1.set_ylabel('Frequency', fontsize=12)
    
    # Execution Time vs CPU Usage
    ax2.scatter(df['execution_time_ms'], df['cpu_percent'], alpha=0.6)
    ax2.set_title('Execution Time vs CPU Usage', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Execution Time (ms)', fontsize=12)
    ax2.set_ylabel('CPU Percentage (%)', fontsize=12)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'execution_time_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print(f'Saved {os.path.join(out_dir, "execution_time_analysis.png")}')

def main():
    parser = argparse.ArgumentParser(description='Enhanced CPU and memory metrics analysis.')
    parser.add_argument('--url', default='http://localhost:8080', 
                       help='Base URL where the mock server is listening.')
    parser.add_argument('--output', default='./enhanced_plots', 
                       help='Directory to store generated plots.')
    args = parser.parse_args()

    print("Starting enhanced metrics analysis...")
    metrics = fetch_metrics(args.url)
    
    if not metrics:
        print("No metrics data available. Make sure the server is running and has processed some requests.")
        return
    
    print(f"Found metrics for {len(metrics)} operations")
    for operation, records in metrics.items():
        print(f"  {operation}: {len(records)} samples")
    
    create_comprehensive_plots(metrics, args.output)
    print(f"\nEnhanced analysis complete! Check {args.output} for detailed visualizations.")

if __name__ == '__main__':
    main() 
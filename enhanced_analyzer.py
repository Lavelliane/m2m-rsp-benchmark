#!/usr/bin/env python3
"""
Enhanced Analysis Script for M2M RSP Load Testing
Provides detailed performance analysis, bottleneck detection, 
correlation analysis, and actionable recommendations
"""

import json
import os
import glob
import argparse
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from datetime import datetime
from scipy.stats import pearsonr, spearmanr
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import warnings
import sys
from tabulate import tabulate
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
from collections import defaultdict
import re

class EnhancedAnalyzer:
    def __init__(self, load_test_file, metrics_file=None, output_dir="output/analysis",
                bottleneck_threshold=5.0, correlation_threshold=0.7):
        self.load_test_file = load_test_file
        self.metrics_file = metrics_file
        self.output_dir = output_dir
        self.bottleneck_threshold = bottleneck_threshold
        self.correlation_threshold = correlation_threshold
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize data containers
        self.load_results = None
        self.metrics = None
        self.detailed_metrics = None
        self.performance_data = None
        self.analysis_results = {}
        
        # Load data
        self._load_data()
        
    def _load_data(self):
        """Load data from the load test and metrics files"""
        print(f"Loading load test results from {self.load_test_file}")
        try:
            with open(self.load_test_file, 'r') as f:
                self.load_results = json.load(f)
        except Exception as e:
            print(f"Error loading load test results: {e}")
            self.load_results = None
        
        if self.metrics_file:
            print(f"Loading metrics from {self.metrics_file}")
            try:
                with open(self.metrics_file, 'r') as f:
                    self.metrics = json.load(f)
            except Exception as e:
                print(f"Error loading metrics: {e}")
                self.metrics = None
        
        # Extract raw metrics for detailed analysis
        if self.metrics:
            self.detailed_metrics = self.metrics.get("metrics", [])
    
    def _prepare_performance_data(self):
        """Prepare performance data for analysis"""
        if not self.load_results:
            print("No load test results available for analysis")
            return False
        
        # Extract client results
        raw_results = self.load_results.get("raw_results", [])
        if not raw_results:
            print("No raw results available in the load test data")
            return False
        
        # Prepare data frames for analysis
        client_data = []
        operation_data = []
        
        for client in raw_results:
            client_id = client.get("client_id", "unknown")
            success = client.get("success", False)
            total_time = client.get("total_time", 0)
            
            # Add client summary
            client_data.append({
                "client_id": client_id,
                "success": success,
                "total_time": total_time
            })
            
            # Add operation details
            for op in client.get("operations", []):
                operation_data.append({
                    "client_id": client_id,
                    "operation": op.get("name", "unknown"),
                    "time": op.get("time", 0),
                    "success": success
                })
        
        # Convert to pandas DataFrames
        self.client_df = pd.DataFrame(client_data)
        self.operation_df = pd.DataFrame(operation_data)
        
        # Create performance summary
        if not self.operation_df.empty:
            # Overall statistics per operation
            self.operation_stats = self.operation_df.groupby("operation")["time"].agg([
                "count", "min", "max", "mean", "median", "std"
            ]).reset_index()
            
            # Mark bottlenecks
            self.operation_stats["is_bottleneck"] = self.operation_stats["mean"] > self.bottleneck_threshold
            
            # Calculate percentiles
            percentiles = [50, 90, 95, 99]
            for p in percentiles:
                self.operation_stats[f"p{p}"] = self.operation_df.groupby("operation")["time"].quantile(p/100)
            
            # Sort by mean time (descending)
            self.operation_stats = self.operation_stats.sort_values("mean", ascending=False)
            
            # Store in analysis results
            self.analysis_results["operation_stats"] = self.operation_stats.to_dict(orient="records")
            
            # Create time-series representation
            if self.detailed_metrics:
                # Try to match operation times with server metrics
                self._match_operations_with_metrics()
            
            return True
        else:
            print("No operation data available for analysis")
            return False
    
    def _match_operations_with_metrics(self):
        """Match operation times with server metrics"""
        if not self.detailed_metrics:
            return
        
        # Create a time-based index for metrics
        metrics_times = [m["timestamp"] for m in self.detailed_metrics]
        if not metrics_times:
            return
        
        # Try to estimate the start time of the load test
        # This is an approximation based on the first few clients
        successful_clients = self.client_df[self.client_df["success"] == True]
        if successful_clients.empty:
            return
        
        # Use the metrics time range
        metrics_start = min(metrics_times)
        metrics_end = max(metrics_times)
        
        # Match operations with metrics time frame
        # This is approximate since we don't have exact timestamps for operations
        if self.operation_df is not None and not self.operation_df.empty:
            # Calculate approximate timestamps (for visualization only)
            # This assumes operations happened sequentially within each client
            self.operation_df["approx_start"] = metrics_start
            
            # Store in results
            self.analysis_results["time_matched"] = True
    
    def analyze_performance(self):
        """Analyze performance data"""
        print("Analyzing performance data...")
        
        # Prepare performance data
        if not self._prepare_performance_data():
            return False
        
        # 1. Overall success rate analysis
        self._analyze_success_rates()
        
        # 2. Operation performance analysis
        self._analyze_operation_performance()
        
        # 3. Bottleneck analysis
        self._analyze_bottlenecks()
        
        # 4. Resource correlation analysis (if metrics available)
        if self.metrics:
            self._analyze_resource_correlation()
        
        # 5. Perform anomaly detection
        self._detect_anomalies()
        
        # 6. Generate recommendations
        self._generate_recommendations()
        
        return True
    
    def _analyze_success_rates(self):
        """Analyze success rates"""
        if self.client_df is None or self.client_df.empty:
            return
        
        # Calculate overall success rate
        total_clients = len(self.client_df)
        successful_clients = self.client_df["success"].sum()
        success_rate = (successful_clients / total_clients) * 100 if total_clients > 0 else 0
        
        # Calculate success rate per operation
        op_success = self.operation_df.groupby("operation")["success"].agg(["count", "sum"])
        op_success["rate"] = (op_success["sum"] / op_success["count"]) * 100
        
        # Store results
        self.analysis_results["success_rates"] = {
            "overall": {
                "total": int(total_clients),
                "successful": int(successful_clients),
                "rate": float(success_rate)
            },
            "operations": op_success.reset_index().to_dict(orient="records")
        }
    
    def _analyze_operation_performance(self):
        """Analyze operation performance"""
        if self.operation_stats is None or self.operation_stats.empty:
            return
        
        # Calculate coefficient of variation (CV) for stability analysis
        self.operation_stats["cv"] = (self.operation_stats["std"] / self.operation_stats["mean"]) * 100
        
        # Identify unstable operations (high variability)
        self.operation_stats["is_unstable"] = self.operation_stats["cv"] > 50  # CV > 50% is considered unstable
        
        # Store results
        self.analysis_results["operation_performance"] = {
            "stats": self.operation_stats.to_dict(orient="records"),
            "unstable_operations": self.operation_stats[self.operation_stats["is_unstable"]]["operation"].tolist()
        }
    
    def _analyze_bottlenecks(self):
        """Analyze bottlenecks"""
        if self.operation_stats is None or self.operation_stats.empty:
            return
        
        # Identify bottlenecks
        bottlenecks = self.operation_stats[self.operation_stats["is_bottleneck"]]
        
        # Calculate contribution to total time
        total_mean_time = self.operation_stats["mean"].sum()
        
        if total_mean_time > 0:
            bottlenecks["contribution"] = (bottlenecks["mean"] / total_mean_time) * 100
        else:
            bottlenecks["contribution"] = 0
        
        # Store results
        self.analysis_results["bottlenecks"] = {
            "threshold": float(self.bottleneck_threshold),
            "identified": bottlenecks.to_dict(orient="records"),
            "count": len(bottlenecks)
        }
    
    def _analyze_resource_correlation(self):
        """Analyze correlation between performance and resource usage"""
        if not self.detailed_metrics or self.operation_df is None or self.operation_df.empty:
            return
        
        # Extract system metrics time series
        timestamps = []
        cpu_usage = []
        memory_usage = []
        disk_read = []
        disk_write = []
        net_recv = []
        net_sent = []
        
        for m in self.detailed_metrics:
            timestamps.append(m["timestamp"])
            cpu_usage.append(m["system"]["cpu_percent"])
            memory_usage.append(m["system"]["memory_percent"])
            disk_read.append(m["disk"]["read_rate_kb"])
            disk_write.append(m["disk"]["write_rate_kb"])
            net_recv.append(m["network"]["recv_rate_kb"])
            net_sent.append(m["network"]["sent_rate_kb"])
        
        # Create a DataFrame for metrics
        metrics_df = pd.DataFrame({
            "timestamp": timestamps,
            "cpu_percent": cpu_usage,
            "memory_percent": memory_usage,
            "disk_read_kb": disk_read,
            "disk_write_kb": disk_write,
            "net_recv_kb": net_recv,
            "net_sent_kb": net_sent
        })
        
        # Identify time periods with high CPU/memory usage
        high_cpu_periods = metrics_df[metrics_df["cpu_percent"] > 80]
        high_memory_periods = metrics_df[metrics_df["memory_percent"] > 80]
        
        # Analyze process metrics if available
        process_metrics = []
        
        for m in self.detailed_metrics:
            if "processes" in m:
                for pid, p_info in m["processes"].items():
                    if p_info.get("metrics"):
                        process_metrics.append({
                            "timestamp": m["timestamp"],
                            "pid": pid,
                            "name": p_info.get("name", "unknown"),
                            "cpu_percent": p_info["metrics"].get("cpu_percent", 0),
                            "memory_percent": p_info["metrics"].get("memory", {}).get("percent", 0)
                        })
        
        # Create a DataFrame for process metrics
        if process_metrics:
            process_df = pd.DataFrame(process_metrics)
            
            # Find processes with high CPU/memory usage
            high_cpu_processes = process_df[process_df["cpu_percent"] > 50].groupby("name")["cpu_percent"].mean().reset_index()
            high_memory_processes = process_df[process_df["memory_percent"] > 50].groupby("name")["memory_percent"].mean().reset_index()
            
            # Store results
            self.analysis_results["resource_usage"] = {
                "high_cpu_periods": {
                    "count": len(high_cpu_periods),
                    "timestamps": high_cpu_periods["timestamp"].tolist() if len(high_cpu_periods) < 100 else []
                },
                "high_memory_periods": {
                    "count": len(high_memory_periods),
                    "timestamps": high_memory_periods["timestamp"].tolist() if len(high_memory_periods) < 100 else []
                },
                "high_cpu_processes": high_cpu_processes.to_dict(orient="records"),
                "high_memory_processes": high_memory_processes.to_dict(orient="records")
            }
    
    def _detect_anomalies(self):
        """Detect anomalies in operation performance"""
        if self.operation_df is None or self.operation_df.empty:
            return
        
        anomalies = []
        
        # Analyze each operation type
        for operation in self.operation_df["operation"].unique():
            # Get operation times
            op_times = self.operation_df[self.operation_df["operation"] == operation]["time"].values
            
            if len(op_times) < 5:
                # Not enough data for anomaly detection
                continue
            
            # Use simple statistical method for anomaly detection
            mean = np.mean(op_times)
            std = np.std(op_times)
            
            # Define anomaly threshold (3 standard deviations)
            threshold = mean + 3 * std
            
            # Find anomalies
            anomaly_indices = np.where(op_times > threshold)[0]
            
            if len(anomaly_indices) > 0:
                # Get client IDs for anomalies
                clients = self.operation_df[self.operation_df["operation"] == operation].iloc[anomaly_indices]["client_id"].values
                times = op_times[anomaly_indices]
                
                for i, client_id in enumerate(clients):
                    anomalies.append({
                        "operation": operation,
                        "client_id": int(client_id),
                        "time": float(times[i]),
                        "threshold": float(threshold),
                        "mean": float(mean),
                        "deviation": float((times[i] - mean) / std)
                    })
        
        # Store results
        self.analysis_results["anomalies"] = {
            "count": len(anomalies),
            "detected": anomalies
        }
    
    def _generate_recommendations(self):
        """Generate recommendations based on analysis"""
        recommendations = []
        
        # 1. Check for bottlenecks
        if "bottlenecks" in self.analysis_results:
            bottlenecks = self.analysis_results["bottlenecks"]
            
            for bottleneck in bottlenecks.get("identified", []):
                operation = bottleneck.get("operation", "")
                mean_time = bottleneck.get("mean", 0)
                contribution = bottleneck.get("contribution", 0)
                
                if "Profile Preparation" in operation:
                    recommendations.append({
                        "target": operation,
                        "impact": "high" if contribution > 30 else "medium",
                        "issue": f"Slow profile preparation (avg: {mean_time:.2f}s, {contribution:.1f}% of total time)",
                        "recommendation": "Optimize profile preparation by implementing template caching, reducing cryptographic operations, and improving data serialization efficiency."
                    })
                
                elif "Key Establishment" in operation:
                    recommendations.append({
                        "target": operation,
                        "impact": "high" if contribution > 20 else "medium",
                        "issue": f"Slow key establishment (avg: {mean_time:.2f}s, {contribution:.1f}% of total time)",
                        "recommendation": "Optimize ECDH implementation, consider key caching, and use hardware acceleration for cryptographic operations if available."
                    })
                
                elif "Profile Enabling" in operation:
                    recommendations.append({
                        "target": operation,
                        "impact": "high" if contribution > 25 else "medium",
                        "issue": f"Slow profile enabling (avg: {mean_time:.2f}s, {contribution:.1f}% of total time)",
                        "recommendation": "Reduce command overhead, optimize PSK-TLS encryption/decryption, and implement more efficient error handling."
                    })
                
                elif "Profile" in operation and "Installation" in operation:
                    recommendations.append({
                        "target": operation,
                        "impact": "medium",
                        "issue": f"Slow profile installation (avg: {mean_time:.2f}s, {contribution:.1f}% of total time)",
                        "recommendation": "Optimize profile decryption and installation process, reduce I/O operations, and implement parallel processing where possible."
                    })
                
                else:
                    recommendations.append({
                        "target": operation,
                        "impact": "medium" if contribution > 15 else "low",
                        "issue": f"Slow operation: {operation} (avg: {mean_time:.2f}s, {contribution:.1f}% of total time)",
                        "recommendation": "Profile this operation to identify specific bottlenecks and optimize accordingly."
                    })
        
        # 2. Check for unstable operations
        if "operation_performance" in self.analysis_results:
            unstable_ops = self.analysis_results["operation_performance"].get("unstable_operations", [])
            
            for operation in unstable_ops:
                if operation not in [r["target"] for r in recommendations]:
                    recommendations.append({
                        "target": operation,
                        "impact": "medium",
                        "issue": f"Highly variable performance in {operation}",
                        "recommendation": "Investigate causes of performance variability. Check for resource contention, network issues, or system load imbalances."
                    })
        
        # 3. Check for resource issues
        if "resource_usage" in self.analysis_results:
            resource_usage = self.analysis_results["resource_usage"]
            
            if resource_usage.get("high_cpu_periods", {}).get("count", 0) > 5:
                recommendations.append({
                    "target": "System Resources",
                    "impact": "high",
                    "issue": "Frequent high CPU usage during test",
                    "recommendation": "Optimize CPU-intensive operations, consider scaling horizontally, or allocate more CPU resources to handle the load."
                })
            
            if resource_usage.get("high_memory_periods", {}).get("count", 0) > 5:
                recommendations.append({
                    "target": "System Resources",
                    "impact": "high",
                    "issue": "Frequent high memory usage during test",
                    "recommendation": "Check for memory leaks, optimize memory usage in profile handling, and consider increasing available memory."
                })
            
            # Process-specific recommendations
            for process in resource_usage.get("high_cpu_processes", []):
                recommendations.append({
                    "target": f"Process: {process.get('name', 'unknown')}",
                    "impact": "medium",
                    "issue": f"High CPU usage (avg: {process.get('cpu_percent', 0):.1f}%)",
                    "recommendation": "Profile this process to identify CPU-intensive operations and optimize accordingly."
                })
            
            for process in resource_usage.get("high_memory_processes", []):
                recommendations.append({
                    "target": f"Process: {process.get('name', 'unknown')}",
                    "impact": "medium",
                    "issue": f"High memory usage (avg: {process.get('memory_percent', 0):.1f}%)",
                    "recommendation": "Check for memory leaks and optimize memory management in this process."
                })
        
        # 4. Check for anomalies
        if "anomalies" in self.analysis_results and self.analysis_results["anomalies"].get("count", 0) > 0:
            # Group anomalies by operation
            anomaly_counts = {}
            for anomaly in self.analysis_results["anomalies"].get("detected", []):
                op = anomaly.get("operation", "unknown")
                if op not in anomaly_counts:
                    anomaly_counts[op] = 0
                anomaly_counts[op] += 1
            
            for op, count in anomaly_counts.items():
                if count >= 3:  # Only report if multiple anomalies detected
                    recommendations.append({
                        "target": op,
                        "impact": "medium",
                        "issue": f"Performance anomalies detected ({count} instances)",
                        "recommendation": "Investigate specific conditions that lead to performance spikes in this operation."
                    })
        
        # 5. Check success rates
        if "success_rates" in self.analysis_results:
            overall_rate = self.analysis_results["success_rates"].get("overall", {}).get("rate", 100)
            
            if overall_rate < 95:
                recommendations.append({
                    "target": "System Reliability",
                    "impact": "critical",
                    "issue": f"Low success rate ({overall_rate:.1f}%)",
                    "recommendation": "Improve error handling, implement retry mechanisms, and investigate causes of failures."
                })
            
            # Check for operations with low success rates
            for op in self.analysis_results["success_rates"].get("operations", []):
                if op.get("rate", 100) < 90:
                    recommendations.append({
                        "target": op.get("operation", "unknown"),
                        "impact": "high",
                        "issue": f"Low success rate ({op.get('rate', 0):.1f}%)",
                        "recommendation": "Implement better error handling and retry mechanisms for this operation."
                    })
        
        # 6. Add scaling recommendations
        client_count = self.analysis_results.get("success_rates", {}).get("overall", {}).get("total", 0)
        if client_count > 0:
            if client_count >= 50:
                # High load test, add scaling recommendations
                recommendations.append({
                    "target": "System Scalability",
                    "impact": "medium",
                    "issue": f"System tested with {client_count} clients",
                    "recommendation": "Implement connection pooling, add load balancing, and consider distributed deployment for higher load scenarios."
                })
        
        # Save recommendations
        self.analysis_results["recommendations"] = sorted(recommendations, key=lambda x: {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3
        }.get(x["impact"], 4))
    
    def generate_report(self):
        """Generate a comprehensive analysis report"""
        if not self.analysis_results:
            print("No analysis results available")
            return
        
        # Create report timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Basic report information
        report = {
            "timestamp": timestamp,
            "load_test_file": self.load_test_file,
            "metrics_file": self.metrics_file,
            "analysis_results": self.analysis_results
        }
        
        # Save report to file
        report_file = os.path.join(self.output_dir, "analysis_report.json")
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Generate HTML report
        self._generate_html_report(report)
        
        # Generate charts
        self._generate_charts()
        
        print(f"Analysis report saved to {report_file}")
        print(f"HTML report saved to {os.path.join(self.output_dir, 'analysis_report.html')}")
    
    def _generate_html_report(self, report):
        """Generate an HTML report"""
        html_file = os.path.join(self.output_dir, "analysis_report.html")
        
        # Get key metrics
        success_rates = report["analysis_results"].get("success_rates", {})
        bottlenecks = report["analysis_results"].get("bottlenecks", {})
        recommendations = report["analysis_results"].get("recommendations", [])
        
        # Create HTML content
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>M2M RSP Load Test Analysis Report</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; color: #333; }}
        h1, h2, h3, h4 {{ color: #2c3e50; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background-color: #3498db; color: white; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; padding: 20px; background-color: #f9f9f9; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary-box {{ display: inline-block; padding: 15px; margin: 10px; background-color: #ecf0f1; border-radius: 5px; text-align: center; min-width: 150px; }}
        .summary-box h3 {{ margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #3498db; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .critical {{ background-color: #e74c3c; color: white; padding: 5px; border-radius: 3px; }}
        .high {{ background-color: #e67e22; color: white; padding: 5px; border-radius: 3px; }}
        .medium {{ background-color: #f39c12; color: white; padding: 5px; border-radius: 3px; }}
        .low {{ background-color: #2ecc71; color: white; padding: 5px; border-radius: 3px; }}
        .chart-container {{ margin: 20px 0; }}
        img {{ max-width: 100%; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>M2M RSP Load Test Analysis Report</h1>
            <p>Generated on: {report["timestamp"]}</p>
        </div>
        
        <div class="section">
            <h2>Test Summary</h2>
            <div class="summary-box">
                <h3>Total Clients</h3>
                <p>{success_rates.get("overall", {}).get("total", 0)}</p>
            </div>
            <div class="summary-box">
                <h3>Success Rate</h3>
                <p>{success_rates.get("overall", {}).get("rate", 0):.1f}%</p>
            </div>
            <div class="summary-box">
                <h3>Bottlenecks</h3>
                <p>{bottlenecks.get("count", 0)}</p>
            </div>
            <div class="summary-box">
                <h3>Recommendations</h3>
                <p>{len(recommendations)}</p>
            </div>
        </div>
        
        <div class="section">
            <h2>Recommendations</h2>
            <table>
                <tr>
                    <th>Target</th>
                    <th>Impact</th>
                    <th>Issue</th>
                    <th>Recommendation</th>
                </tr>
        """
        
        # Add recommendations
        for rec in recommendations:
            impact_class = rec.get("impact", "low").lower()
            html_content += f"""
                <tr>
                    <td>{rec.get("target", "")}</td>
                    <td><span class="{impact_class}">{rec.get("impact", "").upper()}</span></td>
                    <td>{rec.get("issue", "")}</td>
                    <td>{rec.get("recommendation", "")}</td>
                </tr>
            """
        
        html_content += """
            </table>
        </div>
        """
        
        # Add operation performance
        if "operation_stats" in report["analysis_results"]:
            html_content += """
        <div class="section">
            <h2>Operation Performance</h2>
            <table>
                <tr>
                    <th>Operation</th>
                    <th>Count</th>
                    <th>Min (s)</th>
                    <th>Max (s)</th>
                    <th>Mean (s)</th>
                    <th>90th % (s)</th>
                    <th>Bottleneck</th>
                </tr>
            """
            
            for op in report["analysis_results"]["operation_stats"]:
                bottleneck = "Yes" if op.get("is_bottleneck", False) else "No"
                bottleneck_class = "critical" if op.get("is_bottleneck", False) else ""
                
                html_content += f"""
                <tr>
                    <td>{op.get("operation", "")}</td>
                    <td>{op.get("count", 0)}</td>
                    <td>{op.get("min", 0):.3f}</td>
                    <td>{op.get("max", 0):.3f}</td>
                    <td>{op.get("mean", 0):.3f}</td>
                    <td>{op.get("p90", 0):.3f}</td>
                    <td class="{bottleneck_class}">{bottleneck}</td>
                </tr>
                """
            
            html_content += """
            </table>
        </div>
            """
        
        # Add charts
        html_content += """
        <div class="section">
            <h2>Performance Charts</h2>
            <div class="chart-container">
                <h3>Operation Times</h3>
                <img src="operation_times.png" alt="Operation Times Chart">
            </div>
            
            <div class="chart-container">
                <h3>Operation Distribution</h3>
                <img src="operation_distribution.png" alt="Operation Distribution Chart">
            </div>
        """
        
        # Add system resource charts if available
        if self.metrics_file:
            html_content += """
            <div class="chart-container">
                <h3>System Resources</h3>
                <img src="system_resources.png" alt="System Resources Chart">
            </div>
            
            <div class="chart-container">
                <h3>Operation vs. Resources</h3>
                <img src="operation_resources.png" alt="Operation vs Resources Chart">
            </div>
            """
        
        html_content += """
        </div>
    </div>
</body>
</html>
        """
        
        # Write HTML to file
        with open(html_file, 'w') as f:
            f.write(html_content)
    
    def _generate_charts(self):
        """Generate analysis charts"""
        print("Generating analysis charts...")
        
        # Set style
        plt.style.use('ggplot')
        sns.set(style="whitegrid")
        
        # 1. Operation times chart
        self._generate_operation_times_chart()
        
        # 2. Operation distribution chart
        self._generate_operation_distribution_chart()
        
        # 3. System resources chart (if metrics available)
        if self.metrics:
            self._generate_system_resources_chart()
            
            # 4. Operation vs. Resources chart
            self._generate_operation_resources_chart()
    
    def _generate_operation_times_chart(self):
        """Generate chart for operation times"""
        if self.operation_stats is None or self.operation_stats.empty:
            return
        
        plt.figure(figsize=(14, 8))
        
        # Create bar chart of mean operation times
        operations = self.operation_stats["operation"].values
        mean_times = self.operation_stats["mean"].values
        std_times = self.operation_stats["std"].values
        is_bottleneck = self.operation_stats["is_bottleneck"].values
        
        # Set color based on bottleneck status
        colors = ['#e74c3c' if b else '#3498db' for b in is_bottleneck]
        
        # Plot bars
        bars = plt.bar(range(len(operations)), mean_times, color=colors)
        
        # Add error bars
        plt.errorbar(range(len(operations)), mean_times, yerr=std_times, fmt='none', ecolor='black', capsize=5)
        
        # Add bottleneck threshold line
        plt.axhline(y=self.bottleneck_threshold, color='red', linestyle='--', label=f'Bottleneck Threshold ({self.bottleneck_threshold}s)')
        
        # Add labels and title
        plt.xlabel('Operations')
        plt.ylabel('Mean Time (seconds)')
        plt.title('Mean Operation Time (with Standard Deviation)')
        plt.xticks(range(len(operations)), operations, rotation=45, ha='right')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Save chart
        plt.savefig(os.path.join(self.output_dir, "operation_times.png"), dpi=150)
        plt.close()
    
    def _generate_operation_distribution_chart(self):
        """Generate chart for operation time distribution"""
        if self.operation_df is None or self.operation_df.empty:
            return
        
        plt.figure(figsize=(14, 8))
        
        # Create box plot of operation times
        sns.boxplot(x="operation", y="time", data=self.operation_df)
        
        # Add individual points as swarm plot
        if len(self.operation_df) < 100:  # Only for smaller datasets
            sns.swarmplot(x="operation", y="time", data=self.operation_df, color='black', size=3, alpha=0.5)
        
        # Add bottleneck threshold line
        plt.axhline(y=self.bottleneck_threshold, color='red', linestyle='--', label=f'Bottleneck Threshold ({self.bottleneck_threshold}s)')
        
        # Add labels and title
        plt.xlabel('Operations')
        plt.ylabel('Time (seconds)')
        plt.title('Operation Time Distribution')
        plt.xticks(rotation=45, ha='right')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Save chart
        plt.savefig(os.path.join(self.output_dir, "operation_distribution.png"), dpi=150)
        plt.close()
    
    def _generate_system_resources_chart(self):
        """Generate chart for system resources over time"""
        if not self.detailed_metrics:
            return
        
        plt.figure(figsize=(14,
        10))
        
        # Create 4 subplots
        ax1 = plt.subplot(3, 1, 1)  # CPU
        ax2 = plt.subplot(3, 1, 2)  # Memory
        ax3 = plt.subplot(3, 1, 3)  # Disk and Network I/O
        
        # Extract data
        timestamps = [m["timestamp"] - self.detailed_metrics[0]["timestamp"] for m in self.detailed_metrics]
        cpu_percent = [m["system"]["cpu_percent"] for m in self.detailed_metrics]
        memory_percent = [m["system"]["memory_percent"] for m in self.detailed_metrics]
        disk_read = [m["disk"]["read_rate_kb"] for m in self.detailed_metrics]
        disk_write = [m["disk"]["write_rate_kb"] for m in self.detailed_metrics]
        net_recv = [m["network"]["recv_rate_kb"] for m in self.detailed_metrics]
        net_sent = [m["network"]["sent_rate_kb"] for m in self.detailed_metrics]
        
        # Plot CPU
        ax1.plot(timestamps, cpu_percent, 'b-', linewidth=2)
        ax1.set_ylabel('CPU Usage (%)')
        ax1.set_title('CPU Utilization')
        ax1.set_ylim(0, 100)
        ax1.grid(True, alpha=0.3)
        
        # Plot Memory
        ax2.plot(timestamps, memory_percent, 'r-', linewidth=2)
        ax2.set_ylabel('Memory Usage (%)')
        ax2.set_title('Memory Utilization')
        ax2.set_ylim(0, 100)
        ax2.grid(True, alpha=0.3)
        
        # Plot Disk and Network I/O
        ax3.plot(timestamps, disk_read, 'g-', linewidth=1.5, label='Disk Read (KB/s)')
        ax3.plot(timestamps, disk_write, 'y-', linewidth=1.5, label='Disk Write (KB/s)')
        ax3.plot(timestamps, net_recv, 'm-', linewidth=1.5, label='Net Recv (KB/s)')
        ax3.plot(timestamps, net_sent, 'c-', linewidth=1.5, label='Net Sent (KB/s)')
        ax3.set_xlabel('Elapsed Time (seconds)')
        ax3.set_ylabel('Rate (KB/s)')
        ax3.set_title('I/O Rates')
        ax3.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        
        # Adjust layout
        plt.tight_layout()
        
        # Save chart
        plt.savefig(os.path.join(self.output_dir, "system_resources.png"), dpi=150)
        plt.close()
    
    def _generate_operation_resources_chart(self):
        """Generate chart correlating operations with resource usage"""
        if not self.detailed_metrics or self.operation_df is None or self.operation_df.empty:
            return
        
        # This is a more complex chart that attempts to overlay operation timing
        # with resource usage. Since we don't have exact operation timestamps,
        # this is an approximation.
        
        plt.figure(figsize=(14, 10))
        
        # Extract data
        timestamps = [m["timestamp"] - self.detailed_metrics[0]["timestamp"] for m in self.detailed_metrics]
        cpu_percent = [m["system"]["cpu_percent"] for m in self.detailed_metrics]
        memory_percent = [m["system"]["memory_percent"] for m in self.detailed_metrics]
        
        # Plot CPU and Memory
        plt.plot(timestamps, cpu_percent, 'b-', linewidth=2, label='CPU (%)')
        plt.plot(timestamps, memory_percent, 'r-', linewidth=2, label='Memory (%)')
        
        # Add operation timing approximations
        # This requires additional information to accurately map operations to time
        # For now, we'll add vertical lines for estimated bottleneck regions
        if "bottlenecks" in self.analysis_results:
            bottlenecks = [b["operation"] for b in self.analysis_results["bottlenecks"].get("identified", [])]
            
            # Simplified approximation - divide timeline into equal segments
            total_time = timestamps[-1] if timestamps else 0
            if total_time > 0 and bottlenecks:
                segment_size = total_time / (len(bottlenecks) + 1)
                
                for i, bottleneck in enumerate(bottlenecks):
                    position = segment_size * (i + 1)
                    plt.axvline(x=position, color='#e74c3c', linestyle='--', alpha=0.7)
                    plt.text(position, 95, bottleneck, rotation=90, alpha=0.7, ha='right')
        
        # Add labels and title
        plt.xlabel('Elapsed Time (seconds)')
        plt.ylabel('Utilization (%)')
        plt.title('Resource Utilization Over Time with Operation Indicators')
        plt.legend(loc='upper right')
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 100)
        plt.tight_layout()
        
        # Save chart
        plt.savefig(os.path.join(self.output_dir, "operation_resources.png"), dpi=150)
        plt.close()
    
    def print_summary(self):
        """Print a summary of the analysis results"""
        if not self.analysis_results:
            print("No analysis results available")
            return
        
        # Get key metrics
        success_rates = self.analysis_results.get("success_rates", {})
        bottlenecks = self.analysis_results.get("bottlenecks", {})
        recommendations = self.analysis_results.get("recommendations", [])
        
        print("\n" + "="*80)
        print(" "*30 + "ANALYSIS SUMMARY")
        print("="*80)
        
        # Test information
        print("\nTest Information:")
        print(f"  Load Test File: {os.path.basename(self.load_test_file)}")
        if self.metrics_file:
            print(f"  Metrics File: {os.path.basename(self.metrics_file)}")
        
        # Success rates
        print("\nSuccess Rates:")
        print(f"  Total Clients: {success_rates.get('overall', {}).get('total', 0)}")
        print(f"  Successful Clients: {success_rates.get('overall', {}).get('successful', 0)}")
        print(f"  Success Rate: {success_rates.get('overall', {}).get('rate', 0):.1f}%")
        
        # Bottlenecks
        print("\nBottlenecks:")
        print(f"  Threshold: {bottlenecks.get('threshold', 0.0):.1f} seconds")
        print(f"  Detected: {bottlenecks.get('count', 0)}")
        
        if bottlenecks.get("identified"):
            print("\n  Bottleneck Details:")
            for bottleneck in bottlenecks.get("identified", []):
                print(f"    - {bottleneck.get('operation', '')}: {bottleneck.get('mean', 0):.2f}s (±{bottleneck.get('std', 0):.2f}s)")
                if "contribution" in bottleneck:
                    print(f"      Contribution: {bottleneck.get('contribution', 0):.1f}% of total time")
        
        # Recommendations
        print("\nTop Recommendations:")
        for rec in recommendations[:5]:  # Show top 5
            print(f"  - [{rec.get('impact', '').upper()}] {rec.get('issue', '')}")
            print(f"    Recommendation: {rec.get('recommendation', '')}")
        
        if len(recommendations) > 5:
            print(f"\n  ... and {len(recommendations) - 5} more recommendations (see full report).")
        
        # Operation statistics
        if "operation_stats" in self.analysis_results:
            print("\nOperation Performance Summary:")
            print(f"  {'Operation':<30} {'Count':>8} {'Min (s)':>10} {'Max (s)':>10} {'Mean (s)':>10} {'90th % (s)':>12}")
            print("  " + "-"*80)
            
            for op in self.analysis_results["operation_stats"][:5]:  # Show top 5
                print(f"  {op.get('operation', ''):<30} {op.get('count', 0):>8} {op.get('min', 0):>10.3f} {op.get('max', 0):>10.3f} {op.get('mean', 0):>10.3f} {op.get('p90', 0):>12.3f}")
        
        print("\n" + "="*80)
        print(f"Full analysis report saved to: {os.path.join(self.output_dir, 'analysis_report.html')}")
        print("="*80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Enhanced Analysis for M2M RSP Load Testing")
    parser.add_argument("--load-test", type=str, required=True, help="Load test results file")
    parser.add_argument("--metrics", type=str, help="Server metrics file")
    parser.add_argument("--output", type=str, default="output/analysis", help="Output directory")
    parser.add_argument("--threshold", type=float, default=5.0, help="Bottleneck threshold in seconds")
    parser.add_argument("--correlation", type=float, default=0.7, help="Correlation threshold")
    
    args = parser.parse_args()
    
    analyzer = EnhancedAnalyzer(
        load_test_file=args.load_test,
        metrics_file=args.metrics,
        output_dir=args.output,
        bottleneck_threshold=args.threshold,
        correlation_threshold=args.correlation
    )
    
    # Run analysis
    analyzer.analyze_performance()
    
    # Generate report
    analyzer.generate_report()
    
    # Print summary
    analyzer.print_summary()

if __name__ == "__main__":
    main()
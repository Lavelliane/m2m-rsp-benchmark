#!/usr/bin/env python3
"""
Enhanced System Monitoring for M2M RSP Load Testing
Provides detailed metrics on system resources, per-process statistics,
network traffic, and components health
"""

import psutil
import time
import datetime
import json
import os
import threading
import argparse
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import socket
import subprocess
import platform
import re
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

class EnhancedServerMonitor:
    def __init__(self, interval=0.5, output_file="server_metrics.json", 
                 pid_filter=None, port_filter=None):
        self.interval = interval
        self.output_file = output_file
        self.running = False
        self.metrics = []
        self.initial_io = None
        self.initial_net = None
        self.pid_filter = pid_filter or ["python"]  # Filter for Python processes by default
        self.port_filter = port_filter or [8001, 8002, 8003, 9001, 9002, 9003]  # M2M RSP ports
        self.process_history = {}  # Track processes by PID over time
        self.component_history = {}  # Track components by service name over time
        self.start_time = None
        
    def get_open_ports(self):
        """Get all open TCP ports and the processes using them"""
        ports = {}
        
        if platform.system() == "Windows":
            # Use netstat on Windows
            output = subprocess.check_output("netstat -ano", shell=True).decode()
            for line in output.split('\n'):
                if "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            local_addr = parts[1]
                            if ":" in local_addr:
                                port = int(local_addr.split(":")[-1])
                                pid = int(parts[4])
                                if port in self.port_filter:
                                    try:
                                        process = psutil.Process(pid)
                                        ports[port] = {
                                            "pid": pid,
                                            "name": process.name(),
                                            "cmdline": " ".join(process.cmdline())
                                        }
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        ports[port] = {"pid": pid, "name": "unknown", "cmdline": ""}
                        except (ValueError, IndexError):
                            pass
        else:
            # Use lsof on Unix-like systems
            try:
                for port in self.port_filter:
                    cmd = f"lsof -i :{port} -n -P"
                    try:
                        output = subprocess.check_output(cmd, shell=True).decode()
                        for line in output.split('\n')[1:]:  # Skip header
                            if line:
                                parts = line.split()
                                if len(parts) >= 9:
                                    process_name = parts[0]
                                    pid = int(parts[1])
                                    try:
                                        process = psutil.Process(pid)
                                        ports[port] = {
                                            "pid": pid,
                                            "name": process_name,
                                            "cmdline": " ".join(process.cmdline())
                                        }
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        ports[port] = {"pid": pid, "name": process_name, "cmdline": ""}
                    except subprocess.CalledProcessError:
                        # Port not in use
                        pass
            except Exception as e:
                print(f"Error getting open ports: {e}")
                
        return ports
    
    def get_component_metrics(self):
        """Get metrics for the RSP components based on port numbers"""
        port_mapping = {
            8001: "SM-DP (HTTP)",
            8002: "SM-SR (HTTP)",
            8003: "eUICC (HTTP)",
            9001: "SM-DP (HTTPS)",
            9002: "SM-SR (HTTPS)",
            9003: "eUICC (HTTPS)"
        }
        
        components = {}
        open_ports = self.get_open_ports()
        
        for port, details in open_ports.items():
            if port in port_mapping:
                component_name = port_mapping[port]
                
                try:
                    # Check if service is responsive
                    proto = "https" if port >= 9000 else "http"
                    url = f"{proto}://localhost:{port}/status"
                    
                    # Using socket to check basic connectivity instead of HTTP
                    # to avoid affecting performance during load test
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    result = s.connect_ex(('localhost', port))
                    responsive = (result == 0)
                    s.close()
                    
                    # Get process metrics if PID is known
                    performance_metrics = {}
                    if details.get("pid"):
                        try:
                            process = psutil.Process(details["pid"])
                            performance_metrics = {
                                "cpu_percent": process.cpu_percent(interval=None),
                                "memory_percent": process.memory_percent(),
                                "memory_mb": process.memory_info().rss / (1024 * 1024),
                                "threads": len(process.threads()),
                                "connections": len(process.connections()),
                                "open_files": len(process.open_files()),
                                "status": process.status()
                            }
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            print(f"Could not get metrics for process {details['pid']}: {e}")
                    
                    components[component_name] = {
                        "port": port,
                        "pid": details.get("pid"),
                        "responsive": responsive,
                        "metrics": performance_metrics
                    }
                    
                except Exception as e:
                    print(f"Error checking component {component_name}: {e}")
                    
        return components
    
    def collect_thread_stats(self, process):
        """Collect thread statistics for a given process"""
        thread_stats = []
        
        try:
            threads = process.threads()
            for thread in threads:
                # Get thread CPU times
                thread_stats.append({
                    "id": thread.id,
                    "user_time": thread.user_time,
                    "system_time": thread.system_time
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            # Process disappeared or no access
            pass
            
        return thread_stats
    
    def collect_process_metrics(self, process):
        """Collect detailed metrics for a single process"""
        try:
            # Get detailed process info
            with process.oneshot():  # Minimize system calls
                cpu_percent = process.cpu_percent(interval=None)
                mem_info = process.memory_info()
                context_switches = process.num_ctx_switches()
                io_counters = process.io_counters() if hasattr(process, 'io_counters') else None
                open_files = len(process.open_files())
                connections = len(process.connections())
                threads = self.collect_thread_stats(process)
            
            # Convert memory to MB
            rss_mb = mem_info.rss / (1024 * 1024)
            vms_mb = mem_info.vms / (1024 * 1024)
            
            # Calculate IO rates if we have history
            io_read_bytes = 0
            io_write_bytes = 0
            io_read_rate = 0
            io_write_rate = 0
            
            if io_counters:
                if process.pid in self.process_history:
                    prev_time = self.process_history[process.pid]["timestamp"]
                    prev_io = self.process_history[process.pid].get("io_counters")
                    
                    if prev_io:
                        time_diff = time.time() - prev_time
                        if time_diff > 0:
                            io_read_bytes = io_counters.read_bytes
                            io_write_bytes = io_counters.write_bytes
                            io_read_rate = (io_read_bytes - prev_io["read_bytes"]) / time_diff / 1024  # KB/s
                            io_write_rate = (io_write_bytes - prev_io["write_bytes"]) / time_diff / 1024  # KB/s
            
            # Create metrics object
            metrics = {
                "cpu_percent": cpu_percent,
                "memory": {
                    "rss_mb": rss_mb,
                    "vms_mb": vms_mb,
                    "percent": process.memory_percent()
                },
                "io": {
                    "read_bytes": io_read_bytes,
                    "write_bytes": io_write_bytes,
                    "read_rate_kb": io_read_rate,
                    "write_rate_kb": io_write_rate
                },
                "context_switches": {
                    "voluntary": context_switches.voluntary,
                    "involuntary": context_switches.involuntary
                },
                "open_files": open_files,
                "connections": connections,
                "thread_count": len(threads),
                "threads": threads,
                "status": process.status()
            }
            
            # Update process history
            self.process_history[process.pid] = {
                "timestamp": time.time(),
                "io_counters": {
                    "read_bytes": io_counters.read_bytes if io_counters else 0,
                    "write_bytes": io_counters.write_bytes if io_counters else 0
                } if io_counters else None
            }
            
            return metrics
            
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError) as e:
            # Process disappeared or no access
            if process.pid in self.process_history:
                del self.process_history[process.pid]
            return None
    
    def collect_metrics(self):
        """Collect system metrics at regular intervals"""
        while self.running:
            try:
                timestamp = time.time()
                current_time = datetime.datetime.fromtimestamp(timestamp)
                if not self.start_time:
                    self.start_time = timestamp
                
                # System-wide CPU and memory
                cpu_percent = psutil.cpu_percent(interval=None)
                cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
                memory = psutil.virtual_memory()
                swap = psutil.swap_memory()
                
                # System load (Unix-like systems only)
                try:
                    load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
                except (AttributeError, OSError):
                    load_avg = (0, 0, 0)
                
                # Disk I/O
                disk_io = psutil.disk_io_counters()
                
                # Calculate disk I/O rates
                disk_read_rate = 0
                disk_write_rate = 0
                
                if self.initial_io:
                    time_diff = timestamp - self.initial_io["timestamp"]
                    if time_diff > 0:
                        disk_read_rate = (disk_io.read_bytes - self.initial_io["read_bytes"]) / time_diff / 1024  # KB/s
                        disk_write_rate = (disk_io.write_bytes - self.initial_io["write_bytes"]) / time_diff / 1024  # KB/s
                
                self.initial_io = {
                    "timestamp": timestamp,
                    "read_bytes": disk_io.read_bytes,
                    "write_bytes": disk_io.write_bytes
                }
                
                # Network I/O
                net_io = psutil.net_io_counters()
                
                # Calculate network I/O rates
                net_sent_rate = 0
                net_recv_rate = 0
                
                if self.initial_net:
                    time_diff = timestamp - self.initial_net["timestamp"]
                    if time_diff > 0:
                        net_sent_rate = (net_io.bytes_sent - self.initial_net["bytes_sent"]) / time_diff / 1024  # KB/s
                        net_recv_rate = (net_io.bytes_recv - self.initial_net["bytes_recv"]) / time_diff / 1024  # KB/s
                
                self.initial_net = {
                    "timestamp": timestamp,
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv
                }
                
                # Get relevant processes
                processes = {}
                for process in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        process_info = process.info
                        name = process_info['name'].lower()
                        cmdline = " ".join(process_info['cmdline'] if process_info['cmdline'] else []).lower()
                        
                        # Check if it matches any filter
                        matched = False
                        for filter_term in self.pid_filter:
                            if filter_term.lower() in name or filter_term.lower() in cmdline:
                                matched = True
                                break
                                
                        if matched:
                            pid = process_info['pid']
                            processes[pid] = {
                                "name": process_info['name'],
                                "cmdline": process_info['cmdline'],
                                "metrics": self.collect_process_metrics(process)
                            }
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        continue
                
                # Get component-specific metrics
                components = self.get_component_metrics()
                
                # Store component history
                for name, data in components.items():
                    if name not in self.component_history:
                        self.component_history[name] = []
                    
                    # Store limited history (last 10 points)
                    if len(self.component_history[name]) > 10:
                        self.component_history[name].pop(0)
                    
                    self.component_history[name].append({
                        "timestamp": timestamp,
                        "responsive": data["responsive"],
                        "metrics": data["metrics"]
                    })
                
                # Store collected metrics
                self.metrics.append({
                    'timestamp': timestamp,
                    'elapsed_seconds': timestamp - self.start_time,
                    'datetime': current_time.strftime('%Y-%m-%d %H:%M:%S.%f'),
                    'system': {
                        'cpu_percent': cpu_percent,
                        'cpu_per_core': cpu_per_core,
                        'memory_percent': memory.percent,
                        'memory_used_mb': memory.used / (1024 * 1024),
                        'memory_available_mb': memory.available / (1024 * 1024),
                        'swap_percent': swap.percent,
                        'swap_used_mb': swap.used / (1024 * 1024),
                        'load_avg': load_avg
                    },
                    'disk': {
                        'read_count': disk_io.read_count,
                        'write_count': disk_io.write_count,
                        'read_bytes': disk_io.read_bytes,
                        'write_bytes': disk_io.write_bytes,
                        'read_rate_kb': disk_read_rate,
                        'write_rate_kb': disk_write_rate
                    },
                    'network': {
                        'bytes_sent': net_io.bytes_sent,
                        'bytes_recv': net_io.bytes_recv,
                        'packets_sent': net_io.packets_sent,
                        'packets_recv': net_io.packets_recv,
                        'errin': net_io.errin if hasattr(net_io, 'errin') else 0,
                        'errout': net_io.errout if hasattr(net_io, 'errout') else 0,
                        'sent_rate_kb': net_sent_rate,
                        'recv_rate_kb': net_recv_rate
                    },
                    'processes': processes,
                    'components': components
                })
                
            except Exception as e:
                print(f"Error collecting metrics: {e}")
                
            # Sleep until next collection
            time.sleep(self.interval)
    
    def start(self):
        """Start monitoring"""
        self.running = True
        self.thread = threading.Thread(target=self.collect_metrics)
        self.thread.daemon = True
        self.thread.start()
        print(f"Enhanced server monitoring started (interval: {self.interval}s)")
        
    def stop(self):
        """Stop monitoring and save results"""
        self.running = False
        if hasattr(self, 'thread') and self.thread:
            self.thread.join(timeout=2.0)
            
        # Save metrics to file
        if self.metrics:
            output_dir = os.path.dirname(self.output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            with open(self.output_file, 'w') as f:
                json.dump({
                    'version': '2.0',
                    'start_time': self.metrics[0]['datetime'],
                    'end_time': self.metrics[-1]['datetime'],
                    'duration_seconds': self.metrics[-1]['timestamp'] - self.metrics[0]['timestamp'],
                    'interval': self.interval,
                    'metrics': self.metrics
                }, f, indent=2)
                
            print(f"Server metrics saved to {self.output_file}")
    
    def generate_enhanced_charts(self, output_prefix="server_metrics"):
        """Generate enhanced charts from collected metrics"""
        if not self.metrics:
            print("No metrics to chart")
            return
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_prefix)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Set a consistent style
        plt.style.use('ggplot')
        sns.set(style="whitegrid")
        
        # Get timestamps and elapsed time for x-axis
        timestamps = [m['timestamp'] for m in self.metrics]
        elapsed_seconds = [m['elapsed_seconds'] for m in self.metrics]
        
        # 1. System Overview Chart (CPU, Memory, Swap)
        plt.figure(figsize=(14, 8))
        
        # Create two subplots
        ax1 = plt.subplot(2, 1, 1)
        ax2 = plt.subplot(2, 1, 2)
        
        # CPU usage and per-core
        cpu_percent = [m['system']['cpu_percent'] for m in self.metrics]
        
        # Get CPU cores data if available
        has_per_core = 'cpu_per_core' in self.metrics[0]['system']
        if has_per_core:
            cpu_cores = np.array([m['system']['cpu_per_core'] for m in self.metrics])
            num_cores = len(self.metrics[0]['system']['cpu_per_core'])
            
            # Plot each core
            for i in range(num_cores):
                ax1.plot(elapsed_seconds, cpu_cores[:, i], alpha=0.3, linewidth=1, 
                         label=f"Core {i}" if i < 4 else "")
        
        # Plot overall CPU
        ax1.plot(elapsed_seconds, cpu_percent, 'b-', linewidth=2, label='Overall CPU')
        ax1.set_ylim(0, 100)
        ax1.set_ylabel('CPU Usage (%)')
        ax1.set_title('CPU Utilization')
        ax1.grid(True, alpha=0.3)
        
        # Only show legend for first few cores to avoid clutter
        if has_per_core and num_cores > 0:
            ax1.legend(loc='upper right', fontsize='small', ncol=min(5, num_cores+1))
        
        # Memory and swap usage
        memory_percent = [m['system']['memory_percent'] for m in self.metrics]
        swap_percent = [m['system']['swap_percent'] for m in self.metrics]
        
        ax2.plot(elapsed_seconds, memory_percent, 'r-', linewidth=2, label='Memory')
        ax2.plot(elapsed_seconds, swap_percent, 'm-', linewidth=2, label='Swap')
        ax2.set_ylim(0, 100)
        ax2.set_xlabel('Elapsed Time (seconds)')
        ax2.set_ylabel('Usage (%)')
        ax2.set_title('Memory and Swap Utilization')
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper right')
        
        plt.tight_layout()
        plt.savefig(f"{output_prefix}_system.png", dpi=150)
        plt.close()
        
        # 2. I/O Performance Chart (Disk and Network)
        plt.figure(figsize=(14, 8))
        
        # Create two subplots
        ax1 = plt.subplot(2, 1, 1)
        ax2 = plt.subplot(2, 1, 2)
        
        # Disk I/O rates
        disk_read_rate = [m['disk']['read_rate_kb'] for m in self.metrics]
        disk_write_rate = [m['disk']['write_rate_kb'] for m in self.metrics]
        
        ax1.plot(elapsed_seconds, disk_read_rate, 'g-', linewidth=2, label='Read')
        ax1.plot(elapsed_seconds, disk_write_rate, 'y-', linewidth=2, label='Write')
        ax1.set_ylabel('Disk I/O (KB/s)')
        ax1.set_title('Disk I/O Performance')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper right')
        
        # Network I/O rates
        net_sent_rate = [m['network']['sent_rate_kb'] for m in self.metrics]
        net_recv_rate = [m['network']['recv_rate_kb'] for m in self.metrics]
        
        ax2.plot(elapsed_seconds, net_sent_rate, 'c-', linewidth=2, label='Sent')
        ax2.plot(elapsed_seconds, net_recv_rate, 'm-', linewidth=2, label='Received')
        ax2.set_xlabel('Elapsed Time (seconds)')
        ax2.set_ylabel('Network I/O (KB/s)')
        ax2.set_title('Network I/O Performance')
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper right')
        
        plt.tight_layout()
        plt.savefig(f"{output_prefix}_io.png", dpi=150)
        plt.close()
        
        # 3. Process Performance Heatmap
        # Extract process metrics if available
        process_data = {}
        for m in self.metrics:
            for pid, p_info in m['processes'].items():
                if p_info['metrics'] is not None:
                    # Convert PID to string for consistent keys
                    pid_str = str(pid)
                    if pid_str not in process_data:
                        process_data[pid_str] = {
                            'name': p_info['name'],
                            'cpu': [],
                            'memory': [],
                            'timestamps': []
                        }
                    
                    process_data[pid_str]['cpu'].append(p_info['metrics']['cpu_percent'])
                    process_data[pid_str]['memory'].append(p_info['metrics']['memory']['percent'])
                    process_data[pid_str]['timestamps'].append(m['elapsed_seconds'])
        
        # Generate process performance charts
        if process_data:
            plt.figure(figsize=(16, 10))
            
            # Create subplot grid based on number of processes
            n_processes = len(process_data)
            
            # Determine layout based on number of processes
            if n_processes <= 3:
                n_rows, n_cols = n_processes, 1
            elif n_processes <= 6:
                n_rows, n_cols = (n_processes + 1) // 2, 2
            else:
                n_rows, n_cols = (n_processes + 2) // 3, 3
            
            # Plot each process
            for i, (pid, data) in enumerate(process_data.items()):
                # Skip if not enough data points
                if len(data['cpu']) < 2:
                    continue
                
                ax = plt.subplot(n_rows, n_cols, i+1)
                
                ax.plot(data['timestamps'], data['cpu'], 'b-', linewidth=1.5, label='CPU %')
                ax.plot(data['timestamps'], data['memory'], 'r-', linewidth=1.5, label='Memory %')
                
                # Set title and labels
                ax.set_title(f"{data['name']} (PID: {pid})", fontsize=10)
                ax.set_xlabel('Time (s)', fontsize=8)
                ax.set_ylabel('%', fontsize=8)
                ax.grid(True, alpha=0.3)
                ax.legend(loc='upper right', fontsize=8)
                
                # Set y-axis limit
                ax.set_ylim(0, max(max(data['cpu']), max(data['memory'])) * 1.1)
            
            plt.tight_layout()
            plt.savefig(f"{output_prefix}_processes.png", dpi=150)
            plt.close()
        
        # 4. Component Health Dashboard
        component_data = {}
        for m in self.metrics:
            for name, c_info in m['components'].items():
                if name not in component_data:
                    component_data[name] = {
                        'responsive': [],
                        'cpu': [],
                        'memory': [],
                        'timestamps': []
                    }
                
                component_data[name]['responsive'].append(1 if c_info['responsive'] else 0)
                
                # Get metrics if available
                if 'metrics' in c_info and c_info['metrics']:
                    component_data[name]['cpu'].append(c_info['metrics'].get('cpu_percent', 0))
                    component_data[name]['memory'].append(c_info['metrics'].get('memory_percent', 0))
                else:
                    component_data[name]['cpu'].append(0)
                    component_data[name]['memory'].append(0)
                
                component_data[name]['timestamps'].append(m['elapsed_seconds'])
        
        # Generate component health dashboard
        if component_data:
            plt.figure(figsize=(16, 12))
            
            # Determine layout based on number of components
            n_components = len(component_data)
            n_rows = n_components
            n_cols = 3  # Three metrics per component
            
            # Plot each component
            for i, (name, data) in enumerate(component_data.items()):
                # Skip if not enough data points
                if len(data['timestamps']) < 2:
                    continue
                
                # Plot responsiveness
                ax1 = plt.subplot(n_rows, n_cols, i*n_cols + 1)
                ax1.plot(data['timestamps'], data['responsive'], 'g-', linewidth=2)
                ax1.set_title(f"{name}: Availability", fontsize=10)
                ax1.set_ylabel('Status (1=Up)', fontsize=8)
                ax1.set_ylim(-0.1, 1.1)
                ax1.set_yticks([0, 1])
                ax1.set_yticklabels(['Down', 'Up'])
                ax1.grid(True, alpha=0.3)
                
                # Plot CPU usage
                ax2 = plt.subplot(n_rows, n_cols, i*n_cols + 2)
                ax2.plot(data['timestamps'], data['cpu'], 'b-', linewidth=2)
                ax2.set_title(f"{name}: CPU Usage", fontsize=10)
                ax2.set_ylabel('CPU %', fontsize=8)
                ax2.set_ylim(0, 100)
                ax2.grid(True, alpha=0.3)
                
                # Plot memory usage
                ax3 = plt.subplot(n_rows, n_cols, i*n_cols + 3)
                ax3.plot(data['timestamps'], data['memory'], 'r-', linewidth=2)
                ax3.set_title(f"{name}: Memory Usage", fontsize=10)
                ax3.set_ylabel('Memory %', fontsize=8)
                ax3.set_ylim(0, 100)
                ax3.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(f"{output_prefix}_components.png", dpi=150)
            plt.close()
            
        print(f"Enhanced charts saved with prefix {output_prefix}")
        
        return {
            "system_chart": f"{output_prefix}_system.png",
            "io_chart": f"{output_prefix}_io.png",
            "processes_chart": f"{output_prefix}_processes.png",
            "components_chart": f"{output_prefix}_components.png"
        }

def main():
    parser = argparse.ArgumentParser(description="Enhanced Server Resource Monitoring")
    parser.add_argument("--interval", type=float, default=0.5, help="Monitoring interval in seconds")
    parser.add_argument("--output", type=str, default="output/server_metrics.json", help="Output file path")
    parser.add_argument("--duration", type=int, default=0, help="Monitoring duration in seconds (0 for manual stop)")
    parser.add_argument("--process-filter", type=str, default="python", 
                       help="Comma-separated list of process name filters")
    parser.add_argument("--port-filter", type=str, default="8001,8002,8003,9001,9002,9003", 
                       help="Comma-separated list of ports to monitor")
    
    args = parser.parse_args()
    
    # Parse filters
    pid_filter = args.process_filter.split(',')
    port_filter = [int(p) for p in args.port_filter.split(',') if p.isdigit()]
    
    # Create the monitor
    monitor = EnhancedServerMonitor(
        interval=args.interval, 
        output_file=args.output,
        pid_filter=pid_filter,
        port_filter=port_filter
    )
    
    try:
        print(f"Starting enhanced server monitoring (Interval: {args.interval}s)")
        print(f"Monitoring processes matching: {', '.join(pid_filter)}")
        print(f"Monitoring ports: {', '.join(map(str, port_filter))}")
        
        monitor.start()
        
        if args.duration > 0:
            print(f"Monitoring for {args.duration} seconds...")
            time.sleep(args.duration)
        else:
            print("Monitoring started. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nStopping monitoring...")
    finally:
        monitor.stop()
        charts = monitor.generate_enhanced_charts(output_prefix=os.path.splitext(args.output)[0])
        print("Monitoring completed. Output files:")
        for chart_type, chart_path in charts.items():
            print(f"- {chart_type}: {chart_path}")

if __name__ == "__main__":
    main()
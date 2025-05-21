import psutil
import time
import datetime
import json
import os
import threading
import argparse
import matplotlib.pyplot as plt

class ServerMonitor:
    def __init__(self, interval=1.0, output_file="server_metrics.json"):
        self.interval = interval
        self.output_file = output_file
        self.running = False
        self.metrics = []
        
    def collect_metrics(self):
        """Collect system metrics at regular intervals"""
        while self.running:
            try:
                timestamp = time.time()
                cpu_percent = psutil.cpu_percent(interval=None)
                memory = psutil.virtual_memory()
                
                # Collect network metrics
                net_io = psutil.net_io_counters()
                
                # Get process-specific stats for Python processes
                processes = {}
                for process in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
                    try:
                        # Filter for Python processes
                        if "python" in process.info['name'].lower():
                            processes[process.info['pid']] = {
                                'name': process.info['name'],
                                'cpu_percent': process.info['cpu_percent'],
                                'memory': process.info['memory_info'].rss / (1024 * 1024)  # MB
                            }
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                
                # Store collected metrics
                self.metrics.append({
                    'timestamp': timestamp,
                    'datetime': datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f'),
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_used_mb': memory.used / (1024 * 1024),
                    'net_bytes_sent': net_io.bytes_sent,
                    'net_bytes_recv': net_io.bytes_recv,
                    'processes': processes
                })
                
            except Exception as e:
                print(f"Error collecting metrics: {e}")
                
            time.sleep(self.interval)
            
    def start(self):
        """Start monitoring"""
        self.running = True
        self.thread = threading.Thread(target=self.collect_metrics)
        self.thread.daemon = True
        self.thread.start()
        print(f"Server monitoring started (interval: {self.interval}s)")
        
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
                    'start_time': self.metrics[0]['datetime'],
                    'end_time': self.metrics[-1]['datetime'],
                    'interval': self.interval,
                    'metrics': self.metrics
                }, f, indent=2)
                
            print(f"Server metrics saved to {self.output_file}")
            
    def generate_charts(self, output_prefix="server_metrics"):
        """Generate charts from collected metrics"""
        if not self.metrics:
            print("No metrics to chart")
            return
            
        timestamps = [m['timestamp'] - self.metrics[0]['timestamp'] for m in self.metrics]
        
        # CPU and Memory chart
        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, [m['cpu_percent'] for m in self.metrics], 'b-', label='CPU %')
        plt.plot(timestamps, [m['memory_percent'] for m in self.metrics], 'r-', label='Memory %')
        plt.xlabel('Time (seconds)')
        plt.ylabel('Percentage')
        plt.title('CPU and Memory Usage')
        plt.legend()
        plt.grid(True)
        
        # Save chart
        output_dir = os.path.dirname(output_prefix)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        plt.savefig(f"{output_prefix}_cpu_memory.png")
        
        # Network I/O chart
        plt.figure(figsize=(12, 6))
        sent = [m['net_bytes_sent'] for m in self.metrics]
        recv = [m['net_bytes_recv'] for m in self.metrics]
        
        # Convert to KB/s
        sent_rate = [(sent[i] - sent[i-1])/1024 if i > 0 else 0 for i in range(len(sent))]
        recv_rate = [(recv[i] - recv[i-1])/1024 if i > 0 else 0 for i in range(len(recv))]
        
        plt.plot(timestamps, sent_rate, 'g-', label='Sent (KB/s)')
        plt.plot(timestamps, recv_rate, 'm-', label='Received (KB/s)')
        plt.xlabel('Time (seconds)')
        plt.ylabel('KB/s')
        plt.title('Network I/O')
        plt.legend()
        plt.grid(True)
        plt.savefig(f"{output_prefix}_network.png")
        
        print(f"Charts saved with prefix {output_prefix}")

def main():
    parser = argparse.ArgumentParser(description="Server resource monitoring")
    parser.add_argument("--interval", type=float, default=0.5, help="Monitoring interval in seconds")
    parser.add_argument("--output", type=str, default="output/server_metrics.json", help="Output file path")
    parser.add_argument("--duration", type=int, default=0, help="Monitoring duration in seconds (0 for manual stop)")
    
    args = parser.parse_args()
    
    monitor = ServerMonitor(interval=args.interval, output_file=args.output)
    
    try:
        monitor.start()
        
        if args.duration > 0:
            print(f"Monitoring for {args.duration} seconds...")
            time.sleep(args.duration)
        else:
            print("Monitoring started. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("Stopping monitoring...")
    finally:
        monitor.stop()
        monitor.generate_charts(output_prefix=os.path.splitext(args.output)[0])

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
M2M RSP Service Mesh Benchmark Script
Tests M2M RSP workflows under increasing load across geographic zones
Exports detailed latency and performance metrics to CSV
"""

import asyncio
import aiohttp
import time
import csv
import json
import argparse
import statistics
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

@dataclass
class TestResult:
    timestamp: str
    zone: str
    endpoint: str
    workflow: str
    concurrent_users: int
    response_time: float
    status_code: int
    success: bool
    error_message: str = ""

@dataclass
class ZoneConfig:
    name: str
    location: str
    url: str
    expected_latency: str

class M2MRSPBenchmark:
    def __init__(self):
        self.zones = {
            'seoul': ZoneConfig('Seoul', 'South Korea (Local)', 'http://localhost:30080', '<10ms'),
            'virginia': ZoneConfig('Virginia', 'USA (Far)', 'http://localhost:30081', '~180ms'),
            'ireland': ZoneConfig('Ireland', 'Europe (Far)', 'http://localhost:30082', '~280ms'),
            'gateway': ZoneConfig('Gateway', 'Load Balanced', 'http://localhost:30852', 'Mixed')
        }
        
        # M2M RSP workflow endpoints (actual endpoints from mock server)
        self.workflows = {
            'status_check': '/status/smdp',
            'prepare_profile': '/smdp/profile/prepare',
            'key_establishment_init': '/smdp/key-establishment/init',
            'key_establishment_complete': '/smdp/key-establishment/complete',
            'register_euicc': '/smsr/euicc/register',
            'create_isdp': '/smsr/isdp/create',
            'install_profile': '/smsr/profile/install/test_euicc_123',
            'enable_profile': '/smsr/profile/enable/test_euicc_123',
            'metrics': '/metrics',
            'system_metrics': '/system-metrics'
        }
        
        self.results: List[TestResult] = []
        self.session: Optional[aiohttp.ClientSession] = None

    async def create_session(self):
        """Create aiohttp session with appropriate timeouts"""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
        self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()

    async def make_request(self, zone: str, workflow: str, method: str = 'GET', 
                          data: Optional[Dict] = None) -> Tuple[float, int, str]:
        """Make HTTP request and measure response time"""
        url = f"{self.zones[zone].url}{self.workflows[workflow]}"
        
        start_time = time.time()
        try:
            async with self.session.request(method, url, json=data) as response:
                content = await response.text()
                end_time = time.time()
                response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                return response_time, response.status, content
        except Exception as e:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            return response_time, 0, str(e)

    async def run_single_test(self, zone: str, workflow: str, concurrent_users: int, 
                             user_id: int) -> TestResult:
        """Run a single test request"""
        timestamp = datetime.now().isoformat()
        
        # Simulate different M2M RSP operations with correct payloads
        method = 'GET'
        data = None
        
        if workflow == 'prepare_profile':
            method = 'POST'
            data = {
                'profileType': 'telecom',
                'iccid': f'89001012{user_id:012d}'
            }
        elif workflow == 'key_establishment_init':
            method = 'POST'
            data = {}
        elif workflow == 'key_establishment_complete':
            method = 'POST'
            data = {
                'session_id': f'session_{user_id}',
                'public_key': 'test_public_key_base64'
            }
        elif workflow == 'register_euicc':
            method = 'POST'
            data = {
                'euiccId': f'test_euicc_{user_id}',
                'psk': f'psk_{user_id:016x}'
            }
        elif workflow == 'create_isdp':
            method = 'POST'
            data = {
                'euiccId': f'test_euicc_{user_id}',
                'memoryRequired': 1024
            }
        elif workflow in ['install_profile', 'enable_profile']:
            method = 'POST'
            data = {
                'profileId': f'profile_{user_id}'
            }
        
        response_time, status_code, content = await self.make_request(zone, workflow, method, data)
        
        success = 200 <= status_code < 300
        error_message = "" if success else content[:100]  # Truncate error message
        
        return TestResult(
            timestamp=timestamp,
            zone=self.zones[zone].name,
            endpoint=self.workflows[workflow],
            workflow=workflow,
            concurrent_users=concurrent_users,
            response_time=response_time,
            status_code=status_code,
            success=success,
            error_message=error_message
        )

    async def run_load_test(self, zone: str, workflow: str, concurrent_users: int, 
                           requests_per_user: int = 10) -> List[TestResult]:
        """Run load test for specific zone and workflow"""
        print(f"Testing {self.zones[zone].name} - {workflow} - {concurrent_users} concurrent users")
        
        tasks = []
        for user_id in range(concurrent_users):
            for request_id in range(requests_per_user):
                task = self.run_single_test(zone, workflow, concurrent_users, 
                                          user_id * requests_per_user + request_id)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and return valid results
        valid_results = [r for r in results if isinstance(r, TestResult)]
        return valid_results

    async def run_comprehensive_benchmark(self, max_concurrent_users: int = 100, 
                                        step_size: int = 10) -> None:
        """Run comprehensive benchmark across all zones and workflows"""
        print("🚀 Starting M2M RSP Service Mesh Benchmark")
        print(f"Max concurrent users: {max_concurrent_users}")
        print(f"Step size: {step_size}")
        print("=" * 60)
        
        await self.create_session()
        
        try:
            # Test load levels
            load_levels = list(range(step_size, max_concurrent_users + 1, step_size))
            
            # Primary workflows to test (start with most important)
            primary_workflows = ['status_check', 'prepare_profile', 'register_euicc', 'install_profile']
            secondary_workflows = ['key_establishment_init', 'create_isdp', 'enable_profile', 'metrics', 'system_metrics']
            
            total_tests = len(self.zones) * len(primary_workflows) * len(load_levels)
            test_count = 0
            
            # Test primary workflows under all load levels
            for workflow in primary_workflows:
                for concurrent_users in load_levels:
                    for zone in self.zones.keys():
                        test_count += 1
                        print(f"[{test_count}/{total_tests}] Testing {zone} - {workflow} - {concurrent_users} users")
                        
                        try:
                            results = await self.run_load_test(zone, workflow, concurrent_users, 
                                                             requests_per_user=5)
                            self.results.extend(results)
                            
                            # Brief pause between test batches
                            await asyncio.sleep(1)
                            
                        except Exception as e:
                            print(f"Error in test {zone}/{workflow}/{concurrent_users}: {e}")
            
            # Test secondary workflows at lower load levels
            secondary_load_levels = [10, 25, 50]  # Reduced load for secondary tests
            for workflow in secondary_workflows:
                for concurrent_users in secondary_load_levels:
                    for zone in ['seoul', 'gateway']:  # Test only key zones for secondary workflows
                        print(f"[Secondary] Testing {zone} - {workflow} - {concurrent_users} users")
                        
                        try:
                            results = await self.run_load_test(zone, workflow, concurrent_users, 
                                                             requests_per_user=3)
                            self.results.extend(results)
                            await asyncio.sleep(0.5)
                            
                        except Exception as e:
                            print(f"Error in secondary test {zone}/{workflow}/{concurrent_users}: {e}")
            
        finally:
            await self.close_session()

    def export_to_csv(self, filename: str = None) -> str:
        """Export results to CSV file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"m2m_rsp_benchmark_{timestamp}.csv"
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'timestamp', 'zone', 'endpoint', 'workflow', 'concurrent_users',
                'response_time_ms', 'status_code', 'success', 'error_message'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for result in self.results:
                writer.writerow({
                    'timestamp': result.timestamp,
                    'zone': result.zone,
                    'endpoint': result.endpoint,
                    'workflow': result.workflow,
                    'concurrent_users': result.concurrent_users,
                    'response_time_ms': f"{result.response_time:.2f}",
                    'status_code': result.status_code,
                    'success': result.success,
                    'error_message': result.error_message
                })
        
        return filename

    def generate_summary_report(self) -> Dict:
        """Generate summary statistics"""
        summary = {}
        
        for zone_key, zone_config in self.zones.items():
            zone_name = zone_config.name
            zone_results = [r for r in self.results if r.zone == zone_name]
            
            if not zone_results:
                continue
                
            summary[zone_name] = {
                'total_requests': len(zone_results),
                'success_rate': sum(1 for r in zone_results if r.success) / len(zone_results) * 100,
                'avg_response_time': statistics.mean(r.response_time for r in zone_results),
                'median_response_time': statistics.median(r.response_time for r in zone_results),
                'p95_response_time': sorted([r.response_time for r in zone_results])[int(len(zone_results) * 0.95)],
                'min_response_time': min(r.response_time for r in zone_results),
                'max_response_time': max(r.response_time for r in zone_results),
                'expected_latency': zone_config.expected_latency
            }
        
        return summary

    def export_summary_csv(self, filename: str = None) -> str:
        """Export summary statistics to CSV"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"m2m_rsp_summary_{timestamp}.csv"
        
        summary = self.generate_summary_report()
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'zone', 'location', 'total_requests', 'success_rate_percent',
                'avg_response_time_ms', 'median_response_time_ms', 'p95_response_time_ms',
                'min_response_time_ms', 'max_response_time_ms', 'expected_latency'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for zone_name, stats in summary.items():
                zone_config = next(z for z in self.zones.values() if z.name == zone_name)
                writer.writerow({
                    'zone': zone_name,
                    'location': zone_config.location,
                    'total_requests': stats['total_requests'],
                    'success_rate_percent': f"{stats['success_rate']:.2f}",
                    'avg_response_time_ms': f"{stats['avg_response_time']:.2f}",
                    'median_response_time_ms': f"{stats['median_response_time']:.2f}",
                    'p95_response_time_ms': f"{stats['p95_response_time']:.2f}",
                    'min_response_time_ms': f"{stats['min_response_time']:.2f}",
                    'max_response_time_ms': f"{stats['max_response_time']:.2f}",
                    'expected_latency': stats['expected_latency']
                })
        
        return filename

    def print_summary(self):
        """Print summary to console"""
        summary = self.generate_summary_report()
        
        print("\n" + "=" * 80)
        print("M2M RSP BENCHMARK SUMMARY")
        print("=" * 80)
        
        for zone_name, stats in summary.items():
            zone_config = next(z for z in self.zones.values() if z.name == zone_name)
            print(f"\n📍 {zone_name} ({zone_config.location})")
            print(f"   Expected Latency: {stats['expected_latency']}")
            print(f"   Total Requests: {stats['total_requests']:,}")
            print(f"   Success Rate: {stats['success_rate']:.2f}%")
            print(f"   Avg Response Time: {stats['avg_response_time']:.2f}ms")
            print(f"   Median Response Time: {stats['median_response_time']:.2f}ms")
            print(f"   95th Percentile: {stats['p95_response_time']:.2f}ms")
            print(f"   Min/Max: {stats['min_response_time']:.2f}ms / {stats['max_response_time']:.2f}ms")

async def main():
    parser = argparse.ArgumentParser(description='M2M RSP Service Mesh Benchmark')
    parser.add_argument('--max-users', type=int, default=50, help='Maximum concurrent users (default: 50)')
    parser.add_argument('--step-size', type=int, default=10, help='Load step size (default: 10)')
    parser.add_argument('--output-dir', type=str, default='.', help='Output directory for CSV files')
    parser.add_argument('--quick', action='store_true', help='Run quick test with reduced load')
    
    args = parser.parse_args()
    
    if args.quick:
        max_users = 20
        step_size = 5
        print("🚀 Running QUICK benchmark mode")
    else:
        max_users = args.max_users
        step_size = args.step_size
        print(f"🚀 Running FULL benchmark mode")
    
    print(f"Max users: {max_users}, Step size: {step_size}")
    print(f"Output directory: {args.output_dir}")
    
    benchmark = M2MRSPBenchmark()
    
    try:
        # Run the benchmark
        await benchmark.run_comprehensive_benchmark(max_users, step_size)
        
        # Export results
        detailed_csv = benchmark.export_to_csv(f"{args.output_dir}/m2m_rsp_detailed_results.csv")
        summary_csv = benchmark.export_summary_csv(f"{args.output_dir}/m2m_rsp_summary_results.csv")
        
        # Print summary
        benchmark.print_summary()
        
        print(f"\n📊 Results exported to:")
        print(f"   Detailed: {detailed_csv}")
        print(f"   Summary: {summary_csv}")
        print(f"\n✅ Benchmark completed successfully!")
        print(f"   Total requests: {len(benchmark.results):,}")
        
    except KeyboardInterrupt:
        print("\n🛑 Benchmark interrupted by user")
        if benchmark.results:
            detailed_csv = benchmark.export_to_csv(f"{args.output_dir}/m2m_rsp_partial_results.csv")
            print(f"📊 Partial results saved to: {detailed_csv}")
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        raise

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Run the benchmark
    asyncio.run(main()) 
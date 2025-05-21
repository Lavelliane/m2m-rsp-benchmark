import asyncio
import aiohttp
import time
import statistics
import argparse
import json
import os
from datetime import datetime

async def run_rsp_process(session, client_id):
    """Simulates a complete RSP process for a single eUICC"""
    start_time = time.time()
    results = {
        "client_id": client_id,
        "start_time": start_time,
        "operations": [],
        "success": False,
        "total_time": 0
    }
    
    try:
        # Step 1: Register eUICC with SM-SR
        reg_start = time.time()
        async with session.post("https://localhost:9002/euicc/register", 
                               json={"euiccId": f"8901234567890{client_id:05d}",
                                    "euiccInfo1": {
                                        "svn": "2.1.0",
                                        "euiccCiPKId": f"id{client_id}",
                                        "euiccCapabilities": {
                                            "supportedAlgorithms": ["ECKA-ECDH", "AES-128", "HMAC-SHA-256"],
                                            "secureDomainSupport": True,
                                            "pskSupport": True
                                        }
                                    },
                                   "smsrId": "SMSR-loadtest",
                                   "eid": f"89{client_id:010d}"
                                   }, 
                               ssl=False) as response:
            reg_data = await response.json()
            reg_time = time.time() - reg_start
            results["operations"].append({"name": "Registration", "time": reg_time})
            
            if reg_data.get("status") != "success":
                raise Exception(f"Registration failed: {reg_data.get('message')}")
                
        # Step 2: Create ISD-P
        isdp_start = time.time()
        async with session.post("https://localhost:9002/isdp/create", 
                               json={"euiccId": f"8901234567890{client_id:05d}", 
                                    "memoryRequired": 256}, 
                               ssl=False) as response:
            isdp_data = await response.json()
            isdp_time = time.time() - isdp_start
            results["operations"].append({"name": "ISD-P Creation", "time": isdp_time})
            
            if isdp_data.get("status") != "success":
                raise Exception(f"ISD-P creation failed: {isdp_data.get('message')}")
                
            isdp_aid = isdp_data.get("isdpAid")
                
        # Step 3: Key establishment (simulated)
        key_start = time.time()
        time.sleep(0.1)  # Simulate key establishment
        key_time = time.time() - key_start
        results["operations"].append({"name": "Key Establishment", "time": key_time})
        
        # Step 4: Profile preparation
        profile_start = time.time()
        profile_id = f"89012345{client_id:08d}"
        async with session.post("https://localhost:9001/profile/prepare", 
                               json={"profileType": "telecom", 
                                    "iccid": profile_id}, 
                               ssl=False) as response:
            profile_data = await response.json()
            profile_time = time.time() - profile_start
            results["operations"].append({"name": "Profile Preparation", "time": profile_time})
            
            if profile_data.get("status") != "success":
                raise Exception(f"Profile preparation failed: {profile_data.get('message')}")
        
        # Step 5: Profile Installation (simulated)
        install_start = time.time()
        async with session.post(f"https://localhost:9002/profile/install/8901234567890{client_id:05d}", 
                              json={"profileId": profile_id}, 
                              ssl=False) as response:
            install_data = await response.json()
            install_time = time.time() - install_start
            results["operations"].append({"name": "Profile Installation", "time": install_time})
            
            if install_data.get("status") != "success":
                raise Exception(f"Profile installation failed: {install_data.get('message')}")
                
        # Step 6: Profile Enabling
        enable_start = time.time()
        async with session.post(f"https://localhost:9002/profile/enable/8901234567890{client_id:05d}", 
                              json={"profileId": profile_id}, 
                              ssl=False) as response:
            enable_data = await response.json()
            enable_time = time.time() - enable_start
            results["operations"].append({"name": "Profile Enabling", "time": enable_time})
            
            if enable_data.get("status") != "success":
                raise Exception(f"Profile enabling failed: {enable_data.get('message')}")
        
        results["success"] = True
        results["total_time"] = time.time() - start_time
        return results
    
    except Exception as e:
        results["error"] = str(e)
        results["total_time"] = time.time() - start_time
        return results

async def load_test(num_clients, concurrent_clients, ramp_up_time=0):
    """Run a load test with the specified number of clients"""
    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = []
        results = []
        
        # Create the tasks with optional ramp-up time
        for i in range(num_clients):
            if ramp_up_time > 0 and i > 0:
                await asyncio.sleep(ramp_up_time / num_clients)
            task = asyncio.create_task(run_rsp_process(session, i+1))
            tasks.append(task)
            
            # Control concurrency
            if len(tasks) >= concurrent_clients:
                done, pending = await asyncio.wait(
                    tasks, 
                    return_when=asyncio.FIRST_COMPLETED
                )
                results.extend([t.result() for t in done])
                tasks = list(pending)
        
        # Wait for any remaining tasks
        if tasks:
            done, _ = await asyncio.wait(tasks)
            results.extend([t.result() for t in done])
            
        return results

def analyze_results(results, output_path=None):
    """Analyze the load test results"""
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    # Overall statistics
    total_times = [r["total_time"] for r in successful] if successful else [0]
    
    # Per-operation statistics
    operations = {}
    for result in successful:
        for op in result["operations"]:
            if op["name"] not in operations:
                operations[op["name"]] = []
            operations[op["name"]].append(op["time"])
    
    # Print summary
    print(f"\nLoad Test Results Summary:")
    print(f"Total clients: {len(results)}")
    print(f"Successful: {len(successful)} ({len(successful)/max(len(results),1)*100:.1f}%)")
    print(f"Failed: {len(failed)} ({len(failed)/max(len(results),1)*100:.1f}%)")
    
    if successful:
        print(f"\nOverall Response Time:")
        print(f"  Min: {min(total_times):.2f}s")
        print(f"  Max: {max(total_times):.2f}s")
        print(f"  Avg: {statistics.mean(total_times):.2f}s")
        print(f"  Median: {statistics.median(total_times):.2f}s")
        if len(total_times) > 1:
            print(f"  StdDev: {statistics.stdev(total_times):.2f}s")
    
    print("\nOperation Times (seconds):")
    print(f"{'Operation':<30} {'Min':>6} {'Max':>6} {'Avg':>6} {'Med':>6} {'StdDev':>6}")
    print("-" * 65)
    
    for op_name, times in operations.items():
        if times:
            avg = statistics.mean(times)
            med = statistics.median(times)
            std = statistics.stdev(times) if len(times) > 1 else 0
            print(f"{op_name:<30} {min(times):>6.2f} {max(times):>6.2f} {avg:>6.2f} {med:>6.2f} {std:>6.2f}")
    
    # Identify bottlenecks (operations taking > 5 seconds on average)
    bottlenecks = []
    for op_name, times in operations.items():
        if times and statistics.mean(times) > 5.0:  # Threshold of 5 seconds
            bottlenecks.append((op_name, statistics.mean(times)))
    
    print("\nPotential Bottlenecks:")
    if bottlenecks:
        for op_name, avg_time in sorted(bottlenecks, key=lambda x: x[1], reverse=True):
            print(f"  {op_name}: {avg_time:.2f}s average")
    else:
        print("  None identified (threshold: 5.0s)")
    
    # Save results to file
    if output_path:
        output_file = output_path
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("output/load_tests", exist_ok=True)
        output_file = f"output/load_tests/load_test_{timestamp}.json"
    
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump({
            "summary": {
                "total": len(results),
                "successful": len(successful),
                "failed": len(failed),
                "total_time_stats": {
                    "min": min(total_times) if total_times[0] > 0 else 0,
                    "max": max(total_times) if total_times[0] > 0 else 0,
                    "avg": statistics.mean(total_times) if total_times[0] > 0 else 0,
                    "median": statistics.median(total_times) if total_times[0] > 0 else 0,
                    "stdev": statistics.stdev(total_times) if len(total_times) > 1 and total_times[0] > 0 else 0
                }
            },
            "operations": {name: {
                "min": min(times),
                "max": max(times),
                "avg": statistics.mean(times),
                "median": statistics.median(times),
                "stdev": statistics.stdev(times) if len(times) > 1 else 0
            } for name, times in operations.items()},
            "bottlenecks": [{"name": name, "avg_time": time} for name, time in bottlenecks],
            "raw_results": results
        }, f, indent=2)
    
    print(f"\nDetailed results saved to {output_file}")
    return bottlenecks

async def main():
    parser = argparse.ArgumentParser(description="Load testing for M2M RSP")
    parser.add_argument("--clients", type=int, default=10, help="Number of clients to simulate")
    parser.add_argument("--concurrency", type=int, default=5, help="Maximum concurrent clients")
    parser.add_argument("--ramp-up", type=float, default=0, help="Ramp-up time in seconds")
    parser.add_argument("--output", type=str, help="Custom output file path for results")
    args = parser.parse_args()
    
    print(f"Starting load test with {args.clients} clients (max {args.concurrency} concurrent)")
    start_time = time.time()
    
    results = await load_test(args.clients, args.concurrency, args.ramp_up)
    
    print(f"\nLoad test completed in {time.time() - start_time:.2f} seconds")
    analyze_results(results, args.output)

if __name__ == "__main__":
    asyncio.run(main())
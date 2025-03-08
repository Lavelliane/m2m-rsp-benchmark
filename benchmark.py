"""
M2M Remote SIM Provisioning Protocol Benchmarking
This script runs the complete protocol for multiple iterations and reports average timings.
"""

import time
import statistics
from collections import defaultdict

# Import the protocol phases
from key_establishment import simulate_key_establishment
from isdp_creation import isdp_creation
from profile_download_installation import profile_download_and_installation
from app import TimingContext

class BenchmarkTimingContext(TimingContext):
    """Extended TimingContext to collect timing data for benchmarking"""
    
    # Static dictionary to collect timing data across all instances
    timing_data = defaultdict(list)
    
    def __init__(self, name):
        super().__init__(name)
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        
        # Store the timing data for this operation
        BenchmarkTimingContext.timing_data[self.name].append(self.duration)
        
        # Don't print timing for each iteration when benchmarking
        # Only print if we're in verbose mode
        if hasattr(BenchmarkTimingContext, 'verbose') and BenchmarkTimingContext.verbose:
            print(f"{self.name}: {self.duration:.6f} seconds")
    
    @classmethod
    def reset_timing_data(cls):
        """Reset the collected timing data"""
        cls.timing_data = defaultdict(list)
    
    @classmethod
    def get_timing_statistics(cls):
        """Calculate and return timing statistics"""
        stats = {}
        
        for name, times in cls.timing_data.items():
            if times:
                stats[name] = {
                    'min': min(times),
                    'max': max(times),
                    'avg': statistics.mean(times),
                    'median': statistics.median(times),
                    'stdev': statistics.stdev(times) if len(times) > 1 else 0,
                    'count': len(times)
                }
        
        return stats


def run_single_iteration(iteration_num, verbose=False):
    """Run a single iteration of the complete M2M RSP protocol"""
    # Save original verbose setting
    if hasattr(BenchmarkTimingContext, 'verbose'):
        old_verbose = BenchmarkTimingContext.verbose
    else:
        old_verbose = False
    
    # Set verbose mode for this iteration
    BenchmarkTimingContext.verbose = verbose
    
    iteration_start = time.time()
    
    with BenchmarkTimingContext(f"Complete Protocol (Iteration {iteration_num})"):
        # Execute ISDP creation (first step)
        with BenchmarkTimingContext("Phase I: ISDP Creation"):
            # Create fresh entities
            with BenchmarkTimingContext("Entities Initialization"):
                smdp = app.SMDP()
                euicc = app.EUICC()
                smsr = app.SMSR()
            
            # Execute ISDP creation
            isdp_result = isdp_creation.isdp_creation((euicc, smdp, smsr), silent=not verbose)
            
            if isdp_result and len(isdp_result) >= 4:
                euicc, smdp, smsr, isdp_id = isdp_result
                
                # Execute key establishment using ISDP data
                with BenchmarkTimingContext("Phase II: Key Establishment"):
                    entities = key_establishment.simulate_key_establishment((euicc, smdp, smsr, isdp_id), silent=not verbose)
                    
                    if entities and len(entities) >= 3:
                        euicc, smdp, smsr = entities[:3]
                        
                        # Execute profile download and installation using ES8 interface and SCP03t
                        with BenchmarkTimingContext("Phase III: Profile Download & Installation (ES8/SCP03t)"):
                            profile_download_installation.profile_download_and_installation((euicc, smdp, smsr, isdp_id), silent=not verbose)
    
    # Restore original verbose setting
    BenchmarkTimingContext.verbose = old_verbose
    
    return time.time() - iteration_start


def run_benchmark(iterations=1000, progress_interval=50, verbose_first=True, output_file="benchmark_results.txt"):
    """
    Run the M2M RSP protocol for the specified number of iterations
    
    Args:
        iterations: Number of iterations to run
        progress_interval: How often to print progress (every N iterations)
        verbose_first: Whether to print detailed timing for the first iteration
        output_file: File to save the results to (None for no file output)
    """
    print(f"\n=== Starting M2M RSP Protocol Benchmark ({iterations} iterations) ===\n")
    
    # Reset timing data before starting
    BenchmarkTimingContext.reset_timing_data()
    
    total_start_time = time.time()
    
    for i in range(iterations):
        # Run the iteration (verbose for first iteration if requested)
        run_single_iteration(i+1, verbose=(verbose_first and i==0))
        
        # Print progress at intervals
        if (i+1) % progress_interval == 0 or i+1 == iterations:
            print(f"Completed {i+1}/{iterations} iterations ({((i+1)/iterations)*100:.1f}%)")
    
    total_time = time.time() - total_start_time
    
    # Calculate and display timing statistics
    stats = BenchmarkTimingContext.get_timing_statistics()
    
    # Prepare the results output
    results_output = []
    results_output.append("\n=== Benchmark Results ===\n")
    results_output.append(f"Total benchmark time: {total_time:.2f} seconds")
    results_output.append(f"Average iteration time: {total_time/iterations:.6f} seconds")
    results_output.append(f"Iterations: {iterations}")
    
    results_output.append("\n--- Average Process Times ---\n")
    
    # First print the main phases in order
    main_phases = [
        "Phase I: ISDP Creation",
        "Phase II: Key Establishment",
        "Phase III: Profile Download & Installation",
        "Complete Protocol (Iteration"  # Partial match for all iterations
    ]
    
    for phase in main_phases:
        matching_phases = [name for name in stats.keys() if phase in name]
        for name in matching_phases:
            results_output.append(f"{name}: {stats[name]['avg']:.6f} seconds")
    
    results_output.append("\n--- Detailed Operation Times ---\n")
    
    # Print other operations, sorted by average time (descending)
    other_ops = sorted(
        [name for name in stats.keys() if not any(phase in name for phase in main_phases)],
        key=lambda x: stats[x]['avg'],
        reverse=True
    )
    
    for name in other_ops:
        results_output.append(f"{name}: {stats[name]['avg']:.6f} seconds")
    
    # Print the results to the console
    for line in results_output:
        print(line)
    
    # Save results to file if requested
    if output_file:
        try:
            with open(output_file, 'w') as f:
                f.write("\n".join(results_output))
            print(f"\nResults saved to {output_file}")
        except Exception as e:
            print(f"\nError saving results to file: {e}")
    
    return stats


if __name__ == "__main__":
    # Monkey patch the TimingContext in the imported modules
    import app
    import sys
    
    # First, modify the path to look in the current directory
    sys.path.insert(0, '.')
    
    # Replace TimingContext with BenchmarkTimingContext
    app.TimingContext = BenchmarkTimingContext
    
    # Import the modules
    import key_establishment
    import isdp_creation
    import profile_download_installation
    
    # Replace TimingContext in the modules
    key_establishment.TimingContext = BenchmarkTimingContext
    isdp_creation.TimingContext = BenchmarkTimingContext
    profile_download_installation.TimingContext = BenchmarkTimingContext
    
    # Run a short benchmark and save results to a file
    run_benchmark(iterations=100, progress_interval=10, output_file="rsp_benchmark_results.txt") 
import time

# Dictionary to track all timings
all_timings = {}

class TimingContext:
    """Context manager for timing operations"""
    
    def __init__(self, name):
        self.name = name
        self.elapsed_time = 0  # Initialize the elapsed_time attribute
        # Add to global tracking dictionary
        if name not in all_timings:
            all_timings[name] = 0
        
    def __enter__(self):
        # Use perf_counter for more accurate timing measurements 
        self.start_time = time.perf_counter()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.elapsed_time = self.end_time - self.start_time  # Store in elapsed_time attribute
        
        # Update the global tracking dictionary
        all_timings[self.name] += self.elapsed_time
        
        # Print the current timing
        print(f"{self.name}: {self.elapsed_time:.6f} seconds")
    
    @staticmethod
    def get_all_timings():
        """Return a copy of all recorded timings"""
        return dict(all_timings)
    
    @staticmethod
    def reset_timings():
        """Reset the timing records"""
        all_timings.clear() 
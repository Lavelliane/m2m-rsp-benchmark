import time

class TimingContext:
    """Context manager for timing operations"""
    
    def __init__(self, name):
        self.name = name
        self.elapsed_time = 0  # Initialize the elapsed_time attribute
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.elapsed_time = self.end_time - self.start_time  # Store in elapsed_time attribute
        print(f"{self.name}: {self.elapsed_time:.6f} seconds") 
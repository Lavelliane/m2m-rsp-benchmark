import time

class TimingContext:
    """Context manager for timing operations"""
    
    def __init__(self, name):
        self.name = name
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        print(f"{self.name}: {self.duration:.6f} seconds") 
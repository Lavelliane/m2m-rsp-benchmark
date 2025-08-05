#!/bin/bash
"""
Script to run SM-DP load test and collect metrics.
This script will:
1. Start the SM-DP server
2. Run the k6 load test
3. Extract metrics to CSV format
4. Clean up processes
"""

set -e  # Exit on any error

# Configuration
SMDP_PORT=8081
SMSR_PORT=8080
K6_LOG_FILE="k6_output.log"
CSV_OUTPUT_FILE="smdp_load_test_metrics.csv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to kill process by port
kill_by_port() {
    local port=$1
    local pid=$(lsof -ti:$port)
    if [ ! -z "$pid" ]; then
        print_status "Killing process on port $port (PID: $pid)"
        kill -9 $pid 2>/dev/null || true
        sleep 2
    fi
}

# Function to wait for server to be ready
wait_for_server() {
    local url=$1
    local timeout=30
    local count=0
    
    print_status "Waiting for server to be ready at $url..."
    
    while [ $count -lt $timeout ]; do
        if curl -s -f "$url/status" >/dev/null 2>&1; then
            print_status "Server is ready!"
            return 0
        fi
        sleep 1
        count=$((count + 1))
        printf "."
    done
    
    print_error "Timeout waiting for server to be ready"
    return 1
}

# Function to check dependencies
check_dependencies() {
    print_header "Checking Dependencies"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "python3 is required but not installed"
        exit 1
    fi
    
    # Check k6
    if ! command -v k6 &> /dev/null; then
        print_error "k6 is required but not installed"
        print_status "Please install k6 from: https://k6.io/docs/getting-started/installation/"
        exit 1
    fi
    
    # Check curl
    if ! command -v curl &> /dev/null; then
        print_error "curl is required but not installed"
        exit 1
    fi
    
    # Check lsof
    if ! command -v lsof &> /dev/null; then
        print_warning "lsof is not available - port checking may not work properly"
    fi
    
    print_status "All dependencies are available"
}

# Function to install Python dependencies
install_python_deps() {
    print_header "Installing Python Dependencies"
    
    cd "$PROJECT_ROOT"
    
    # Check if requirements.txt exists, if not create minimal requirements
    if [ ! -f "requirements.txt" ]; then
        print_status "Creating requirements.txt..."
        cat > requirements.txt << EOF
klein>=21.2.0
cryptography>=3.4.8
psutil>=5.8.0
pandas>=1.3.0
twisted>=21.7.0
EOF
    fi
    
    # Install dependencies
    print_status "Installing Python packages..."
    pip3 install -r requirements.txt
    
    print_status "Python dependencies installed"
}

# Function to start SM-DP server
start_smdp_server() {
    print_header "Starting SM-DP Server"
    
    # Kill any existing process on the port
    if check_port $SMDP_PORT; then
        print_warning "Port $SMDP_PORT is already in use"
        kill_by_port $SMDP_PORT
    fi
    
    cd "$PROJECT_ROOT"
    
    # Start SM-DP server in background
    print_status "Starting SM-DP server on port $SMDP_PORT..."
    python3 mock/smdp-server.py $SMDP_PORT > smdp_server.log 2>&1 &
    SMDP_PID=$!
    
    # Wait for server to be ready
    if wait_for_server "http://localhost:$SMDP_PORT"; then
        print_status "SM-DP server started successfully (PID: $SMDP_PID)"
    else
        print_error "Failed to start SM-DP server"
        return 1
    fi
}

# Function to run k6 load test
run_load_test() {
    print_header "Running k6 Load Test"
    
    cd "$PROJECT_ROOT"
    
    # Remove old log file
    rm -f "$K6_LOG_FILE"
    
    print_status "Starting k6 load test..."
    print_status "Test will run for approximately 10 minutes with ramping load"
    print_status "Metrics will be collected and saved to $CSV_OUTPUT_FILE"
    
    # Set environment variable for SM-DP URL
    export SMDP_URL="http://localhost:$SMDP_PORT"
    
    # Run k6 test and capture output
    if k6 run load-test/smdp-load-test.js --console-output="$K6_LOG_FILE" 2>&1 | tee -a "$K6_LOG_FILE"; then
        print_status "Load test completed successfully"
    else
        print_error "Load test failed or was interrupted"
        return 1
    fi
}

# Function to extract metrics
extract_metrics() {
    print_header "Extracting Metrics to CSV"
    
    cd "$PROJECT_ROOT"
    
    if [ -f "$K6_LOG_FILE" ]; then
        print_status "Extracting metrics from $K6_LOG_FILE..."
        python3 scripts/extract_csv_metrics.py "$K6_LOG_FILE" -o "$CSV_OUTPUT_FILE"
        
        if [ -f "$CSV_OUTPUT_FILE" ]; then
            print_status "Metrics successfully extracted to $CSV_OUTPUT_FILE"
            
            # Show CSV file info
            local line_count=$(wc -l < "$CSV_OUTPUT_FILE")
            print_status "CSV file contains $((line_count - 1)) data rows (plus header)"
            
            # Show first few lines of CSV
            print_status "Preview of CSV data:"
            head -6 "$CSV_OUTPUT_FILE"
        else
            print_error "Failed to create CSV file"
            return 1
        fi
    else
        print_error "k6 log file not found: $K6_LOG_FILE"
        return 1
    fi
}

# Function to cleanup processes
cleanup() {
    print_header "Cleaning Up"
    
    # Kill SM-DP server
    if [ ! -z "$SMDP_PID" ] && kill -0 $SMDP_PID 2>/dev/null; then
        print_status "Stopping SM-DP server (PID: $SMDP_PID)..."
        kill $SMDP_PID 2>/dev/null || true
        sleep 2
        
        # Force kill if still running
        if kill -0 $SMDP_PID 2>/dev/null; then
            kill -9 $SMDP_PID 2>/dev/null || true
        fi
    fi
    
    # Also try to kill by port in case PID tracking failed
    kill_by_port $SMDP_PORT
    
    print_status "Cleanup completed"
}

# Function to show final summary
show_summary() {
    print_header "Load Test Summary"
    
    echo "Files generated:"
    [ -f "$K6_LOG_FILE" ] && echo "  - k6 log file: $K6_LOG_FILE"
    [ -f "$CSV_OUTPUT_FILE" ] && echo "  - CSV metrics: $CSV_OUTPUT_FILE"
    [ -f "smdp_server.log" ] && echo "  - SM-DP server log: smdp_server.log"
    
    if [ -f "$CSV_OUTPUT_FILE" ]; then
        echo ""
        echo "Next steps:"
        echo "  1. Analyze the CSV data in $CSV_OUTPUT_FILE"
        echo "  2. Import into Excel, Google Sheets, or analysis tools"
        echo "  3. Create visualizations of CPU and memory usage vs load"
        echo "  4. Check server logs for any errors or warnings"
    fi
    
    print_status "Load test completed successfully!"
}

# Trap to ensure cleanup on exit
trap cleanup EXIT

# Main execution
main() {
    print_header "M2M RSP SM-DP Load Test Runner"
    
    # Check command line arguments
    if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --deps-only    Only install dependencies"
        echo "  --no-deps      Skip dependency installation"
        echo ""
        echo "This script will:"
        echo "  1. Check and install dependencies"
        echo "  2. Start the SM-DP server"
        echo "  3. Run k6 load test"
        echo "  4. Extract metrics to CSV"
        echo "  5. Clean up processes"
        exit 0
    fi
    
    # Check dependencies
    check_dependencies
    
    # Install dependencies unless --no-deps is specified
    if [ "$1" != "--no-deps" ]; then
        install_python_deps
    fi
    
    # If only installing deps, exit here
    if [ "$1" = "--deps-only" ]; then
        print_status "Dependencies installed. Run without --deps-only to start the test."
        exit 0
    fi
    
    # Start the test sequence
    if start_smdp_server; then
        if run_load_test; then
            extract_metrics
            show_summary
        else
            print_error "Load test failed"
            exit 1
        fi
    else
        print_error "Failed to start SM-DP server"
        exit 1
    fi
}

# Run main function
main "$@" 
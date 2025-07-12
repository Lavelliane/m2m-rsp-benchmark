#!/bin/bash

# SM-DP Metrics Collection Test Script
# This script runs the k6 test and captures metrics in CSV format

# Configuration
SMDP_PORT=8081
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CSV_FILE="smdp_metrics_${TIMESTAMP}.csv"
LOG_FILE="smdp_test_${TIMESTAMP}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}SM-DP Performance Test with Metrics Collection${NC}"
echo "================================================="
echo "Timestamp: $(date)"
echo "CSV Output: $CSV_FILE"
echo "Log Output: $LOG_FILE"
echo ""

# Function to check if service is running
check_service() {
    local port=$1
    local name=$2
    
    if curl -s "http://localhost:$port/status" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name is running on port $port${NC}"
        return 0
    else
        echo -e "${RED}✗ $name is not running on port $port${NC}"
        return 1
    fi
}

# Function to start SM-DP server if not running
start_smdp_if_needed() {
    if ! check_service $SMDP_PORT "SM-DP Server"; then
        echo -e "${YELLOW}Starting SM-DP Server...${NC}"
        
        # Check if smdp-server.py exists
        if [ ! -f "smdp-server.py" ]; then
            echo -e "${RED}Error: smdp-server.py not found in current directory${NC}"
            echo "Please run this script from the mock directory"
            exit 1
        fi
        
        # Start SM-DP server in background
        python3 smdp-server.py $SMDP_PORT > smdp_server_${TIMESTAMP}.log 2>&1 &
        SMDP_PID=$!
        echo "SM-DP Server started with PID: $SMDP_PID"
        
        # Wait for server to start
        echo "Waiting for SM-DP Server to start..."
        sleep 3
        
        # Check if it's running
        if ! check_service $SMDP_PORT "SM-DP Server"; then
            echo -e "${RED}Failed to start SM-DP Server${NC}"
            exit 1
        fi
        
        # Set flag to stop server later
        STOP_SMDP=true
    else
        STOP_SMDP=false
    fi
}

# Function to cleanup
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    
    if [ "$STOP_SMDP" = true ] && [ ! -z "$SMDP_PID" ]; then
        echo "Stopping SM-DP Server (PID: $SMDP_PID)"
        kill $SMDP_PID 2>/dev/null
        wait $SMDP_PID 2>/dev/null
    fi
    
    echo "Cleanup complete"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo -e "${RED}Error: k6 is not installed${NC}"
    echo "Please install k6 from https://k6.io/docs/getting-started/installation/"
    exit 1
fi

# Check if the k6 script exists
if [ ! -f "k6-smdp-metrics.js" ]; then
    echo -e "${RED}Error: k6-smdp-metrics.js not found${NC}"
    echo "Please run this script from the mock directory"
    echo "Available k6 scripts:"
    ls -la k6-smdp-metrics*.js 2>/dev/null || echo "  No k6 scripts found"
    exit 1
fi

# Start SM-DP server if needed
start_smdp_if_needed

echo -e "${GREEN}Starting k6 load test...${NC}"
echo ""

# Create CSV header
echo "timestamp,vus,iterations,cpu_percent,mem_percent,memory_mb" > "$CSV_FILE"

# Run k6 test and capture output
k6 run k6-smdp-metrics.js 2>&1 | tee "$LOG_FILE" | while IFS= read -r line
do
    # Extract CSV data lines
    if [[ "$line" =~ ^.*CSV_METRICS,(.*)$ ]]; then
        echo "${BASH_REMATCH[1]}" >> "$CSV_FILE"
    fi
    
    # Show progress
    if [[ "$line" =~ ^.*CSV_HEADER,(.*)$ ]]; then
        echo -e "${GREEN}✓ Metrics collection started${NC}"
    fi
    
    # Show errors
    if [[ "$line" =~ ERROR ]]; then
        echo -e "${RED}$line${NC}"
    fi
done

echo ""
echo -e "${GREEN}Test completed!${NC}"
echo "================================================="

# Show CSV file info
if [ -f "$CSV_FILE" ]; then
    line_count=$(wc -l < "$CSV_FILE")
    if [ $line_count -gt 1 ]; then
        echo -e "${GREEN}✓ CSV file created: $CSV_FILE${NC}"
        echo -e "${GREEN}✓ Data points collected: $((line_count - 1))${NC}"
        echo ""
        echo "CSV Format:"
        echo "timestamp,vus,iterations,cpu_percent,mem_percent,memory_mb"
        echo ""
        echo "Sample data (first 5 lines):"
        head -n 6 "$CSV_FILE"
        echo ""
        echo "Use Excel, Google Sheets, or any CSV viewer to analyze the data."
    else
        echo -e "${YELLOW}⚠ CSV file created but no data points collected${NC}"
        echo "Check the log file for any errors: $LOG_FILE"
    fi
else
    echo -e "${RED}✗ CSV file not created${NC}"
fi

# Show summary
echo ""
echo "Files created:"
echo "- Metrics: $CSV_FILE"
echo "- Test log: $LOG_FILE"
if [ "$STOP_SMDP" = true ]; then
    echo "- SM-DP log: smdp_server_${TIMESTAMP}.log"
fi

echo ""
echo -e "${GREEN}Test completed successfully!${NC}" 
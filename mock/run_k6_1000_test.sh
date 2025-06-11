#!/bin/bash

# k6 Load Test Runner for 1000 VUs with CSV Metrics Extraction
# This script runs the enhanced k6 test and automatically extracts CSV data

echo "k6 Load Test - Ramping to 1000 VUs with CSV Metrics"
echo "====================================================="

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8080}"
OUTPUT_DIR="${OUTPUT_DIR:-.}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CSV_FILE="$OUTPUT_DIR/metrics_1000vu_$TIMESTAMP.csv"
LOG_FILE="$OUTPUT_DIR/k6_1000vu_output_$TIMESTAMP.log"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --url)
            BASE_URL="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --url URL               Base URL of the mock server (default: http://localhost:8080)"
            echo "  --output-dir DIR        Directory for output files (default: current)"
            echo "  --help, -h              Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  BASE_URL                Override the default server URL"
            echo "  OUTPUT_DIR              Override the default output directory"
            echo ""
            echo "Test Details:"
            echo "  - Ramps from 0 to 1000 VUs over 10 minutes (100 VUs per minute)"
            echo "  - Holds 1000 VUs for 2 minutes"
            echo "  - Ramps down to 0 VUs over 1 minute"
            echo "  - Total duration: ~13 minutes"
            echo "  - Records metrics every 10 seconds"
            echo ""
            echo "Output files:"
            echo "  metrics_1000vu_TIMESTAMP.csv   - CSV file with VUs, CPU%, Memory% data"
            echo "  k6_1000vu_output_TIMESTAMP.log - Full k6 output log"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo "Error: k6 is not installed"
    echo "Please install k6 from: https://k6.io/docs/getting-started/installation/"
    exit 1
fi

# Check if mock server is running
echo "Checking if mock server is running at $BASE_URL..."
if ! curl -s "$BASE_URL/status/smdp" > /dev/null 2>&1; then
    echo "Warning: Mock server doesn't seem to be running at $BASE_URL"
    echo "Please start the mock server first with: python mock/mock.py"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "Mock server is running ✓"
fi

echo ""
echo "Test Configuration:"
echo "  Target URL: $BASE_URL"
echo "  Max VUs: 1000"
echo "  Ramping Schedule:"
echo "    0→100→200→300→400→500→600→700→800→900→1000 VUs"
echo "    (1 minute per stage)"
echo "    Hold 1000 VUs for 2 minutes"
echo "    Ramp down to 0 over 1 minute"
echo "  Total Duration: ~13 minutes"
echo "  Metrics Interval: Every 10 seconds"
echo ""
echo "Output Files:"
echo "  CSV Metrics: $CSV_FILE"
echo "  Full Log: $LOG_FILE"
echo ""
echo "Starting k6 load test..."
echo "This is a long test (~13 minutes). Press Ctrl+C to stop if needed."
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K6_SCRIPT="$SCRIPT_DIR/k6-ramp-1000-csv.js"

# Export environment variables for k6
export BASE_URL

# Run k6 test and extract CSV data in real-time
echo "Running: k6 run $K6_SCRIPT"
echo ""

# Create CSV header
echo "timestamp,vus,cpu_percent,memory_percent,memory_mb" > "$CSV_FILE"

# Run k6 and extract CSV data
k6 run "$K6_SCRIPT" 2>&1 | tee "$LOG_FILE" | while IFS= read -r line; do
    # Print all lines to stdout
    echo "$line"
    
    # Extract CSV metrics lines
    if [[ "$line" =~ time=\"[^\"]*\"\ level=info\ msg=\"CSV_METRICS,([^\"]+)\" ]]; then
        # Extract CSV data from k6 log message
        csv_data="${BASH_REMATCH[1]}"
        echo "$csv_data" >> "$CSV_FILE"
    elif [[ "$line" =~ CSV_METRICS,(.+) ]]; then
        # Fallback: direct CSV line format
        csv_data="${BASH_REMATCH[1]}"
        echo "$csv_data" >> "$CSV_FILE"
    fi
done

echo ""
echo "Load test completed!"
echo ""

# Check if CSV file was created and has data
if [[ -f "$CSV_FILE" ]] && [[ $(wc -l < "$CSV_FILE") -gt 1 ]]; then
    echo "✓ CSV metrics saved to: $CSV_FILE"
    echo "  Lines: $(wc -l < "$CSV_FILE") (including header)"
    echo "  Size: $(du -h "$CSV_FILE" | cut -f1)"
    echo ""
    echo "Sample data (first 5 lines):"
    head -n 5 "$CSV_FILE"
    if [[ $(wc -l < "$CSV_FILE") -gt 5 ]]; then
        echo "..."
        echo "Last 2 lines:"
        tail -n 2 "$CSV_FILE"
    fi
    
    # Generate basic statistics
    echo ""
    echo "Quick Statistics:"
    if command -v python3 &> /dev/null; then
        python3 -c "
import csv
import sys

try:
    with open('$CSV_FILE', 'r') as f:
        reader = csv.DictReader(f)
        data = list(reader)
    
    if data:
        vus = [int(row['vus']) for row in data if row['vus'].isdigit()]
        cpus = [float(row['cpu_percent']) for row in data if row['cpu_percent'].replace('.','').isdigit()]
        mems = [float(row['memory_percent']) for row in data if row['memory_percent'].replace('.','').isdigit()]
        
        print(f'  Data points: {len(data)}')
        if vus:
            print(f'  VUs: min={min(vus)}, max={max(vus)}, avg={sum(vus)/len(vus):.1f}')
        if cpus:
            print(f'  CPU%: min={min(cpus):.1f}, max={max(cpus):.1f}, avg={sum(cpus)/len(cpus):.1f}')
        if mems:
            print(f'  Memory%: min={min(mems):.1f}, max={max(mems):.1f}, avg={sum(mems)/len(mems):.1f}')
except Exception as e:
    print(f'  Error calculating stats: {e}')
"
    fi
else
    echo "⚠ No CSV metrics were generated"
    echo "Possible reasons:"
    echo "  - Test was stopped early"
    echo "  - Mock server was not accessible"
    echo "  - Connection issues during the test"
    echo ""
    echo "Check the log file for details: $LOG_FILE"
fi

echo ""
echo "✓ Full k6 output saved to: $LOG_FILE"

echo ""
echo "Analysis suggestions:"
echo "  - Open CSV in Excel/LibreOffice for visualization"
echo "  - Python analysis:"
echo "    import pandas as pd"
echo "    df = pd.read_csv('$CSV_FILE')"
echo "    df.plot(x='vus', y=['cpu_percent', 'memory_percent'])"
echo "  - Create charts with gnuplot:"
echo "    gnuplot -e \"set datafile separator ','; set terminal png; set output 'chart.png'; plot '$CSV_FILE' using 2:3 with lines title 'CPU%', '$CSV_FILE' using 2:4 with lines title 'Memory%'\"" 
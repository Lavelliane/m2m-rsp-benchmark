#!/bin/bash

set -e

echo "🎯 M2M RSP Service Mesh Benchmark Runner"
echo "========================================"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Python 3 is installed
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 >/dev/null 2>&1; then
    echo "❌ pip3 is required but not installed"
    exit 1
fi

# Install requirements if needed
echo -e "${BLUE}📦 Installing Python dependencies...${NC}"
pip3 install aiohttp asyncio

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/benchmark_results"

# Create results directory
mkdir -p "$RESULTS_DIR"

echo -e "${GREEN}✅ Setup complete${NC}"
echo ""

# Show usage options
echo "Available benchmark modes:"
echo "1. Quick test (20 users, 5 step size) - ~5 minutes"
echo "2. Standard test (50 users, 10 step size) - ~15 minutes"
echo "3. Heavy test (100 users, 10 step size) - ~30 minutes"
echo "4. Custom configuration"
echo ""

read -p "Select mode (1-4): " choice

case $choice in
    1)
        echo -e "${YELLOW}🚀 Running Quick Benchmark...${NC}"
        python3 "$SCRIPT_DIR/benchmark_m2m_rsp.py" --quick --output-dir "$RESULTS_DIR"
        ;;
    2)
        echo -e "${YELLOW}🚀 Running Standard Benchmark...${NC}"
        python3 "$SCRIPT_DIR/benchmark_m2m_rsp.py" --max-users 50 --step-size 10 --output-dir "$RESULTS_DIR"
        ;;
    3)
        echo -e "${YELLOW}🚀 Running Heavy Benchmark...${NC}"
        python3 "$SCRIPT_DIR/benchmark_m2m_rsp.py" --max-users 100 --step-size 10 --output-dir "$RESULTS_DIR"
        ;;
    4)
        read -p "Max concurrent users: " max_users
        read -p "Step size: " step_size
        echo -e "${YELLOW}🚀 Running Custom Benchmark (${max_users} users, ${step_size} step)...${NC}"
        python3 "$SCRIPT_DIR/benchmark_m2m_rsp.py" --max-users "$max_users" --step-size "$step_size" --output-dir "$RESULTS_DIR"
        ;;
    *)
        echo "❌ Invalid selection"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}🎉 Benchmark completed!${NC}"
echo ""
echo "📊 Results saved in: $RESULTS_DIR"
echo "   • Detailed results: m2m_rsp_detailed_results.csv"
echo "   • Summary results: m2m_rsp_summary_results.csv"
echo ""
echo "📈 To analyze results:"
echo "   • Open CSV files in Excel/Google Sheets"
echo "   • Use pandas/matplotlib for advanced analysis"
echo "   • Import into Grafana for visualization"
echo ""

# List generated files
echo "Generated files:"
ls -la "$RESULTS_DIR"/*.csv 2>/dev/null || echo "No CSV files found" 
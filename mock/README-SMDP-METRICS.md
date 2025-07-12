# SM-DP Metrics Collection

This setup allows you to perform load testing on the SM-DP server while collecting CPU and memory metrics every 5 seconds, and export the data to CSV format.

## Files

- `k6-smdp-metrics.js` - Full RSP flow k6 script with metrics collection
- `k6-smdp-metrics-simple.js` - Simplified version without key establishment
- `run-smdp-metrics-test.sh` - Shell script to run the test and capture CSV output
- `analyze-smdp-metrics.py` - Python script to analyze the CSV data and create visualizations
- `generate_ec_key.py` - Utility script to generate valid EC keys for testing

## Quick Start

1. **Run the test** (will auto-start SM-DP server if needed):
   ```bash
   cd mock
   ./run-smdp-metrics-test.sh
   ```

2. **Analyze the results**:
   ```bash
   python3 analyze-smdp-metrics.py
   ```

## What Gets Tested

The k6 script performs the complete RSP flow:

1. **Profile Preparation** - Create a new profile at SM-DP
2. **Key Establishment** - ECDH key exchange between eUICC and SM-DP
3. **Profile Download** - Download the prepared profile package
4. **Download Confirmation** - Confirm successful download

## Metrics Collected

Every 5 seconds, the script collects:
- `cpu_percent` - CPU usage percentage
- `mem_percent` - Memory usage percentage  
- `memory_mb` - Memory usage in MB
- `vus` - Number of virtual users (from k6)
- `iterations` - Current iteration count (from k6)
- `timestamp` - ISO timestamp

## CSV Format

```csv
timestamp,vus,iterations,cpu_percent,mem_percent,memory_mb
2024-01-15T10:30:00.000Z,2,5,25.50,45.20,128.75
2024-01-15T10:30:05.000Z,5,12,32.10,47.80,135.20
...
```

## Load Test Configuration

The default configuration ramps up gradually:
- 10s: 0 → 2 VUs
- 20s: 2 → 5 VUs  
- 20s: 5 → 8 VUs
- 10s: 8 → 0 VUs

## Customization

To modify the test:

1. **Change VU ramp-up**: Edit `options.stages` in `k6-smdp-metrics.js`
2. **Change metrics interval**: Modify `METRICS_INTERVAL` (default: 5000ms)
3. **Change SM-DP port**: Modify `SMDP_BASE_URL` (default: localhost:8081)

## Troubleshooting

**"Invalid EC key" errors**: 
- The script uses a pre-generated valid SECP256R1 key
- If you get this error, run `python3 generate_ec_key.py` to generate a new key and update the script

**SM-DP not starting**:
- Check that `smdp-server.py` exists in the mock directory
- Ensure Python dependencies are installed: `pip install klein cryptography psutil`

**No metrics collected**:
- Check that the SM-DP server is running on port 8081
- Verify the `/system-metrics` endpoint is accessible: `curl http://localhost:8081/system-metrics`

## Dependencies

- **k6** - Load testing tool
- **Python 3** with packages: `pandas`, `matplotlib`, `cryptography`, `psutil`
- **SM-DP server** - The mock SM-DP server (`smdp-server.py`)

## Example Output

After running the test, you'll get:
- `smdp_metrics_TIMESTAMP.csv` - Raw metrics data
- `smdp_test_TIMESTAMP.log` - Test execution log
- `smdp_metrics_TIMESTAMP_analysis.png` - Visualization charts

The analysis will show:
- CPU and memory usage over time
- Correlation between VUs and resource usage
- Peak usage statistics
- Performance trends 
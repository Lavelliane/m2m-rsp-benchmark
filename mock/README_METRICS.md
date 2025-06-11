# RSP Metrics Collection

This guide explains how to collect CPU and memory usage data per process from eUICC registration to profile enabling in CSV format.

## Overview

The mock server now has enhanced metrics collection capabilities that track:
- **CPU usage percentage** per operation
- **Memory usage in MB** per operation  
- **Execution time in milliseconds** per operation
- **Timestamps** for chronological analysis

The complete RSP flow operations tracked are:
1. `register_euicc` - eUICC registration with SM-SR
2. `create_isdp` - ISD-P creation on eUICC
3. `key_establishment` - ECDH key establishment between entities
4. `prepare_profile` - Profile preparation at SM-DP
5. `install_profile` - Profile installation on eUICC
6. `enable_profile` - Profile activation

## Quick Start

### Method 1: Automated Collection (Recommended)

Use the automated collection script:

```bash
# Make sure you're in the mock directory
cd mock

# Run the automated metrics collection
python3 collect_metrics.py
```

This script will:
1. Start the mock server (if not running)
2. Clear any existing metrics
3. Run the k6 load test
4. Collect metrics and save to CSV
5. Display a summary report

### Method 2: Manual Collection

If you prefer manual control:

```bash
# Terminal 1: Start the mock server
python3 mock.py

# Terminal 2: Clear existing metrics and run test
curl -X POST http://localhost:8080/metrics/clear
k6 run k6-load-test.js

# Collect metrics to CSV
curl -X POST http://localhost:8080/metrics/save-csv \
  -H "Content-Type: application/json" \
  -d '{"filename": "my_rsp_metrics.csv"}'
```

## API Endpoints

### Metrics Collection Endpoints

| Endpoint | Method | Description |
|----------|---------|-------------|
| `/metrics` | GET | Get raw metrics data in JSON |
| `/metrics/export-csv` | GET | Download metrics as CSV file |
| `/metrics/save-csv` | POST | Save metrics to CSV file on server |
| `/metrics/rsp-flow` | GET | Get RSP flow analysis summary |
| `/metrics/clear` | POST | Clear all collected metrics |

### Using the Endpoints

**Save metrics to CSV file:**
```bash
curl -X POST http://localhost:8080/metrics/save-csv \
  -H "Content-Type: application/json" \
  -d '{"filename": "rsp_metrics_20240101.csv"}'
```

**Download CSV directly:**
```bash
curl http://localhost:8080/metrics/export-csv -o rsp_metrics.csv
```

**Get RSP flow summary:**
```bash
curl http://localhost:8080/metrics/rsp-flow | jq .
```

## CSV Format

The generated CSV file contains the following columns:

| Column | Description |
|--------|-------------|
| `operation` | RSP operation name (e.g., register_euicc, install_profile) |
| `timestamp` | Unix timestamp when the operation occurred |
| `datetime` | Human-readable datetime (YYYY-MM-DD HH:MM:SS.mmm) |
| `cpu_percent` | CPU usage percentage during the operation |
| `memory_mb` | Memory usage in megabytes during the operation |
| `execution_time_ms` | Operation execution time in milliseconds |

### Sample CSV Data

```csv
operation,timestamp,datetime,cpu_percent,memory_mb,execution_time_ms
register_euicc,1704067200.123,2024-01-01 12:00:00.123,15.5,2.3,45.2
create_isdp,1704067200.234,2024-01-01 12:00:00.234,8.2,1.8,23.1
key_establishment,1704067200.345,2024-01-01 12:00:00.345,12.1,3.1,67.8
prepare_profile,1704067200.456,2024-01-01 12:00:00.456,18.9,2.9,89.4
install_profile,1704067200.567,2024-01-01 12:00:00.567,22.3,4.2,156.7
enable_profile,1704067200.678,2024-01-01 12:00:00.678,7.4,1.5,34.5
```

## Data Analysis

### Using Python/Pandas

```python
import pandas as pd
import matplotlib.pyplot as plt

# Load the CSV data
df = pd.read_csv('rsp_metrics.csv')

# Convert timestamp to datetime
df['datetime'] = pd.to_datetime(df['datetime'])

# Group by operation
operation_stats = df.groupby('operation').agg({
    'cpu_percent': ['mean', 'min', 'max', 'std'],
    'memory_mb': ['mean', 'min', 'max', 'std'],
    'execution_time_ms': ['mean', 'min', 'max', 'std']
}).round(2)

print(operation_stats)

# Plot CPU usage over time
plt.figure(figsize=(12, 6))
for operation in df['operation'].unique():
    op_data = df[df['operation'] == operation]
    plt.plot(op_data['datetime'], op_data['cpu_percent'], 
             marker='o', label=operation)

plt.xlabel('Time')
plt.ylabel('CPU Usage (%)')
plt.title('CPU Usage by RSP Operation Over Time')
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```

### Using Excel/LibreOffice

1. Open the CSV file in Excel or LibreOffice Calc
2. Create pivot tables to analyze:
   - Average CPU/Memory usage per operation
   - Performance trends over time
   - Resource usage patterns
3. Generate charts to visualize:
   - CPU usage by operation type
   - Memory consumption patterns
   - Execution time distributions

## Load Testing Scenarios

The k6 load test includes several scenarios for different load patterns:

### Default Scenario (Ramping VUs)
- Starts with 5 virtual users
- Ramps up to 200 users over 2 minutes
- Each user executes the complete RSP flow

### Custom Scenarios

You can modify `k6-load-test.js` to test different scenarios:

```javascript
export const options = {
  scenarios: {
    // Constant load
    constant_load: {
      executor: 'constant-vus',
      vus: 50,
      duration: '5m',
    },
    
    // Spike testing
    spike_test: {
      executor: 'ramping-vus',
      stages: [
        { duration: '1m', target: 10 },
        { duration: '30s', target: 100 }, // Spike
        { duration: '1m', target: 10 },
      ],
    }
  }
};
```

## Troubleshooting

### Common Issues

**"k6 not found" error:**
```bash
# Install k6 (Ubuntu/Debian)
sudo apt update
sudo apt install -y k6

# Or using snap
sudo snap install k6

# Or download from https://k6.io/docs/getting-started/installation/
```

**"pandas not found" error:**
```bash
pip install pandas matplotlib  # For data analysis
```

**Server not starting:**
```bash
# Check if port 8080 is in use
netstat -tlnp | grep 8080

# Kill process using port 8080
sudo kill $(sudo lsof -t -i:8080)
```

**No metrics collected:**
- Ensure the load test runs successfully
- Check server logs for errors
- Verify endpoints are responding

### Performance Tuning

For better metrics accuracy:
1. Run tests on a dedicated system
2. Minimize background processes
3. Use longer test durations for more data points
4. Adjust k6 VU ramping for your system capacity

## Advanced Usage

### Custom Metrics Collection

You can extend the metrics collection by modifying the `@with_metrics` decorator in `mock.py`:

```python
@with_metrics("custom_operation")
def my_custom_operation(request):
    # Your operation logic here
    pass
```

### Real-time Monitoring

Monitor metrics in real-time during testing:

```bash
# Terminal 1: Start server with verbose output
python3 mock.py

# Terminal 2: Run test
k6 run k6-load-test.js

# Terminal 3: Monitor metrics
watch -n 2 'curl -s http://localhost:8080/metrics/rsp-flow | jq ".summary"'
```

This setup provides comprehensive insights into your RSP implementation's performance characteristics across the complete eUICC provisioning workflow. 
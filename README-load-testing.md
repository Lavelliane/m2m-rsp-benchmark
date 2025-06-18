# M2M RSP Load Testing

This directory contains tools for load testing M2M RSP (Remote SIM Provisioning) services across multiple zones using k6 and generating CSV data for analysis.

## Overview

The load testing setup includes:
- **`rsp-load-test.js`**: Comprehensive k6 script that tests RSP operations
- **`run-rsp-load-test.sh`**: Shell script to run different load test scenarios
- Support for testing across 3 zones (zone-a, zone-b, zone-c) deployed with microk8s

## Prerequisites

### 1. Install k6
```bash
# On Ubuntu/Debian
sudo apt update
sudo apt install k6

# Or download from https://k6.io/docs/getting-started/installation/
```

### 2. Deploy RSP Services
Make sure your M2M RSP services are deployed and running on microk8s:

```bash
# Apply the Kubernetes manifests
microk8s kubectl apply -f m2m-rsp-deployment/k8s/m2m-rsp-zone-a.yaml
microk8s kubectl apply -f m2m-rsp-deployment/k8s/m2m-rsp-zone-b.yaml
microk8s kubectl apply -f m2m-rsp-deployment/k8s/m2m-rsp-zone-c.yaml

# Check if pods are running
microk8s kubectl get pods -A | grep m2m-rsp

# Check if services are accessible
curl http://localhost:30080/status/smdp  # zone-a
curl http://localhost:30081/status/smdp  # zone-b
curl http://localhost:30082/status/smdp  # zone-c
```

### 3. Verify Network Access
The zones are accessible via NodePort services:
- **Zone A**: `localhost:30080` (us-east-1)
- **Zone B**: `localhost:30081` (us-west-2)  
- **Zone C**: `localhost:30082` (eu-central-1)

## Usage

### Quick Start

1. **Verify zones are accessible:**
```bash
./run-rsp-load-test.sh verify
```

2. **Run a moderate load test:**
```bash
./run-rsp-load-test.sh moderate
```

3. **Run all predefined tests:**
```bash
./run-rsp-load-test.sh all
```

### Available Test Configurations

| Test Name | Description | Load Pattern |
|-----------|-------------|--------------|
| `light` | Light load test | 2-5 virtual users |
| `moderate` | Moderate load test | 5-15 virtual users |
| `heavy` | Heavy load test | 10-30 virtual users |
| `spike` | Spike test | 2→20→2 virtual users |
| `stress` | Stress test | 10-40 virtual users |

### Command Reference

```bash
# Run specific test configurations
./run-rsp-load-test.sh light     # Light load
./run-rsp-load-test.sh moderate  # Moderate load
./run-rsp-load-test.sh heavy     # Heavy load
./run-rsp-load-test.sh spike     # Spike test
./run-rsp-load-test.sh stress    # Stress test

# Run all tests sequentially
./run-rsp-load-test.sh all

# Run custom test with specific load pattern
./run-rsp-load-test.sh custom my_test "--stage 60s:10,120s:20,60s:0"

# Just verify zone accessibility
./run-rsp-load-test.sh verify

# Generate consolidated report from existing results
./run-rsp-load-test.sh report [results_directory]
```

### RSP Operations Tested

The k6 script tests the following M2M RSP operations:

1. **eUICC Registration** (`/smsr/euicc/register`)
2. **ISD-P Creation** (`/smsr/isdp/create`) 
3. **Key Establishment** (`/smdp/key-establishment/init`, `/euicc/key-establishment/respond`)
4. **Profile Preparation** (`/smdp/profile/prepare`)
5. **Profile Installation** (`/smsr/profile/install/<euicc_id>`)
6. **Status Checks** (`/status/<entity_type>`)

### Test Scenarios

The script randomly selects test scenarios with different weights:
- **30%**: Complete RSP flow (all operations end-to-end)
- **20%**: Individual operations (register eUICC + create ISD-P)
- **20%**: Profile operations (prepare profile + key establishment)
- **20%**: Status checks across all entity types
- **10%**: Mixed operations

## Output Files

Each test run generates the following files in `rsp-load-test-results/`:

```
rsp-load-test-results/
├── moderate_20240101_120000/
│   ├── moderate_results.csv      # Detailed metrics in CSV format
│   ├── moderate_results.json     # k6 JSON output
│   ├── moderate_summary.txt      # Test execution summary
│   └── moderate_analysis.txt     # Basic statistical analysis
└── all_tests_20240101_130000/
    ├── test_summary.txt          # Summary of all tests
    ├── light_load/
    ├── moderate_load/
    ├── heavy_load/
    ├── spike_test/
    └── stress_test/
```

### CSV Data Structure

The generated CSV files contain the following columns:
- `timestamp`: When the metric was recorded
- `metric_name`: Type of metric (e.g., http_req_duration, errors, throughput)
- `metric_value`: The actual metric value
- `tags`: Additional metadata (operation, zone, region, etc.)

## Analysis and Visualization

### Basic Analysis
Each test automatically generates a basic analysis file with:
- Request counts by zone and operation
- Response time statistics (min, avg, max)
- Error rates and counts

### Advanced Analysis
You can import the CSV data into tools like:
- **Excel/Google Sheets**: For charts and pivot tables
- **Python/pandas**: For advanced statistical analysis
- **Grafana**: For real-time dashboards
- **R**: For statistical modeling

### Sample Analysis Queries

**Average response time by zone:**
```bash
awk -F',' 'NR>1 && $1=="http_req_duration" {zone_sum[$14]+=$3; zone_count[$14]++} END {for (zone in zone_sum) printf "%s: %.2f ms\n", zone, zone_sum[zone]/zone_count[zone]}' results.csv
```

**Error rate by operation:**
```bash
awk -F',' 'NR>1 && $1=="http_req_failed" {if($3=="1") errors[$13]++; total[$13]++} END {for (op in total) printf "%s: %.2f%%\n", op, (errors[op]*100/total[op])}' results.csv
```

## Load Test Patterns

### Gradual Load Increase
```bash
# Custom test with gradual increase
./run-rsp-load-test.sh custom gradual_load "--stage 60s:5,120s:10,180s:15,120s:20,60s:0"
```

### Sustained Load
```bash
# Long-running sustained load test
./run-rsp-load-test.sh custom sustained "--stage 120s:10,600s:10,120s:0"
```

### Load Steps
```bash
# Step-wise load increase
./run-rsp-load-test.sh custom steps "--stage 60s:5,60s:5,60s:10,60s:10,60s:15,60s:15,60s:0"
```

## Troubleshooting

### Common Issues

1. **Zones not accessible:**
   ```bash
   # Check if microk8s is running
   microk8s status
   
   # Check if pods are running
   microk8s kubectl get pods -A
   
   # Check service status
   microk8s kubectl get svc -A
   ```

2. **k6 not found:**
   ```bash
   # Install k6
   wget https://github.com/grafana/k6/releases/download/v0.45.0/k6-v0.45.0-linux-amd64.tar.gz
   tar -xzf k6-v0.45.0-linux-amd64.tar.gz
   sudo mv k6-v0.45.0-linux-amd64/k6 /usr/local/bin/
   ```

3. **Permission denied:**
   ```bash
   chmod +x run-rsp-load-test.sh
   ```

4. **Port conflicts:**
   - Default NodePorts: 30080, 30081, 30082
   - Check if ports are already in use: `netstat -tlnp | grep 3008`

### Performance Considerations

- **System Resources**: Monitor CPU and memory usage during tests
- **Network**: Ensure adequate bandwidth for load testing
- **Target Services**: Consider the capacity of your RSP mock services
- **Test Duration**: Longer tests provide more stable metrics

## Metrics Reference

### Key Metrics Tracked

| Metric | Description | Unit |
|--------|-------------|------|
| `http_req_duration` | HTTP request response time | milliseconds |
| `http_req_failed` | Failed HTTP requests | boolean (0/1) |
| `http_reqs` | Total HTTP requests | count |
| `response_time` | Custom response time metric | milliseconds |
| `rsp_operation_duration` | RSP operation duration | milliseconds |
| `throughput` | Operations completed | count |
| `errors` | Error rate | rate (0-1) |

### Performance Thresholds

Default thresholds set in the k6 script:
- 95% of requests should complete in < 1000ms
- Error rate should be < 10%

You can modify these in `rsp-load-test.js`:
```javascript
export let options = {
    thresholds: {
        'http_req_duration': ['p(95)<1000'],
        'errors': ['rate<0.1'],
    },
};
```

## Next Steps

1. **Continuous Integration**: Integrate load tests into CI/CD pipeline
2. **Monitoring**: Set up real-time monitoring during load tests
3. **Scaling**: Test how the system behaves under different scaling scenarios
4. **Optimization**: Use results to identify and fix performance bottlenecks

For questions or issues, check the generated log files in the output directory. 
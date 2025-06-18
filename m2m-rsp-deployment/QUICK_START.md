# M2M RSP Service Mesh Benchmark Guide

## 🏗️ Architecture Overview

### Geographic Zones
- **Zone A (Seoul 🇰🇷)**: Local deployment with 2 replicas
  - Namespace: `m2m-rsp-zone-a`
  - Expected latency: <10ms (no simulation)
  - Resources: 256Mi/512Mi per pod
  - Version: v1

- **Zone B (Virginia 🇺🇸)**: Far deployment with 3 replicas  
  - Namespace: `m2m-rsp-zone-b`
  - Simulated latency: ~180ms via EnvoyFilter
  - Resources: 256Mi/512Mi per pod
  - Version: v2

- **Zone C (Ireland 🇮🇪)**: Far deployment with 2 replicas
  - Namespace: `m2m-rsp-zone-c` 
  - Simulated latency: ~280ms via EnvoyFilter
  - Resources: 256Mi/512Mi per pod
  - Version: v3

### Service Mesh Features
- **Istio Gateway**: External load balancer with geographic routing
- **VirtualService**: Traffic splitting (70% Seoul, 20% Virginia, 10% Ireland)
- **DestinationRules**: Circuit breakers, mTLS encryption, load balancing
- **EnvoyFilters**: Realistic latency injection for geographic simulation

## 🎯 Run Benchmarks

### Interactive Mode
```bash
cd m2m-rsp-deployment
./run_benchmark.sh
# Select from: Quick (5min), Standard (15min), Heavy (30min), or Custom
```

### Direct Python Execution
```bash
# Quick test (20 users max, 5-minute duration)
python3 benchmark_m2m_rsp.py --quick

# Standard benchmark
python3 benchmark_m2m_rsp.py --max-users 50 --step-size 10

# Heavy load test
python3 benchmark_m2m_rsp.py --max-users 100 --step-size 10

# Custom configuration
python3 benchmark_m2m_rsp.py --max-users 200 --step-size 25 --output-dir ./results
```

## 🔍 Test Endpoints & Access Methods

| Zone | Direct Access | Gateway Route | Expected Response |
|------|---------------|---------------|-------------------|
| Seoul | `localhost:30080` | 70% of gateway traffic | <10ms fast |
| Virginia | `localhost:30081` | 20% of gateway traffic | ~180ms delay |
| Ireland | `localhost:30082` | 10% of gateway traffic | ~280ms delay |
| Gateway | `localhost:30852` | Load balanced | Mixed latency |

### M2M RSP Workflow Endpoints
- **`/status/smdp`**: SM-DP status check (GET)
- **`/smdp/profile/prepare`**: Profile preparation (POST)
- **`/smdp/key-establishment/init`**: Key establishment init (POST)
- **`/smdp/key-establishment/complete`**: Key establishment complete (POST)
- **`/smsr/euicc/register`**: eUICC registration (POST)
- **`/smsr/isdp/create`**: ISD-P creation (POST)
- **`/smsr/profile/install/{euicc_id}`**: Profile installation (POST)
- **`/smsr/profile/enable/{euicc_id}`**: Profile enablement (POST)
- **`/metrics`**: Performance metrics (GET)
- **`/system-metrics`**: System metrics (GET)

## 📊 Output Files & Analysis

### Detailed Results CSV
**File**: `m2m_rsp_detailed_results.csv`
**Contains**: Per-request metrics for deep analysis
```
timestamp,zone,endpoint,workflow,concurrent_users,response_time_ms,status_code,success,error_message
2024-01-15T10:30:15.123,Seoul,/status/smdp,status_check,10,2.45,200,True,
2024-01-15T10:30:15.456,Virginia,/profiles,profile_list,10,182.67,200,True,
```

### Summary Results CSV  
**File**: `m2m_rsp_summary_results.csv`
**Contains**: Aggregated statistics by zone
```
zone,location,total_requests,success_rate_percent,avg_response_time_ms,median_response_time_ms,p95_response_time_ms,min_response_time_ms,max_response_time_ms,expected_latency
Seoul,South Korea (Local),1250,99.84,3.42,2.89,8.76,0.87,15.23,<10ms
Virginia,USA (Far),750,98.67,183.45,181.22,189.34,178.45,195.67,~180ms
```

## 🔧 Configuration Options

### Load Testing Parameters
- **max-users**: Maximum concurrent users (default: 50)
- **step-size**: Load increment steps (default: 10)
- **output-dir**: Results directory (default: current directory)
- **quick**: Fast test mode (20 users, 5 steps)

### Workflow Testing
The benchmark tests these M2M RSP workflows:
1. **Primary** (all load levels): status_check, prepare_profile, register_euicc, install_profile
2. **Secondary** (reduced load): key_establishment_init, create_isdp, enable_profile, metrics, system_metrics

## 📈 Performance Metrics

### Key Measurements
- **Response Time**: End-to-end request latency in milliseconds
- **Success Rate**: Percentage of successful requests (HTTP 2xx)
- **Throughput**: Requests per second under load
- **Geographic Performance**: Latency comparison across zones
- **Load Scaling**: Performance degradation under increasing concurrent users

### Expected Results
- **Seoul Zone**: Consistent low latency, high throughput
- **Virginia Zone**: +180ms baseline, stable under load  
- **Ireland Zone**: +280ms baseline, stable under load
- **Gateway**: Mixed performance based on routing weights 
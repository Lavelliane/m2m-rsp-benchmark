import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';
import exec from 'k6/execution';

// Configuration
const SMDP_BASE_URL = 'http://localhost:8081'; // SM-DP server port
const METRICS_INTERVAL = 5000; // 5 seconds in milliseconds

// Custom metrics
const errorRate = new Rate('error_rate');
const smdpSuccessRate = new Rate('smdp_success_rate');

// Create trends for each SM-DP operation
const prepareProfileTrend = new Trend('prepare_profile_duration');
const downloadProfileTrend = new Trend('download_profile_duration');
const statusCheckTrend = new Trend('status_check_duration');

// System resource metrics
const cpuUtilization = new Trend('cpu_utilization');
const memoryUsage = new Trend('memory_usage_mb');
const memoryPercent = new Trend('memory_percent');

// Start small for testing
export const options = {
  stages: [
    { duration: '10s', target: 2 },  // Ramp up to 2 VUs
    { duration: '20s', target: 5 },  // Ramp up to 5 VUs
    { duration: '20s', target: 8 },  // Ramp up to 8 VUs
    { duration: '10s', target: 0 },  // Ramp down
  ],
  thresholds: {
    'error_rate': ['rate<0.1'],
    'smdp_success_rate': ['rate>0.9'],
    'prepare_profile_duration': ['p(95)<1000'],
    'download_profile_duration': ['p(95)<1500'],
    'status_check_duration': ['p(95)<200'],
  },
};

// Global tracking for metrics collection
let lastMetricsTime = 0;
let metricsCollectionStarted = false;

// Function to collect and record system metrics
function collectSystemMetrics() {
  const currentTime = Date.now();
  
  // Only collect from VU 1 to avoid duplicates, every 5 seconds
  if (exec.vu.idInTest === 1 && (currentTime - lastMetricsTime) >= METRICS_INTERVAL) {
    try {
      const metricsResponse = http.get(`${SMDP_BASE_URL}/system-metrics`, {
        timeout: '2000ms',
        tags: { operation: 'system_monitoring' }
      });
      
      if (metricsResponse.status === 200) {
        const systemData = metricsResponse.json();
        const timestamp = new Date().toISOString();
        
        // Extract metrics with fallbacks
        const cpuPercent = systemData.cpu_percent || 0;
        const memoryPct = systemData.memory_percent || 0;
        const memoryMB = systemData.memory_mb || 0;
        const currentVUs = exec.scenario.iterationInInstance || exec.vu.idInTest || 0;
        const currentIteration = exec.scenario.iterationInTest || 0;
        
        // Record metrics in k6
        cpuUtilization.add(cpuPercent);
        memoryPercent.add(memoryPct);
        memoryUsage.add(memoryMB);
        
        // Output CSV data - this will be captured by the test runner
        console.log(`CSV_METRICS,${timestamp},${currentVUs},${currentIteration},${cpuPercent.toFixed(2)},${memoryPct.toFixed(2)},${memoryMB.toFixed(2)}`);
        
        lastMetricsTime = currentTime;
      } else {
        console.log(`Failed to collect system metrics: ${metricsResponse.status}`);
      }
    } catch (error) {
      console.log(`System metrics collection error: ${error.message}`);
    }
  }
}

// Helper function to generate valid ICCID
function generateICCID() {
  const baseNumber = "8901001" + randomString(10, '0123456789');
  // Simple checksum for demo purposes
  return baseNumber + "0";
}

export default function() {
  // Initialize metrics collection header (only once)
  if (!metricsCollectionStarted && exec.vu.idInTest === 1) {
    console.log("CSV_HEADER,timestamp,vus,iterations,cpu_percent,mem_percent,memory_mb");
    metricsCollectionStarted = true;
  }
  
  // Collect system metrics
  collectSystemMetrics();
  
  let success = true;
  let profileId = generateICCID();
  
  // Test 1: Prepare Profile at SM-DP
  const preparePayload = JSON.stringify({
    profileType: 'telecom',
    iccid: profileId,
    subscriberId: `sub_${randomString(8)}`,
    profileClassifier: 'operational',
    profileNickname: `TestProfile_${randomString(4)}`,
    serviceProviderName: 'Test Service Provider',
    imsi: `001${randomString(10, '0123456789')}`,
    ki: randomString(32, '0123456789ABCDEF'),
    opc: randomString(32, '0123456789ABCDEF'),
    apns: [{"name": "internet", "type": "default"}],
    plmns: [{"mcc": "001", "mnc": "01"}]
  });
  
  const prepareResponse = http.post(`${SMDP_BASE_URL}/gsma/rsp/smdp/profile/prepare`, preparePayload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { operation: 'prepare_profile' }
  });
  
  const prepareCheck = check(prepareResponse, {
    'Profile preparation successful': (r) => r.status === 200 && r.json('status') === 'success',
    'Profile ID returned': (r) => r.json('profileId') !== undefined
  });
  
  if (!prepareCheck) {
    console.error(`Profile preparation failed: ${prepareResponse.status} ${prepareResponse.body}`);
    success = false;
  }
  
  errorRate.add(!prepareCheck);
  prepareProfileTrend.add(prepareResponse.timings.duration);
  
  // Test 2: Download Profile (simpler test without key establishment)
  if (success) {
    const downloadResponse = http.get(`${SMDP_BASE_URL}/gsma/rsp/smdp/profile/download/${profileId}`, {
      headers: { 'Content-Type': 'application/json' },
      tags: { operation: 'download_profile' }
    });
    
    const downloadCheck = check(downloadResponse, {
      'Profile download successful': (r) => r.status === 200 && r.json('status') === 'success',
      'Profile package returned': (r) => r.json('profilePackage') !== undefined
    });
    
    if (downloadCheck) {
      // Confirm download
      const confirmPayload = JSON.stringify({
        iccid: profileId,
        result: 'success'
      });
      
      const confirmResponse = http.post(`${SMDP_BASE_URL}/gsma/rsp/smdp/profile/confirm-download`, confirmPayload, {
        headers: { 'Content-Type': 'application/json' },
        tags: { operation: 'confirm_download' }
      });
      
      const confirmCheck = check(confirmResponse, {
        'Download confirmation successful': (r) => r.status === 200 && r.json('status') === 'success'
      });
      
      if (!confirmCheck) {
        success = false;
      }
      
      errorRate.add(!confirmCheck);
    } else {
      success = false;
      errorRate.add(1);
    }
    
    downloadProfileTrend.add(downloadResponse.timings.duration);
  }
  
  // Test 3: Status Check (lightweight operation)
  const statusResponse = http.get(`${SMDP_BASE_URL}/status`, {
    tags: { operation: 'status_check' }
  });
  
  const statusCheck = check(statusResponse, {
    'Status check successful': (r) => r.status === 200 && r.json('status') === 'active'
  });
  
  if (!statusCheck) {
    success = false;
  }
  
  errorRate.add(!statusCheck);
  statusCheckTrend.add(statusResponse.timings.duration);
  
  // Record overall success rate
  smdpSuccessRate.add(success ? 1 : 0);
  
  // Add random pause between iterations to prevent exact synchronization
  sleep(Math.random() * 1 + 0.5); // Sleep between 0.5 and 1.5 seconds
}

// Export function to run at the end of the test
export function handleSummary(data) {
  return {
    'smdp_performance_summary.json': JSON.stringify(data, null, 2),
  };
} 
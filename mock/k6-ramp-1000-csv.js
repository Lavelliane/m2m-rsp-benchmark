import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';
import exec from 'k6/execution';

// Custom metrics
const errorRate = new Rate('error_rate');
const rspSuccessRate = new Rate('rsp_success_rate');
const failureRate = new Rate('failure_rate');

// Create trends for each operation to track performance metrics
const registerEuiccTrend = new Trend('register_euicc');
const keyEstablishmentTrend = new Trend('key_establishment');
const createIsdpTrend = new Trend('create_isdp');
const prepareProfileTrend = new Trend('prepare_profile');
const installProfileTrend = new Trend('install_profile');
const enableProfileTrend = new Trend('enable_profile');

// System resource metrics for CSV export
const cpuUtilization = new Trend('cpu_utilization');
const memoryUsagePercent = new Trend('memory_usage_percent');
const memoryUsageMB = new Trend('memory_usage_mb');
const activeVUsMetric = new Trend('active_vus');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

// Enhanced ramping configuration for 1000 VUs
export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'max', 'count'],
  tags: { bucket: '' },
  scenarios: {
    ramp_to_1000: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 100 },   // Ramp to 100 VUs over 1 minute
        { duration: '1m', target: 200 },   // Ramp to 200 VUs over 1 minute
        { duration: '1m', target: 300 },   // Ramp to 300 VUs over 1 minute
        { duration: '1m', target: 400 },   // Ramp to 400 VUs over 1 minute
        { duration: '1m', target: 500 },   // Ramp to 500 VUs over 1 minute
        { duration: '1m', target: 600 },   // Ramp to 600 VUs over 1 minute
        { duration: '1m', target: 700 },   // Ramp to 700 VUs over 1 minute
        { duration: '1m', target: 800 },   // Ramp to 800 VUs over 1 minute
        { duration: '1m', target: 900 },   // Ramp to 900 VUs over 1 minute
        { duration: '1m', target: 1000 },  // Ramp to 1000 VUs over 1 minute
        { duration: '2m', target: 1000 },  // Hold 1000 VUs for 2 minutes
        { duration: '2m', target: 2000 },  // Hold 1000 VUs for 2 minutes
        { duration: '1m', target: 0 },     // Ramp down to 0 over 1 minute
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'error_rate': ['rate<0.15'],           // Allow slightly higher error rate at high load
    'rsp_success_rate': ['rate>0.85'],     // RSP success rate should be greater than 85%
    'failure_rate{bucket:*}': ['rate<0.3'], // Failure rate per VU bucket should be <30%
    'http_req_duration{operation:register_euicc}': ['p(95)<1000'],
    'http_req_duration{operation:key_establishment}': ['p(95)<1500'],
    'http_req_duration{operation:prepare_profile}': ['p(95)<2000'],
    'http_req_duration{operation:install_profile}': ['p(95)<3000'],
  },
};

// CSV metrics tracking
let lastMetricsTime = 0;
const METRICS_INTERVAL = 10000; // 10 seconds in milliseconds

// Helper function to add tag with operation name to metrics
function tagWithOperation(params, operationName) {
  return Object.assign({}, params, {
    tags: { operation: operationName }
  });
}

// Enhanced system metrics collection with CSV recording every 10 seconds
function collectAndRecordSystemMetrics() {
  const currentTime = Date.now();
  
  // Only collect metrics every 10 seconds and only from VU 1 to avoid duplicates
  if (exec.vu.idInTest === 1 && (currentTime - lastMetricsTime) >= METRICS_INTERVAL) {
    try {
      const metricsResponse = http.get(`${BASE_URL}/system-metrics`, {
        timeout: '2000ms',
        tags: { operation: 'system_monitoring' }
      });
      
      if (metricsResponse.status === 200) {
        const systemData = metricsResponse.json();
        const timestamp = new Date().toISOString();
        
        // Extract metrics with fallbacks
        const cpuPercent = systemData.cpu_percent || systemData.system_cpu_percent || 0;
        const memoryPercent = systemData.memory_percent || systemData.system_memory_percent || 0;
        const memoryMB = systemData.memory_mb || systemData.process_memory_mb || 0;
        const currentVUs = exec.scenario.iterationInInstance || exec.vu.idInTest || 0;
        
        // Record metrics in k6
        cpuUtilization.add(cpuPercent);
        memoryUsagePercent.add(memoryPercent);
        memoryUsageMB.add(memoryMB);
        activeVUsMetric.add(currentVUs);
        
        // Output CSV data with clear prefix for extraction
        console.log(`CSV_METRICS,${timestamp},${currentVUs},${cpuPercent.toFixed(2)},${memoryPercent.toFixed(2)},${memoryMB.toFixed(2)}`);
        
        lastMetricsTime = currentTime;
      }
    } catch (error) {
      // Silently handle system monitoring errors
      console.log(`System metrics collection failed: ${error.message}`);
    }
  }
}

export function setup() {
  console.log('='.repeat(70));
  console.log('M2M RSP Load Test - Ramping to 1000 VUs with CSV Metrics');
  console.log('='.repeat(70));
  console.log(`Target Server: ${BASE_URL}`);
  console.log('Ramping Schedule:');
  console.log('  0 → 100 VUs (1m) → 200 VUs (1m) → 300 VUs (1m) → 400 VUs (1m) → 500 VUs (1m)');
  console.log('  → 600 VUs (1m) → 700 VUs (1m) → 800 VUs (1m) → 900 VUs (1m) → 1000 VUs (1m)');
  console.log('  → Hold 1000 VUs (2m) → Ramp down to 0 (1m)');
  console.log('Total Duration: ~13 minutes');
  console.log('='.repeat(70));
  console.log('CSV Data Format: timestamp,vus,cpu_percent,memory_percent,memory_mb');
  console.log('CSV data will be logged every 10 seconds with prefix "CSV_METRICS,"');
  console.log('='.repeat(70));
  
  // Verify server is running
  try {
    const statusResponse = http.get(`${BASE_URL}/status/smdp`, { timeout: '5s' });
    if (statusResponse.status !== 200) {
      throw new Error(`Server status check failed: ${statusResponse.status}`);
    }
    console.log('✓ Mock server is running and accessible');
  } catch (error) {
    console.error(`✗ Failed to connect to mock server: ${error.message}`);
    console.error('Please ensure the mock server is running with: python mock/mock.py');
    throw error;
  }
  
  return {};
}

export default function() {
  // Collect system metrics every 10 seconds (only from VU 1)
  collectAndRecordSystemMetrics();
  
  let euiccId = `EID_${randomString(8)}`;
  let profileId, sessionId, smsrId, psk, isdpAid;
  let success = true;
  
  // Step 1: Register eUICC with SM-SR
  group('Register eUICC with SM-SR', function() {
    const payload = JSON.stringify({
      euiccId: euiccId,
      euiccInfo1: {
        svn: "2.1.0",
        euiccCiPKId: "id12345",
        euiccCiPK: {
          key: "base64KeyData",
          algorithm: "EC/SECP256R1"
        },
        euiccCapabilities: {
          supportedAlgorithms: ["ECKA-ECDH", "AES-128", "HMAC-SHA-256"],
          secureDomainSupport: true,
          pskSupport: true
        },
        testEuicc: false
      },
      eid: "89" + euiccId
    });
    
    const params = tagWithOperation({ headers: { 'Content-Type': 'application/json' } }, 'register_euicc');
    const response = http.post(`${BASE_URL}/smsr/euicc/register`, payload, params);
    
    const checkResult = check(response, {
      'eUICC Registration successful': (r) => r.status === 200 && r.json('status') === 'success',
      'PSK returned': (r) => r.json('psk') !== undefined
    });
    
    if (checkResult) {
      smsrId = response.json('smsrId');
      psk = response.json('psk');
    } else {
      console.error(`VU${exec.vu.idInTest}: eUICC Registration failed: ${response.status} ${response.body}`);
      success = false;
    }
    
    errorRate.add(checkResult ? 0 : 1);
    registerEuiccTrend.add(response.timings.duration);
  });
  
  // Only continue if eUICC registration was successful
  if (!success) {
    rspSuccessRate.add(0);
    return;
  }
  
  // Step 2: Create ISD-P on eUICC
  group('Create ISD-P on eUICC', function() {
    const payload = JSON.stringify({
      euiccId: euiccId,
      memoryRequired: 256
    });
    
    const params = tagWithOperation({ headers: { 'Content-Type': 'application/json' } }, 'create_isdp');
    const response = http.post(`${BASE_URL}/smsr/isdp/create`, payload, params);
    
    const checkResult = check(response, {
      'ISD-P Creation successful': (r) => r.status === 200 && r.json('status') === 'success',
      'ISD-P AID returned': (r) => r.json('isdpAid') !== undefined
    });
    
    if (checkResult) {
      isdpAid = response.json('isdpAid');
    } else {
      console.error(`VU${exec.vu.idInTest}: ISD-P Creation failed: ${response.status} ${response.body}`);
      success = false;
    }
    
    errorRate.add(checkResult ? 0 : 1);
    createIsdpTrend.add(response.timings.duration);
  });
  
  if (!success) {
    rspSuccessRate.add(0);
    return;
  }
  
  // Step 3: Key establishment between eUICC and SM-DP
  group('Key Establishment', function() {
    // Initialize key establishment
    const params = tagWithOperation({ headers: { 'Content-Type': 'application/json' } }, 'key_establishment');
    let response = http.post(`${BASE_URL}/smdp/key-establishment/init`, '{}', params);
    
    const initCheckResult = check(response, {
      'Key establishment init successful': (r) => r.status === 200 && r.json('status') === 'success',
      'Session ID returned': (r) => r.json('session_id') !== undefined,
      'Public key returned': (r) => r.json('public_key') !== undefined
    });
    
    if (!initCheckResult) {
      console.error(`VU${exec.vu.idInTest}: Key establishment init failed: ${response.status} ${response.body}`);
      success = false;
      errorRate.add(1);
      return;
    }
    
    // Save session ID and respond to key establishment
    sessionId = response.json('session_id');
    const publicKey = response.json('public_key');
    const randomChallenge = response.json('random_challenge');
    
    // eUICC responds to key establishment
    const euiccResponsePayload = JSON.stringify({
      session_id: sessionId,
      public_key: publicKey,
      entity: 'sm-dp'
    });
    
    response = http.post(`${BASE_URL}/euicc/key-establishment/respond`, euiccResponsePayload, params);
    
    const euiccResponseCheck = check(response, {
      'eUICC key establishment response successful': (r) => r.status === 200 && r.json('status') === 'success',
      'eUICC public key returned': (r) => r.json('public_key') !== undefined
    });
    
    if (!euiccResponseCheck) {
      console.error(`VU${exec.vu.idInTest}: eUICC key establishment response failed: ${response.status} ${response.body}`);
      success = false;
      errorRate.add(1);
      return;
    }
    
    // Complete key establishment
    const completePayload = JSON.stringify({
      session_id: sessionId,
      public_key: response.json('public_key')
    });
    
    response = http.post(`${BASE_URL}/smdp/key-establishment/complete`, completePayload, params);
    
    const completeCheckResult = check(response, {
      'Key establishment completion successful': (r) => r.status === 200 && r.json('status') === 'success'
    });
    
    if (!completeCheckResult) {
      console.error(`VU${exec.vu.idInTest}: Key establishment completion failed: ${response.status} ${response.body}`);
      success = false;
    }
    
    errorRate.add(completeCheckResult ? 0 : 1);
    keyEstablishmentTrend.add(response.timings.duration);
  });
  
  if (!success) {
    rspSuccessRate.add(0);
    return;
  }
  
  // Step 4: Prepare profile at SM-DP
  group('Prepare Profile at SM-DP', function() {
    profileId = `ICCID_${randomString(8)}`;
    
    const payload = JSON.stringify({
      profileType: 'telecom',
      iccid: profileId,
      timestamp: Math.floor(Date.now() / 1000)
    });
    
    const params = tagWithOperation({ headers: { 'Content-Type': 'application/json' } }, 'prepare_profile');
    const response = http.post(`${BASE_URL}/smdp/profile/prepare`, payload, params);
    
    const checkResult = check(response, {
      'Profile preparation successful': (r) => r.status === 200 && r.json('status') === 'success',
      'Profile ID returned': (r) => r.json('profileId') !== undefined
    });
    
    if (!checkResult) {
      console.error(`VU${exec.vu.idInTest}: Profile preparation failed: ${response.status} ${response.body}`);
      success = false;
    }
    
    errorRate.add(checkResult ? 0 : 1);
    prepareProfileTrend.add(response.timings.duration);
  });
  
  if (!success) {
    rspSuccessRate.add(0);
    return;
  }
  
  // Step 5: Install profile on eUICC
  group('Install Profile on eUICC', function() {
    const payload = JSON.stringify({
      profileId: profileId
    });
    
    const params = tagWithOperation({ headers: { 'Content-Type': 'application/json' } }, 'install_profile');
    let response = http.post(`${BASE_URL}/smsr/profile/install/${euiccId}`, payload, params);
    
    const smsr_check = check(response, {
      'SM-SR profile installation preparation successful': (r) => r.status === 200 && r.json('status') === 'success',
      'Encrypted profile data returned': (r) => r.json('encryptedData') !== undefined
    });
    
    if (!smsr_check) {
      console.error(`VU${exec.vu.idInTest}: SM-SR profile installation failed: ${response.status} ${response.body}`);
      success = false;
      errorRate.add(1);
      return;
    }
    
    // Now send the encrypted data to eUICC
    const euiccPayload = JSON.stringify({
      encryptedData: response.json('encryptedData'),
      euiccId: euiccId
    });
    
    response = http.post(`${BASE_URL}/euicc/profile/install`, euiccPayload, params);
    
    const euicc_check = check(response, {
      'eUICC profile installation successful': (r) => r.status === 200 && r.json('status') === 'success'
    });
    
    if (!euicc_check) {
      console.error(`VU${exec.vu.idInTest}: eUICC profile installation failed: ${response.status} ${response.body}`);
      success = false;
    }
    
    errorRate.add(euicc_check ? 0 : 1);
    installProfileTrend.add(response.timings.duration);
  });
  
  if (!success) {
    rspSuccessRate.add(0);
    return;
  }
  
  // Step 6: Enable the installed profile
  group('Enable Profile', function() {
    const payload = JSON.stringify({
      profileId: profileId
    });
    
    const params = tagWithOperation({ headers: { 'Content-Type': 'application/json' } }, 'enable_profile');
    const response = http.post(`${BASE_URL}/smsr/profile/enable/${euiccId}`, payload, params);
    
    const checkResult = check(response, {
      'Profile enabling successful': (r) => r.status === 200 && r.json('status') === 'success'
    });
    
    if (!checkResult) {
      console.error(`VU${exec.vu.idInTest}: Profile enabling failed: ${response.status} ${response.body}`);
      success = false;
    }
    
    errorRate.add(checkResult ? 0 : 1);
    enableProfileTrend.add(response.timings.duration);
  });
  
  // Record overall success rate
  rspSuccessRate.add(success ? 1 : 0);
  
  // Use VU bucketing for failure rate analysis
  const bucketSize = 100; // group VUs in increments of 100 for high load testing
  const bucket = Math.ceil(exec.scenario.iterationInInstance / bucketSize) * bucketSize;
  failureRate.add(success ? 0 : 1, { bucket: String(bucket) });
  
  // Add random pause between iterations to prevent exact synchronization
  sleep(Math.random() * 2 + 0.5); // Sleep between 0.5 and 2.5 seconds
}

export function teardown(data) {
  console.log('='.repeat(70));
  console.log('Load Test Completed - 1000 VUs Test');
  console.log('='.repeat(70));
  console.log('To extract CSV data from the output, run:');
  console.log('k6 run mock/k6-ramp-1000-csv.js | grep "^CSV_METRICS," | sed "s/^CSV_METRICS,//" > metrics_1000vu.csv');
  console.log('');
  console.log('Or use the shell script for automatic extraction:');
  console.log('./mock/run_k6_1000_test.sh');
  console.log('='.repeat(70));
} 
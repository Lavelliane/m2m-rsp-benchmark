import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';
import { SharedArray } from 'k6/data';
import exec from 'k6/execution';

// Define custom metrics
const totalRSPCycles = new Counter('total_rsp_cycles');
const successfulRSPCycles = new Counter('successful_rsp_cycles');
const failedRSPCycles = new Counter('failed_rsp_cycles');
const processingTrend = new Trend('rsp_processing_time');

// System resource metrics
const cpuUtilization = new Trend('cpu_utilization');
const memoryUsage = new Trend('memory_usage_mb');

// Define BASE_URL (can be overridden via env variable)
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

// Add HTTP parameters for better connection handling
const params = {
  timeout: '60s',
  connecting_timeout: '30s',
};

export const options = {
  // Add these settings for better connection handling
  batch: 10,
  batchPerHost: 10,
  http: {
    timeout: '60s',
  },
  // Only export summary metrics, not all individual data points
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'max', 'count'],
  scenarios: {
    // Stress test with gradual ramp up, max 150 per stage, still reaching 1000
    stress_test: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 25,
      maxVUs: 1200,
      stages: [
        { duration: '2m', target: 10 },      // Start with 10 req/s
        { duration: '3m', target: 50 },      // Increase by 40
        { duration: '3m', target: 150 },     // Increase by 100
        { duration: '3m', target: 300 },     // Increase by 150
        { duration: '3m', target: 450 },     // Increase by 150
        { duration: '3m', target: 600 },     // Increase by 150
        { duration: '3m', target: 750 },     // Increase by 150
        { duration: '3m', target: 900 },     // Increase by 150
        { duration: '3m', target: 1000 },    // Increase by 100 to reach 1000
        { duration: '5m', target: 1000 },    // Maintain peak for 5 minutes
        { duration: '5m', target: 0 },       // Gradual ramp down
      ],
    },
  },
  thresholds: {
    'successful_rsp_cycles': ['count>100'],           // Should have at least 100 successful cycles
    'http_req_duration': ['p(95)<3000'],              // 95% of requests should be under 3 seconds
    'rsp_processing_time': ['p(95)<15000', 'p(99)<20000'] // 95% of full RSP cycles should complete under 15 seconds
  },
};

// Function to simulate collecting system metrics
// In a real environment, this would be replaced with actual metrics collection
function collectSystemMetrics() {
  // Simulate CPU utilization between 10-95%
  // In real usage, you would get this from the OS or monitoring tools
  const currentCpuUtilization = 10 + (85 * Math.pow(exec.scenario.progress, 1.5));
  cpuUtilization.add(currentCpuUtilization);
  
  // Simulate memory usage between 100-1000MB based on VU count
  // In real usage, you would get this from the OS or monitoring tools
  const baseMemory = 100; // MB
  const memPerVU = 2; // MB per VU
  const currentMemoryUsage = baseMemory + (memPerVU * exec.instance.vusActive);
  memoryUsage.add(currentMemoryUsage);
}

export default function() {
  // Collect system metrics periodically
  collectSystemMetrics();
  
  // Add default parameters to all requests
  const requestConfig = {
    timeout: '60s',
    headers: { 'Content-Type': 'application/json' },
  };
  
  // Add longer sleep between iterations
  sleep(Math.random() * 2 + 1); // Sleep between 1-3 seconds between iterations
  
  // Start timing the full RSP cycle
  const cycleStartTime = new Date();
  
  // Generate random IDs for this test
  const euiccId = `EID_${randomString(8)}`;
  const profileId = `ICCID_${randomString(10)}`;
  
  let success = true;
  totalRSPCycles.add(1);
  
  group('Complete RSP Cycle', function() {
    // Step 1: Register eUICC with SM-SR
    const euiccRegPayload = JSON.stringify({
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
    
    let res = http.post(`${BASE_URL}/smsr/euicc/register`, euiccRegPayload, requestConfig);
    
    if (!check(res, {
      'eUICC Registration successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at eUICC registration: ${res.status}, ${res.body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    const psk = res.json('psk');
    
    // Step 2: Run multiple operations in parallel for better throughput testing
    let requests = {};
    
    // Prepare profile at SM-DP
    requests['profile_prep'] = {
      method: 'POST',
      url: `${BASE_URL}/smdp/profile/prepare`,
      body: JSON.stringify({
        profileType: 'telecom',
        iccid: profileId,
        timestamp: Math.floor(Date.now() / 1000)
      }),
      params: {
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'PrepareProfile' }
      }
    };
    
    // Create ISD-P on eUICC
    requests['isdp_create'] = {
      method: 'POST',
      url: `${BASE_URL}/smsr/isdp/create`,
      body: JSON.stringify({
        euiccId: euiccId,
        memoryRequired: 256
      }),
      params: {
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'CreateIsdp' }
      }
    };
    
    // Initialize key establishment
    requests['key_est_init'] = {
      method: 'POST',
      url: `${BASE_URL}/smdp/key-establishment/init`,
      body: '{}',
      params: {
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'KeyEstInit' }
      }
    };
    
    // Run the parallel requests
    const responses = http.batch(requests);
    
    // Process profile preparation result
    if (!check(responses['profile_prep'], {
      'Profile preparation successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at profile preparation: ${responses['profile_prep'].status}, ${responses['profile_prep'].body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    // Process ISD-P creation result
    if (!check(responses['isdp_create'], {
      'ISD-P creation successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at ISD-P creation: ${responses['isdp_create'].status}, ${responses['isdp_create'].body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    const isdpAid = responses['isdp_create'].json('isdpAid');
    
    // Process key establishment initialization
    if (!check(responses['key_est_init'], {
      'Key establishment init successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at key establishment init: ${responses['key_est_init'].status}, ${responses['key_est_init'].body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    const sessionId = responses['key_est_init'].json('session_id');
    const publicKey = responses['key_est_init'].json('public_key');
    
    // Step 3: eUICC responds to key establishment
    const euiccResponsePayload = JSON.stringify({
      session_id: sessionId,
      public_key: publicKey, // Use the actual public key from the response
      entity: 'sm-dp'
    });
    
    res = http.post(`${BASE_URL}/euicc/key-establishment/respond`, euiccResponsePayload, requestConfig);
    
    if (!check(res, {
      'eUICC key response successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at eUICC key response: ${res.status}, ${res.body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    const euiccPublicKey = res.json('public_key');
    
    // Step 4: Complete key establishment
    const completePayload = JSON.stringify({
      session_id: sessionId,
      public_key: euiccPublicKey
    });
    
    res = http.post(`${BASE_URL}/smdp/key-establishment/complete`, completePayload, requestConfig);
    
    if (!check(res, {
      'Key establishment completion successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at key establishment completion: ${res.status}, ${res.body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    // Step 5: Install profile on eUICC
    const installPayload = JSON.stringify({
      profileId: profileId
    });
    
    res = http.post(`${BASE_URL}/smsr/profile/install/${euiccId}`, installPayload, requestConfig);
    
    if (!check(res, {
      'SM-SR profile installation successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at SM-SR profile installation: ${res.status}, ${res.body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    const encryptedData = res.json('encryptedData');
    
    // Step 6: Install profile on eUICC
    const euiccInstallPayload = JSON.stringify({
      encryptedData: encryptedData,
      euiccId: euiccId
    });
    
    res = http.post(`${BASE_URL}/euicc/profile/install`, euiccInstallPayload, requestConfig);
    
    if (!check(res, {
      'eUICC profile installation successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at eUICC profile installation: ${res.status}, ${res.body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    // Step 7: Enable profile
    const enablePayload = JSON.stringify({
      profileId: profileId
    });
    
    res = http.post(`${BASE_URL}/smsr/profile/enable/${euiccId}`, enablePayload, requestConfig);
    
    if (!check(res, {
      'Profile enabling successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at profile enabling: ${res.status}, ${res.body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    // Verify status
    res = http.get(`${BASE_URL}/status/euicc?id=${euiccId}`, requestConfig);
    
    check(res, {
      'Status check successful': (r) => r.status === 200 && r.json('status') === 'active'
    });
  });
  
  // If the whole cycle was successful, increment counter
  if (success) {
    successfulRSPCycles.add(1);
  }
  
  // Calculate and record the total processing time for the RSP cycle
  const cycleEndTime = new Date();
  const cycleProcessingTime = cycleEndTime - cycleStartTime;
  processingTrend.add(cycleProcessingTime);
}
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

// Track per-iteration failures; will be tagged with current active VUs
const failureRate = new Rate('failure_rate');

// Define BASE_URL (can be overridden via env variable)
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

export const options = {
  scenarios: {
    // Heavier stress test with more arrivals & higher VU ceiling
    stress_test: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '30s', target: 100 },
        { duration: '30s', target: 150 },
        { duration: '30s', target: 0 },
      ],
    },
  },
  thresholds: {
    'successful_rsp_cycles': ['count>100'],           // Should have at least 100 successful cycles
    'http_req_duration': ['p(95)<2000'],              // 95% of requests should be under 2 seconds
    'rsp_processing_time': ['p(95)<10000', 'p(99)<15000'], // 95% of full RSP cycles should complete under 10 seconds
    'failure_rate{bucket:*}': ['rate<0.2']               // failure rate per VU bucket should stay below 20%
  },
};

export default function() {
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
    
    let res = http.post(`${BASE_URL}/smsr/euicc/register`, euiccRegPayload, {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'RegisterEUICC' }
    });
    
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
    
    res = http.post(`${BASE_URL}/euicc/key-establishment/respond`, euiccResponsePayload, {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'EuiccKeyResponse' }
    });
    
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
    
    res = http.post(`${BASE_URL}/smdp/key-establishment/complete`, completePayload, {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'KeyEstComplete' }
    });
    
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
    
    res = http.post(`${BASE_URL}/smsr/profile/install/${euiccId}`, installPayload, {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'ProfileInstallSmSr' }
    });
    
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
    
    res = http.post(`${BASE_URL}/euicc/profile/install`, euiccInstallPayload, {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'ProfileInstallEuicc' }
    });
    
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
    
    res = http.post(`${BASE_URL}/smsr/profile/enable/${euiccId}`, enablePayload, {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'ProfileEnable' }
    });
    
    if (!check(res, {
      'Profile enabling successful': (r) => r.status === 200 && r.json('status') === 'success'
    })) {
      console.log(`Failed at profile enabling: ${res.status}, ${res.body}`);
      success = false;
      failedRSPCycles.add(1);
      return;
    }
    
    // Verify status
    res = http.get(`${BASE_URL}/status/euicc?id=${euiccId}`, {
      tags: { name: 'StatusCheck' }
    });
    
    check(res, {
      'Status check successful': (r) => r.status === 200 && r.json('status') === 'active'
    });
  });
  
  // Record success / failure metrics
  if (success) {
    successfulRSPCycles.add(1);
  }
  // Add to failure rate metric tagged by current active VUs (rounded to nearest 10)
  const vuBucket = Math.ceil(exec.vusActive / 10) * 10; // 1-10→10, 11-20→20, etc.
  failureRate.add(success ? 0 : 1, { bucket: vuBucket });
  
  // Calculate and record the total processing time for the RSP cycle
  const cycleEndTime = new Date();
  const cycleProcessingTime = cycleEndTime - cycleStartTime;
  processingTrend.add(cycleProcessingTime);
  
  // Add random sleep to prevent lockstep behavior
  sleep(Math.random() * 1 + 0.5);
}
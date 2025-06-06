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

// System resource metrics
const cpuUtilization = new Trend('cpu_utilization');
const memoryUsage = new Trend('memory_usage_mb');

// Configuration
const BASE_URL = 'http://localhost:8080'; // Change to match your server

export const options = {
  // Only export summary metrics, not all individual data points
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'max', 'count'],
  tags: { bucket: '' }, // declare custom tag so k6 indexes it
  scenarios: {
    ramp_up_down: {
      executor: 'ramping-vus',
      startVUs: 5,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '30s', target: 100 },
        { duration: '30s', target: 150 },
        { duration: '30s', target: 200 },
      ],
    },
  },
  thresholds: {
    'error_rate': ['rate<0.1'],            // Error rate should be less than 10%
    'rsp_success_rate': ['rate>0.9'],      // RSP success rate should be greater than 90%
    'failure_rate{bucket:*}': ['rate<0.2'], // Failure rate per VU bucket should be <20%
    'http_req_duration{operation:register_euicc}': ['p(95)<500'],     // 95% of registration requests should be below 500ms
    'http_req_duration{operation:key_establishment}': ['p(95)<800'],  // 95% of key establishment should be below 800ms
    'http_req_duration{operation:prepare_profile}': ['p(95)<1000'],   // 95% of profile preparation should be below 1000ms
    'http_req_duration{operation:install_profile}': ['p(95)<1500'],   // 95% of profile installation should be below 1500ms
  },
};

// Helper function to add tag with operation name to metrics
function tagWithOperation(params, operationName) {
  return Object.assign({}, params, {
    tags: { operation: operationName }
  });
}

// Legitimate system metrics collection function
function collectSystemMetrics() {
  // Only collect system metrics every 10th iteration to reduce load
  if (Math.random() < 0.1) {  // 10% chance per iteration
    try {
      const metricsResponse = http.get(`${BASE_URL}/system-metrics`, {
        timeout: '500ms',  // Shorter timeout
        tags: { operation: 'system_monitoring' }
      });
      
      if (metricsResponse.status === 200) {
        const systemData = metricsResponse.json();
        if (systemData.cpu_percent !== undefined) {
          cpuUtilization.add(systemData.cpu_percent);
        }
        if (systemData.memory_mb !== undefined) {
          memoryUsage.add(systemData.memory_mb);
        }
      }
    } catch (error) {
      // Silently handle timeouts - the real metrics are captured server-side
      // in the @with_metrics decorator, so client-side system metrics are optional
    }
  }
}

export default function() {
  // Collect system metrics each iteration
  collectSystemMetrics();
  
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
      console.error(`eUICC Registration failed: ${response.status} ${response.body}`);
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
      console.error(`ISD-P Creation failed: ${response.status} ${response.body}`);
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
      console.error(`Key establishment init failed: ${response.status} ${response.body}`);
      success = false;
      errorRate.add(1);
      return;
    }
    
    // Save session ID and respond to key establishment
    sessionId = response.json('session_id');
    const publicKey = response.json('public_key');
    const randomChallenge = response.json('random_challenge');
    
    // eUICC responds to key establishment
    // Note: Using a valid EC uncompressed point format (04 + x-coord + y-coord)
    // This is a valid EC point for SECP256R1 curve
    const euiccResponsePayload = JSON.stringify({
      session_id: sessionId,
      public_key: publicKey, // Using the public key from the SM-DP as a valid response
      entity: 'sm-dp'
    });
    
    response = http.post(`${BASE_URL}/euicc/key-establishment/respond`, euiccResponsePayload, params);
    
    const euiccResponseCheck = check(response, {
      'eUICC key establishment response successful': (r) => r.status === 200 && r.json('status') === 'success',
      'eUICC public key returned': (r) => r.json('public_key') !== undefined
    });
    
    if (!euiccResponseCheck) {
      console.error(`eUICC key establishment response failed: ${response.status} ${response.body}`);
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
      console.error(`Key establishment completion failed: ${response.status} ${response.body}`);
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
      console.error(`Profile preparation failed: ${response.status} ${response.body}`);
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
      console.error(`SM-SR profile installation failed: ${response.status} ${response.body}`);
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
      console.error(`eUICC profile installation failed: ${response.status} ${response.body}`);
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
      console.error(`Profile enabling failed: ${response.status} ${response.body}`);
      success = false;
    }
    
    errorRate.add(checkResult ? 0 : 1);
    enableProfileTrend.add(response.timings.duration);
  });
  
  // Record overall success rate
  rspSuccessRate.add(success ? 1 : 0);
  
  // Use a smaller bucket size to capture failure rate trends as load increases with reduced VUs
  const bucketSize = 50; // group active VUs in increments of 50
  const bucket = Math.ceil(exec.vusActive / bucketSize) * bucketSize;
  failureRate.add(success ? 0 : 1, { bucket: String(bucket) });
  
  // Add random pause between users to prevent exact synchronization
  sleep(Math.random() * 1 + 0.5); // Sleep between 0.5 and 1.5 seconds
}

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';

// Custom metrics
const profilePreparations = new Counter('profile_preparations');
const keyEstablishments = new Counter('key_establishments');
const profileDownloads = new Counter('profile_downloads');
const errorRate = new Rate('errors');
const responseTime = new Trend('response_time');

// SM-DP server configuration
const SMDP_BASE_URL = __ENV.SMDP_URL || 'http://localhost:8081';

// Load test scenarios - gradually increase load
export const options = {
  scenarios: {
    // Ramp-up scenario - gradually increase load
    ramp_up: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 5 },   // Ramp up to 5 VUs
        { duration: '1m', target: 10 },   // Stay at 10 VUs
        { duration: '30s', target: 20 },  // Ramp up to 20 VUs
        { duration: '1m', target: 20 },   // Stay at 20 VUs
        { duration: '30s', target: 50 },  // Ramp up to 50 VUs
        { duration: '2m', target: 50 },   // Stay at 50 VUs
        { duration: '30s', target: 100 }, // Ramp up to 100 VUs
        { duration: '2m', target: 100 },  // Stay at 100 VUs
        { duration: '1m', target: 0 },    // Ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.1'], // http errors should be less than 10%
    http_req_duration: ['p(95)<2000'], // 95% of requests should be below 2s
  },
};

// Test data for creating realistic profiles
const profileTypes = ['telecom', 'bootstrap', 'operational'];
const serviceProviders = ['TestSP1', 'TestSP2', 'TestSP3', 'GlobalSP', 'LocalSP'];

// Metrics collection
let metricsData = [];

// Function to collect system metrics from SM-DP server
function collectSystemMetrics(vus, iteration) {
  try {
    const response = http.get(`${SMDP_BASE_URL}/system-metrics`, {
      timeout: '5s',
    });
    
    if (response.status === 200) {
      const metrics = JSON.parse(response.body);
      const timestamp = new Date().toISOString();
      
      // Store metrics data for CSV export
      const metricsEntry = {
        vus: vus,
        iterations: iteration,
        cpu_percent: metrics.cpu_percent || 0,
        memory_percent: metrics.memory_percent || 0,
        time: timestamp
      };
      
      // Note: In k6, we can't directly write to files, but we can log for collection
      console.log(`METRICS_CSV,${vus},${iteration},${metrics.cpu_percent || 0},${metrics.memory_percent || 0},${timestamp}`);
      
      return metrics;
    }
  } catch (error) {
    console.log(`Error collecting metrics: ${error}`);
  }
  return null;
}

// Function to generate random ICCID
function generateICCID() {
  const base = '8901001' + Math.random().toString().substr(2, 10);
  // Simple Luhn check digit calculation
  let sum = 0;
  let alternate = false;
  for (let i = base.length - 1; i >= 0; i--) {
    let n = parseInt(base.charAt(i), 10);
    if (alternate) {
      n *= 2;
      if (n > 9) {
        n = (n % 10) + 1;
      }
    }
    sum += n;
    alternate = !alternate;
  }
  const checkDigit = (10 - (sum % 10)) % 10;
  return base + checkDigit;
}

// Function to generate random eUICC ID
function generateEuiccId() {
  return 'eUICC_' + Math.random().toString(36).substr(2, 16).toUpperCase();
}

// Main test function - simulates complete SM-DP workflow
export default function () {
  const vus = __VU;
  const iteration = __ITER;
  
  // Collect system metrics at the start of each iteration
  const startMetrics = collectSystemMetrics(vus, iteration);
  
  // Test data
  const profileType = profileTypes[Math.floor(Math.random() * profileTypes.length)];
  const serviceProvider = serviceProviders[Math.floor(Math.random() * serviceProviders.length)];
  const iccid = generateICCID();
  const euiccId = generateEuiccId();
  
  // 1. Test Profile Preparation
  const prepareProfilePayload = {
    profileType: profileType,
    iccid: iccid,
    serviceProviderName: serviceProvider,
    profileClassifier: 'operational',
    profileNickname: `TestProfile_${Math.random().toString(36).substr(2, 6)}`,
    apns: [
      { name: 'internet', type: 'default' },
      { name: 'ims', type: 'ims' }
    ],
    plmns: [
      { mcc: '001', mnc: '01' }
    ]
  };
  
  const startTime = Date.now();
  
  let prepareResponse = http.post(
    `${SMDP_BASE_URL}/gsma/rsp/smdp/profile/prepare`,
    JSON.stringify(prepareProfilePayload),
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: '10s',
    }
  );
  
  let success = check(prepareResponse, {
    'Profile preparation status is 200': (r) => r.status === 200,
    'Profile preparation response is valid': (r) => {
      try {
        const json = JSON.parse(r.body);
        return json.status === 'success' && json.profileId;
      } catch (e) {
        return false;
      }
    },
  });
  
  if (success) {
    profilePreparations.add(1);
  } else {
    errorRate.add(1);
    console.log(`Profile preparation failed: ${prepareResponse.status} - ${prepareResponse.body}`);
  }
  
  responseTime.add(Date.now() - startTime);
  
  sleep(Math.random() * 2 + 1); // Random sleep 1-3 seconds
  
  // 2. Test Key Establishment Initialization
  const keyEstStartTime = Date.now();
  
  const keyEstPayload = {
    euiccId: euiccId,
    protocolVersion: '1.3.0'
  };
  
  let keyEstResponse = http.post(
    `${SMDP_BASE_URL}/gsma/rsp/smdp/key-establishment/init`,
    JSON.stringify(keyEstPayload),
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: '10s',
    }
  );
  
  let sessionId = null;
  let serverPublicKey = null;
  let serverChallenge = null;
  
  success = check(keyEstResponse, {
    'Key establishment init status is 200': (r) => r.status === 200,
    'Key establishment init response is valid': (r) => {
      try {
        const json = JSON.parse(r.body);
        if (json.status === 'success' && json.sessionId) {
          sessionId = json.sessionId;
          serverPublicKey = json.serverPublicKey;
          serverChallenge = json.serverChallenge;
          return true;
        }
        return false;
      } catch (e) {
        return false;
      }
    },
  });
  
  if (success) {
    keyEstablishments.add(1);
  } else {
    errorRate.add(1);
    console.log(`Key establishment init failed: ${keyEstResponse.status} - ${keyEstResponse.body}`);
  }
  
  responseTime.add(Date.now() - keyEstStartTime);
  
  sleep(Math.random() * 1 + 0.5); // Random sleep 0.5-1.5 seconds
  
  // 3. Test Key Establishment Completion (if init was successful)
  if (sessionId && serverPublicKey) {
    const keyCompleteStartTime = Date.now();
    
    // Generate dummy eUICC public key (in real scenario, this would be from eUICC)
    // k6-compatible way to generate random base64 data
    function generateRandomBase64(length) {
      const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
      let result = '';
      for (let i = 0; i < Math.ceil(length * 4 / 3); i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
      }
      return result;
    }
    
    const euiccPublicKey = generateRandomBase64(65);
    const challengeResponse = generateRandomBase64(16);
    
    const keyCompletePayload = {
      sessionId: sessionId,
      euiccPublicKey: euiccPublicKey,
      challengeResponse: challengeResponse
    };
    
    let keyCompleteResponse = http.post(
      `${SMDP_BASE_URL}/gsma/rsp/smdp/key-establishment/complete`,
      JSON.stringify(keyCompletePayload),
      {
        headers: { 'Content-Type': 'application/json' },
        timeout: '10s',
      }
    );
    
    check(keyCompleteResponse, {
      'Key establishment complete status is 200': (r) => r.status === 200,
      'Key establishment complete response is valid': (r) => {
        try {
          const json = JSON.parse(r.body);
          return json.status === 'success';
        } catch (e) {
          return false;
        }
      },
    });
    
    responseTime.add(Date.now() - keyCompleteStartTime);
  }
  
  sleep(Math.random() * 1 + 0.5); // Random sleep 0.5-1.5 seconds
  
  // 4. Test Profile Download (if preparation was successful)
  if (prepareResponse.status === 200) {
    const downloadStartTime = Date.now();
    
    let downloadResponse = http.get(
      `${SMDP_BASE_URL}/gsma/rsp/smdp/profile/download/${iccid}`,
      {
        timeout: '15s',
      }
    );
    
    success = check(downloadResponse, {
      'Profile download status is 200': (r) => r.status === 200,
      'Profile download response is valid': (r) => {
        try {
          const json = JSON.parse(r.body);
          return json.status === 'success' && json.profilePackage;
        } catch (e) {
          return false;
        }
      },
    });
    
    if (success) {
      profileDownloads.add(1);
    } else {
      errorRate.add(1);
    }
    
    responseTime.add(Date.now() - downloadStartTime);
    
    sleep(Math.random() * 1 + 0.5); // Random sleep 0.5-1.5 seconds
    
    // 5. Test Download Confirmation
    const confirmStartTime = Date.now();
    
    const confirmPayload = {
      iccid: iccid,
      result: Math.random() > 0.1 ? 'success' : 'failure' // 90% success rate
    };
    
    let confirmResponse = http.post(
      `${SMDP_BASE_URL}/gsma/rsp/smdp/profile/confirm-download`,
      JSON.stringify(confirmPayload),
      {
        headers: { 'Content-Type': 'application/json' },
        timeout: '10s',
      }
    );
    
    check(confirmResponse, {
      'Download confirmation status is 200': (r) => r.status === 200,
      'Download confirmation response is valid': (r) => {
        try {
          const json = JSON.parse(r.body);
          return json.status === 'success';
        } catch (e) {
          return false;
        }
      },
    });
    
    responseTime.add(Date.now() - confirmStartTime);
  }
  
  // Collect metrics at the end of iteration
  const endMetrics = collectSystemMetrics(vus, iteration);
  
  // Add some variability to the test timing
  sleep(Math.random() * 2 + 1); // Random sleep 1-3 seconds
}

// Setup function - runs once at the start
export function setup() {
  console.log('Starting SM-DP Load Test');
  console.log(`Target SM-DP Server: ${SMDP_BASE_URL}`);
  
  // Test server connectivity
  const response = http.get(`${SMDP_BASE_URL}/status`);
  if (response.status !== 200) {
    throw new Error(`SM-DP server not responding: ${response.status}`);
  }
  
  console.log('METRICS_CSV_HEADER,vus,iterations,cpu_percent,memory_percent,time');
  console.log('SM-DP server is responsive, starting load test...');
  
  return { serverUrl: SMDP_BASE_URL };
}

// Teardown function - runs once at the end
export function teardown(data) {
  console.log('Load test completed');
  console.log(`Tested server: ${data.serverUrl}`);
  
  // Final status check
  const response = http.get(`${data.serverUrl}/status`);
  if (response.status === 200) {
    console.log('SM-DP server still responsive after load test');
    try {
      const status = JSON.parse(response.body);
      console.log(`Final server status: ${JSON.stringify(status, null, 2)}`);
    } catch (e) {
      console.log('Could not parse final status response');
    }
  } else {
    console.log(`Warning: SM-DP server not responding after test: ${response.status}`);
  }
} 
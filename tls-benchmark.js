import http from 'k6/http';
import { sleep, check, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';


// Define custom metrics for bottleneck detection
const bottleneckThreshold = 5.0; // seconds
const bottleneckCounter = new Counter('bottleneck_operations');
const operationTrend = new Trend('operation_response_time');
const operationFailRate = new Rate('operation_fail_rate');

// Global TLS settings for all requests
// This is the key fix - k6 requires this to be defined at the root level of options
export const options = {
  insecureSkipTLSVerify: true,
  scenarios: {
    // Infrastructure test
    infrastructure: {
      executor: 'constant-vus',
      vus: 5,
      duration: '30s',
      exec: 'infrastructureTest',
      tags: { scenario: 'infrastructure' },
    },
    // Performance test
    performance: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 5 },
        { duration: '1m', target: 10 },
        { duration: '30s', target: 15 },
        { duration: '1m', target: 5 },
        { duration: '30s', target: 0 },
      ],
      exec: 'performanceTest',
      tags: { scenario: 'performance' },
      startTime: '30s',
    },
    // Stress test to identify bottlenecks
    stress: {
      executor: 'constant-vus',
      vus: 10000,
      duration: '2m',
      exec: 'stressTest',
      tags: { scenario: 'stress' },
      startTime: '3m30s',
    },
  },
  thresholds: {
    'operation_response_time{operation:profile_preparation}': ['p(95)<10000'], // 10s
    'operation_response_time{operation:profile_enabling}': ['p(95)<10000'], // 10s
    'operation_response_time{operation:key_establishment}': ['p(95)<5000'], // 5s
    'operation_fail_rate': ['rate<0.1'], // Less than 10% failure rate
    'http_req_duration': ['p(95)<5000'], // 5s for all HTTP requests
  },
};


const USE_TLS = false;

// Endpoints Configuration
const API_CONFIG = {
  sm_dp: {
    base_url: USE_TLS ? 'https://localhost:9001' : 'http://localhost:8001',
    endpoints: {
      status: '/status',
      key_establishment_init: '/key-establishment/init',
      key_establishment_complete: '/key-establishment/complete',
      profile_prepare: '/profile/prepare'
    }
  },
  sm_sr: {
    base_url: USE_TLS ? 'https://localhost:9002' : 'http://localhost:8002',
    endpoints: {
      status: '/status',
      euicc_register: '/euicc/register',
      isdp_create: '/isdp/create',
      profile_install: '/profile/install',
      profile_enable: '/profile/enable'
    }
  },
  euicc: {
    base_url: USE_TLS ? 'https://localhost:9003' : 'http://localhost:8003',
    endpoints: {
      status: '/status'
    }
  }
};

// Infrastructure test - checks if services are up and running
export function infrastructureTest() {
  group('Service Status Checks', function() {
    // Check SM-DP status
    const smdpRes = http.get(`${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.status}`, 
      { tags: { name: 'sm_dp_status' } });
    
    const smdpCheck = check(smdpRes, {
      'SM-DP is up': (r) => r.status === 200,
      'SM-DP returns valid response': (r) => {
        try {
          return r.json('status') !== undefined;
        } catch (e) {
          console.error('Failed to parse SM-DP response as JSON:', e);
          return false;
        }
      }
    });
    operationFailRate.add(!smdpCheck);
    
    // Check SM-SR status
    const smsrRes = http.get(`${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.status}`, 
      { tags: { name: 'sm_sr_status' } });
    
    const smsrCheck = check(smsrRes, {
      'SM-SR is up': (r) => r.status === 200,
      'SM-SR returns valid response': (r) => {
        try {
          return r.json('status') !== undefined;
        } catch (e) {
          console.error('Failed to parse SM-SR response as JSON:', e);
          return false;
        }
      }
    });
    operationFailRate.add(!smsrCheck);
    
    // Check eUICC status
    const euiccRes = http.get(`${API_CONFIG.euicc.base_url}${API_CONFIG.euicc.endpoints.status}`, 
      { tags: { name: 'euicc_status' } });
    
    const euiccCheck = check(euiccRes, {
      'eUICC is up': (r) => r.status === 200,
      'eUICC returns valid response': (r) => {
        try {
          return r.json('status') !== undefined;
        } catch (e) {
          console.error('Failed to parse eUICC response as JSON:', e);
          return false;
        }
      }
    });
    operationFailRate.add(!euiccCheck);
  });
  
  sleep(1);
}

// Performance test - simulate realistic user flows
export function performanceTest() {
  const euiccId = `89${randomString(17, '0123456789')}`;
  const profileId = `${randomString(19, '0123456789')}`;
  let sessionId;
  
  group('eUICC Registration', function() {
    const payload = {
      euiccId: euiccId,
      euiccInfo1: {
        svn: "2.1.0",
        euiccCiPKId: `id${randomString(5, '0123456789')}`,
        euiccCiPK: {
          key: `MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA${randomString(40)}`,
          algorithm: "EC/SECP256R1"
        },
        euiccCapabilities: {
          supportedAlgorithms: ["ECKA-ECDH", "AES-128", "HMAC-SHA-256"],
          secureDomainSupport: true,
          pskSupport: true
        },
        testEuicc: false
      },
      smsrId: `SMSR-${randomString(8, '0123456789')}`,
      eid: `89${euiccId}`
    };
    
    const startTime = new Date();
    const res = http.post(`${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.euicc_register}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'euicc_registration' }
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    const success = check(res, {
      'eUICC registration successful': (r) => r.status === 200
    });
    
    operationTrend.add(duration, { operation: 'euicc_registration' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'euicc_registration' });
    }
    
    sleep(1);
  });
  
  group('ISD-P Creation', function() {
    const payload = {
      euiccId: euiccId,
      memoryRequired: 256
    };
    
    const startTime = new Date();
    const res = http.post(`${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.isdp_create}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'isdp_creation' }
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    const success = check(res, {
      'ISD-P creation successful': (r) => r.status === 200
    });
    
    operationTrend.add(duration, { operation: 'isdp_creation' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'isdp_creation' });
    }
    
    sleep(1);
  });
  
  group('Key Establishment', function() {
    const startTime = new Date();
    const initRes = http.post(`${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.key_establishment_init}`, 
      JSON.stringify({}), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'key_establishment_init' }
      }
    );
    
    const initSuccess = check(initRes, {
      'Key establishment init successful': (r) => r.status === 200
    });
    
    if (initSuccess && initRes.json('session_id')) {
      sessionId = initRes.json('session_id');
      
      const completePayload = {
        session_id: sessionId,
        public_key: `${randomString(64)}`
      };
      
      http.post(`${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.key_establishment_complete}`, 
        JSON.stringify(completePayload), 
        { 
          headers: { 'Content-Type': 'application/json' },
          tags: { name: 'key_establishment_complete' }
        }
      );
    }
    
    const duration = (new Date() - startTime) / 1000;
    operationTrend.add(duration, { operation: 'key_establishment' });
    operationFailRate.add(!initSuccess);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'key_establishment' });
    }
    
    sleep(1);
  });
  
  group('Profile Preparation', function() {
    const payload = {
      profileType: "telecom",
      iccid: profileId,
      timestamp: Math.floor(Date.now() / 1000)
    };
    
    const startTime = new Date();
    const res = http.post(`${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.profile_prepare}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_preparation' },
        timeout: 30000 // 30 second timeout for longer operations
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    const success = check(res, {
      'Profile preparation successful': (r) => r.status === 200
    });
    
    operationTrend.add(duration, { operation: 'profile_preparation' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_preparation' });
    }
    
    sleep(1);
  });
  
  group('Profile Installation', function() {
    const payload = {
      profileId: profileId
    };
    
    const startTime = new Date();
    const res = http.post(`${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.profile_install}/${euiccId}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_installation' },
        timeout: 20000
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    const success = check(res, {
      'Profile installation successful': (r) => r.status === 200
    });
    
    operationTrend.add(duration, { operation: 'profile_installation' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_installation' });
    }
    
    sleep(1);
  });
  
  group('Profile Enabling', function() {
    const payload = {
      profileId: profileId
    };
    
    const startTime = new Date();
    const res = http.post(`${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.profile_enable}/${euiccId}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_enabling' },
        timeout: 20000
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    const success = check(res, {
      'Profile enabling successful': (r) => r.status === 200
    });
    
    operationTrend.add(duration, { operation: 'profile_enabling' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_enabling' });
    }
    
    sleep(1);
  });
}

// Stress test - focused on bottleneck detection
export function stressTest() {
  const euiccId = `89${randomString(17, '0123456789')}`;
  const profileId = `${randomString(19, '0123456789')}`;
  
  // High volume testing of suspected bottleneck operations
  
  group('Profile Preparation Stress Test', function() {
    const payload = {
      profileType: "telecom",
      iccid: profileId,
      timestamp: Math.floor(Date.now() / 1000)
    };
    
    const startTime = new Date();
    const res = http.post(`${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.profile_prepare}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_preparation_stress' },
        timeout: 30000
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    operationTrend.add(duration, { operation: 'profile_preparation' });
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_preparation' });
    }
  });
  
  group('Key Establishment Stress Test', function() {
    const startTime = new Date();
    const res = http.post(`${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.key_establishment_init}`, 
      JSON.stringify({}), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'key_establishment_stress' }
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    operationTrend.add(duration, { operation: 'key_establishment' });
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'key_establishment' });
    }
  });
  
  group('Profile Enabling Stress Test', function() {
    const payload = {
      profileId: profileId
    };
    
    const startTime = new Date();
    const res = http.post(`${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.profile_enable}/${euiccId}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_enabling_stress' },
        timeout: 20000
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    operationTrend.add(duration, { operation: 'profile_enabling' });
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_enabling' });
    }
  });
  
  // Add randomized sleep for more realistic patterns
  sleep(Math.random() * 2);
}

// Generate summary report
export function handleSummary(data) {
  // Create detailed bottleneck analysis
  const bottlenecks = [];
  
  if (data.metrics.bottleneck_operations && data.metrics.bottleneck_operations.values) {
    Object.entries(data.metrics.bottleneck_operations.values).forEach(([name, count]) => {
      const operation = name.split(':')[1];
      bottlenecks.push({
        operation: operation,
        count: count,
        threshold: bottleneckThreshold
      });
    });
  }
  
  // Sort bottlenecks by count (descending)
  bottlenecks.sort((a, b) => b.count - a.count);
  
  // Build detailed metrics report
  const metricsReport = {};
  
  // Extract operation response times
  if (data.metrics.operation_response_time) {
    const operationMetrics = {};
    
    Object.entries(data.metrics.operation_response_time.values).forEach(([name, value]) => {
      const matches = name.match(/\{operation:([^}]+)\}/);
      if (matches) {
        const operation = matches[1];
        
        if (!operationMetrics[operation]) {
          operationMetrics[operation] = {};
        }
        
        if (name.includes('p(95)')) {
          operationMetrics[operation]['p95'] = value;
        } else if (name.includes('med')) {
          operationMetrics[operation]['median'] = value;
        } else if (name.includes('avg')) {
          operationMetrics[operation]['avg'] = value;
        } else if (name.includes('max')) {
          operationMetrics[operation]['max'] = value;
        }
      }
    });
    
    metricsReport.operations = operationMetrics;
  }
  
  // Create summary object
  const summary = {
    timestamp: new Date().toISOString(),
    testDuration: data.state.testRunDurationMs / 1000,
    metrics: {
      http_req_duration: {
        median: data.metrics.http_req_duration.values.med,
        p95: data.metrics.http_req_duration.values['p(95)'],
        max: data.metrics.http_req_duration.values.max
      },
      iterations: data.metrics.iterations.values.count,
      vus: data.metrics.vus.values.max,
      failRate: data.metrics.operation_fail_rate ? data.metrics.operation_fail_rate.values.rate : 0
    },
    bottlenecks: bottlenecks,
    detailedMetrics: metricsReport
  };
  
  return {
    'summary.json': JSON.stringify(summary, null, 2),
    'stdout': textSummary(data, summary, bottlenecks)
  };
}

// Helper function to format text summary
function textSummary(data, summary, bottlenecks) {
  const out = [];
  
  out.push('# TLS Load Test Summary\n');
  
  out.push('## HTTP Request Duration');
  out.push(`- Median: ${(summary.metrics.http_req_duration.median / 1000).toFixed(2)}s`);
  out.push(`- 95th percentile: ${(summary.metrics.http_req_duration.p95 / 1000).toFixed(2)}s`);
  out.push(`- Maximum: ${(summary.metrics.http_req_duration.max / 1000).toFixed(2)}s\n`);
  
  out.push('## Bottleneck Analysis');
  if (bottlenecks.length > 0) {
    bottlenecks.forEach(bottleneck => {
      out.push(`- ${bottleneck.operation}: ${bottleneck.count} occurrences over threshold (${bottleneck.threshold}s)`);
    });
  } else {
    out.push('- No bottlenecks detected (all operations completed within thresholds)');
  }
  
  out.push('\n## Test Configuration');
  out.push(`- VUs: ${summary.metrics.vus}`);
  out.push(`- Iterations: ${summary.metrics.iterations}`);
  out.push(`- Duration: ${(summary.testDuration / 60).toFixed(2)} minutes`);
  out.push(`- Failure Rate: ${(summary.metrics.failRate * 100).toFixed(2)}%`);
  
  return out.join('\n');
}

// Add a helper function for making HTTP requests with consistent error handling
function makeRequest(method, url, payload = null, options = {}) {
  let response;
  
  // Merge default options with provided options
  const requestOptions = {
    headers: { 'Content-Type': 'application/json' },
    timeout: 20000, // Default timeout
    tags: {},
    ...options
  };
  
  try {
    if (method.toLowerCase() === 'get') {
      response = http.get(url, requestOptions);
    } else if (method.toLowerCase() === 'post') {
      response = http.post(url, payload, requestOptions);
    } else {
      throw new Error(`Unsupported HTTP method: ${method}`);
    }
    
    // Check that the response is valid JSON
    try {
      if (response.body) {
        JSON.parse(response.body);
      }
    } catch (e) {
      console.error(`Invalid JSON response from ${url}: ${response.body}`);
    }
    
    return response;
  } catch (error) {
    console.error(`Request to ${url} failed: ${error.message}`);
    // Return a fake response with error info for consistent handling
    return {
      status: 0,
      body: JSON.stringify({ error: error.message }),
      error: error.message,
      json: (path) => null
    };
  }
} 
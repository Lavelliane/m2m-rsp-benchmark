import http from 'k6/http';
import { sleep, check, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Custom metrics
const bottleneckThreshold = 5.0; // seconds (matching the threshold in main.py)
const bottleneckCounter = new Counter('bottleneck_operations');
const operationTrend = new Trend('operation_response_time');
const operationFailRate = new Rate('operation_fail_rate');
const profilePreparationTime = new Trend('profile_preparation_time');
const keyEstablishmentTime = new Trend('key_establishment_time');
const profileEnablingTime = new Trend('profile_enabling_time');

// TLS settings - we're using self-signed certs so we need to disable verification
const tlsOptions = {
  insecureSkipTLSVerify: true
};

// Configuration
const USE_TLS = false;
const SM_DP_ENDPOINT = USE_TLS ? 'https://localhost:9001' : 'http://localhost:8001';
const SM_SR_ENDPOINT = USE_TLS ? 'https://localhost:9002' : 'http://localhost:8002';
const EUICC_ENDPOINT = USE_TLS ? 'https://localhost:9003' : 'http://localhost:8003';

// Test options
export const options = {
  discardResponseBodies: true,
  scenarios: {
    // Basic infrastructure test
    infrastructure: {
      executor: 'constant-vus',
      vus: 5,
      duration: '30s',
      exec: 'infrastructureTest',
      tags: { scenario: 'infrastructure' },
    },
    // Full eSIM provisioning cycle
    provisioning_cycle: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 5 },
        { duration: '1m', target: 10 },
        { duration: '30s', target: 5 },
        { duration: '30s', target: 0 },
      ],
      exec: 'provisioningCycle',
      tags: { scenario: 'provisioning' },
      startTime: '30s', // Start after infrastructure test
    },
    // Focused stress test on suspected bottlenecks
    bottleneck_test: {
      executor: 'constant-arrival-rate',
      rate: 5,
      timeUnit: '1s',
      duration: '1m',
      preAllocatedVUs: 20,
      exec: 'bottleneckTest',
      tags: { scenario: 'bottleneck' },
      startTime: '3m', // Start after provisioning cycle test
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

// Basic infrastructure test - check if all components are responsive
export function infrastructureTest() {
  group('Component Status Checks', function() {
    // Check SM-DP status
    let smdpRes = http.get(`${SM_DP_ENDPOINT}/status`, { tags: { name: 'sm_dp_status' }, ...tlsOptions });
    let smdpCheck = check(smdpRes, {
      'SM-DP is up': (r) => r.status === 200,
      'SM-DP returns valid JSON': (r) => {
        try {
          return r.body && r.json('status') === 'active';
        } catch (e) {
          console.log('SM-DP response error:', e.message);
          return false;
        }
      }
    });
    operationFailRate.add(!smdpCheck);
    
    // Check SM-SR status
    let smsrRes = http.get(`${SM_SR_ENDPOINT}/status`, { tags: { name: 'sm_sr_status' }, ...tlsOptions });
    let smsrCheck = check(smsrRes, {
      'SM-SR is up': (r) => r.status === 200,
      'SM-SR returns valid JSON': (r) => {
        try {
          return r.body && r.json('status') === 'active';
        } catch (e) {
          console.log('SM-SR response error:', e.message);
          return false;
        }
      }
    });
    operationFailRate.add(!smsrCheck);
    
    // Check eUICC status
    let euiccRes = http.get(`${EUICC_ENDPOINT}/status`, { tags: { name: 'euicc_status' }, ...tlsOptions });
    let euiccCheck = check(euiccRes, {
      'eUICC is up': (r) => r.status === 200,
      'eUICC returns valid JSON': (r) => {
        try {
          return r.body && r.json('status') === 'active';
        } catch (e) {
          console.log('eUICC response error:', e.message);
          return false;
        }
      }
    });
    operationFailRate.add(!euiccCheck);
  });
  
  sleep(1);
}

// Full provisioning cycle test
export function provisioningCycle() {
  const euiccId = `89${randomString(17, '0123456789')}`;
  const profileId = `${randomString(19, '0123456789')}`;
  let sessionId, isdpAid;
  
  group('eUICC Registration', function() {
    // Simulate eUICC registration with SM-SR
    const payload = {
      euiccId: euiccId,
      euiccInfo1: {
        svn: "2.1.0",
        euiccCiPKId: "id12345",
        euiccCiPK: {
          key: "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvKu3t1HFyx...",
          algorithm: "EC/SECP256R1"
        },
        euiccCapabilities: {
          supportedAlgorithms: ["ECKA-ECDH", "AES-128", "HMAC-SHA-256"],
          secureDomainSupport: true,
          pskSupport: true
        },
        testEuicc: false
      },
      smsrId: "SMSR-12345678",
      eid: `89${euiccId}`
    };
    
    const startTime = new Date();
    let res = http.post(`${SM_SR_ENDPOINT}/euicc/register`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'euicc_registration' },
        ...tlsOptions
      }
    );
    const duration = (new Date() - startTime) / 1000; // Convert to seconds
    
    let success = check(res, {
      'eUICC registration successful': (r) => r.status === 200 && r.json('status') === 'success',
      'PSK received': (r) => r.json('psk') !== undefined
    });
    
    operationTrend.add(duration, { operation: 'euicc_registration' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'euicc_registration' });
    }
    
    sleep(1);
  });
  
  group('ISD-P Creation', function() {
    // Create ISD-P on eUICC
    const payload = {
      euiccId: euiccId,
      memoryRequired: 256
    };
    
    const startTime = new Date();
    let res = http.post(`${SM_SR_ENDPOINT}/isdp/create`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'isdp_creation' },
        ...tlsOptions
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    let success = check(res, {
      'ISD-P creation successful': (r) => r.status === 200 && r.json('status') === 'success',
      'ISD-P AID received': (r) => r.json('isdpAid') !== undefined
    });
    
    if (success) {
      isdpAid = res.json('isdpAid');
    }
    
    operationTrend.add(duration, { operation: 'isdp_creation' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'isdp_creation' });
    }
    
    sleep(1);
  });
  
  group('Key Establishment', function() {
    // Initialize key establishment
    const startTime = new Date();
    let initRes = http.post(`${SM_DP_ENDPOINT}/key-establishment/init`, 
      JSON.stringify({}), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'key_establishment_init' },
        ...tlsOptions
      }
    );
    
    let initSuccess = check(initRes, {
      'Key establishment init successful': (r) => r.status === 200 && r.json('status') === 'success',
      'Session ID received': (r) => r.json('session_id') !== undefined,
      'Public key received': (r) => r.json('public_key') !== undefined
    });
    
    if (initSuccess) {
      sessionId = initRes.json('session_id');
      
      // Complete key establishment
      const completePayload = {
        session_id: sessionId,
        public_key: "BASE64_ENCODED_PUBLIC_KEY" // In a real test, this would be a valid key
      };
      
      let completeRes = http.post(`${SM_DP_ENDPOINT}/key-establishment/complete`, 
        JSON.stringify(completePayload), 
        { 
          headers: { 'Content-Type': 'application/json' },
          tags: { name: 'key_establishment_complete' },
          ...tlsOptions
        }
      );
      
      check(completeRes, {
        'Key establishment completion successful': (r) => r.status === 200 && r.json('status') === 'success'
      });
    }
    
    const duration = (new Date() - startTime) / 1000;
    keyEstablishmentTime.add(duration);
    operationTrend.add(duration, { operation: 'key_establishment' });
    operationFailRate.add(!initSuccess);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'key_establishment' });
    }
    
    sleep(1);
  });
  
  group('Profile Preparation', function() {
    // Prepare profile at SM-DP
    const payload = {
      profileType: "telecom",
      iccid: profileId,
      timestamp: Math.floor(Date.now() / 1000)
    };
    
    const startTime = new Date();
    let res = http.post(`${SM_DP_ENDPOINT}/profile/prepare`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_preparation' },
        timeout: 30000, // 30 second timeout since this is a long operation
        ...tlsOptions
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    const success = check(res, {
      'Profile preparation successful': (r) => r.status === 200 && r.json('status') === 'success'
    });
    
    profilePreparationTime.add(duration);
    operationTrend.add(duration, { operation: 'profile_preparation' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_preparation' });
    }
    
    sleep(1);
  });
  
  group('Profile Installation', function() {
    // Request profile installation from SM-SR to eUICC
    const payload = {
      profileId: profileId
    };
    
    const startTime = new Date();
    let res = http.post(`${SM_SR_ENDPOINT}/profile/install/${euiccId}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_installation' },
        timeout: 20000, // 20 second timeout
        ...tlsOptions
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    const success = check(res, {
      'Profile installation request successful': (r) => r.status === 200 && r.json('status') === 'success',
      'Encrypted data present': (r) => r.json('encryptedData') !== undefined
    });
    
    operationTrend.add(duration, { operation: 'profile_installation' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_installation' });
    }
    
    sleep(1);
  });
  
  group('Profile Enabling', function() {
    // Enable profile on eUICC
    const payload = {
      profileId: profileId
    };
    
    const startTime = new Date();
    let res = http.post(`${SM_SR_ENDPOINT}/profile/enable/${euiccId}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_enabling' },
        timeout: 20000, // 20 second timeout
        ...tlsOptions
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    const success = check(res, {
      'Profile enabling successful': (r) => r.status === 200 && r.json('status') === 'success'
    });
    
    profileEnablingTime.add(duration);
    operationTrend.add(duration, { operation: 'profile_enabling' });
    operationFailRate.add(!success);
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_enabling' });
    }
    
    sleep(1);
  });
  
  // Final status check
  group('Final Status Check', function() {
    let euiccRes = http.get(`${EUICC_ENDPOINT}/status`, { tags: { name: 'euicc_final_status' }, ...tlsOptions });
    check(euiccRes, {
      'eUICC has installed profiles': (r) => {
        try {
          return r.status === 200 && r.body && r.json('installedProfiles') > 0;
        } catch (e) {
          console.log('eUICC final status error:', e.message);
          return false;
        }
      }
    });
  });
}

// Focused test on suspected bottlenecks
export function bottleneckTest() {
  const euiccId = `89${randomString(17, '0123456789')}`;
  const profileId = `${randomString(19, '0123456789')}`;
  
  // Focus on profile preparation (known bottleneck)
  group('Profile Preparation Stress Test', function() {
    const payload = {
      profileType: "telecom",
      iccid: profileId,
      timestamp: Math.floor(Date.now() / 1000)
    };
    
    const startTime = new Date();
    let res = http.post(`${SM_DP_ENDPOINT}/profile/prepare`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_preparation_stress' },
        timeout: 30000,
        ...tlsOptions
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    profilePreparationTime.add(duration);
    operationTrend.add(duration, { operation: 'profile_preparation' });
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_preparation' });
    }
  });
  
  // Focus on profile enabling (another potential bottleneck)
  group('Profile Enabling Stress Test', function() {
    const payload = {
      profileId: profileId
    };
    
    const startTime = new Date();
    let res = http.post(`${SM_SR_ENDPOINT}/profile/enable/${euiccId}`, 
      JSON.stringify(payload), 
      { 
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'profile_enabling_stress' },
        timeout: 20000,
        ...tlsOptions
      }
    );
    const duration = (new Date() - startTime) / 1000;
    
    profileEnablingTime.add(duration);
    operationTrend.add(duration, { operation: 'profile_enabling' });
    
    if (duration > bottleneckThreshold) {
      bottleneckCounter.add(1, { operation: 'profile_enabling' });
    }
  });
  
  sleep(Math.random() * 3); // Variable sleep to create more realistic load patterns
}

export function handleSummary(data) {
  // Create a summary report
  const summary = {
    metrics: {
      http_req_duration: data.metrics.http_req_duration,
      bottleneck_operations: data.metrics.bottleneck_operations,
      operation_response_time: data.metrics.operation_response_time,
      operation_fail_rate: data.metrics.operation_fail_rate,
      profile_preparation_time: data.metrics.profile_preparation_time,
      key_establishment_time: data.metrics.key_establishment_time,
      profile_enabling_time: data.metrics.profile_enabling_time,
    },
    bottlenecks: {
      thresholdSeconds: bottleneckThreshold,
      identifiedBottlenecks: []
    }
  };
  
  // Add bottleneck analysis
  if (data.metrics.bottleneck_operations && data.metrics.bottleneck_operations.values) {
    Object.entries(data.metrics.bottleneck_operations.values).forEach(([name, count]) => {
      summary.bottlenecks.identifiedBottlenecks.push({
        operation: name.split(':')[1],
        count: count,
      });
    });
  }
  
  return {
    'summary.json': JSON.stringify(summary, null, 2),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}

// Helper function for text summary
function textSummary(data, options) {
  const { http_req_duration } = data.metrics;
  const out = [];
  
  out.push('# M2M RSP Load Test Summary\n');
  out.push('## HTTP Request Duration\n');
  out.push(`- Median: ${(http_req_duration.values.med / 1000).toFixed(2)}s`);
  out.push(`- 95th percentile: ${(http_req_duration.values['p(95)'] / 1000).toFixed(2)}s`);
  out.push(`- Maximum: ${(http_req_duration.values.max / 1000).toFixed(2)}s\n`);
  
  out.push('## Operation Response Times (seconds)\n');
  if (data.metrics.operation_response_time) {
    Object.entries(data.metrics.operation_response_time.values).forEach(([name, value]) => {
      if (name.includes('med') || name.includes('p(95)') || name.includes('max')) {
        const nameParts = name.split('{');
        const metricName = nameParts[0];
        const tagMatch = nameParts[1] ? nameParts[1].match(/operation:([^}]+)/) : null;
        const operation = tagMatch ? tagMatch[1] : 'unknown';
        const statName = name.includes('med') ? 'median' : name.includes('p(95)') ? '95th pct' : 'max';
        
        out.push(`- ${operation} ${statName}: ${value.toFixed(2)}s`);
      }
    });
  }
  
  out.push('\n## Identified Bottlenecks\n');
  if (data.metrics.bottleneck_operations && data.metrics.bottleneck_operations.values) {
    let foundBottlenecks = false;
    Object.entries(data.metrics.bottleneck_operations.values).forEach(([name, count]) => {
      const operation = name.split(':')[1];
      out.push(`- ${operation}: ${count} occurrences over threshold (${bottleneckThreshold}s)`);
      foundBottlenecks = true;
    });
    
    if (!foundBottlenecks) {
      out.push('- No operations consistently exceeding threshold');
    }
  } else {
    out.push('- No bottleneck data available');
  }
  
  return out.join('\n');
}
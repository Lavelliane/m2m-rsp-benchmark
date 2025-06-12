import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const responseTime = new Trend('response_time');
const requestCount = new Counter('requests');

// Performance test configuration
export const options = {
  scenarios: {
    rsp_flow_test: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 5 },   // Ramp up to 5 users
        { duration: '2m', target: 10 },   // Stay at 10 users
        { duration: '30s', target: 15 },  // Peak at 15 users
        { duration: '1m', target: 5 },    // Ramp down to 5
        { duration: '30s', target: 0 },   // Ramp down to 0
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% of requests should be below 2s
    http_req_failed: ['rate<0.1'],     // Error rate should be below 10%
  },
};

const BASE_URL = 'http://localhost:8080';

// Generate unique IDs for test isolation
function generateId() {
  return Math.random().toString(36).substring(2, 15);
}

// Test data generators
function generateEuiccId() {
  return `EUICC_${generateId()}`;
}

function generateProfileId() {
  return `PROF_${generateId()}`;
}

function generateSessionId() {
  return `SESSION_${generateId()}`;
}

// Test SM-DP endpoints
function testSMDP() {
  const tests = [];
  
  // Test profile preparation
  const profileData = {
    profileType: 'telecom',
    iccid: generateProfileId(),
    operator: 'TestOperator'
  };
  
  let response = http.post(`${BASE_URL}/smdp/profile/prepare`, JSON.stringify(profileData), {
    headers: { 'Content-Type': 'application/json' },
    tags: { entity: 'SM-DP', operation: 'prepare_profile' }
  });
  
  tests.push({
    entity: 'SM-DP',
    operation: 'prepare_profile',
    status: response.status,
    duration: response.timings.duration,
    success: check(response, {
      'SM-DP prepare profile status is 200': (r) => r.status === 200,
      'SM-DP prepare profile has success': (r) => {
        try {
          return JSON.parse(r.body).status === 'success';
        } catch (e) {
          return false;
        }
      }
    })
  });
  
  // Test key establishment initialization
  response = http.post(`${BASE_URL}/smdp/key-establishment/init`, JSON.stringify({}), {
    headers: { 'Content-Type': 'application/json' },
    tags: { entity: 'SM-DP', operation: 'key_establishment_init' }
  });
  
  let sessionId = null;
  let publicKey = null;
  let challenge = null;
  
  const keyInitSuccess = check(response, {
    'SM-DP key init status is 200': (r) => r.status === 200,
    'SM-DP key init has session': (r) => {
      try {
        const data = JSON.parse(r.body);
        sessionId = data.session_id;
        publicKey = data.public_key;
        challenge = data.random_challenge;
        return data.status === 'success' && sessionId;
      } catch (e) {
        return false;
      }
    }
  });
  
  tests.push({
    entity: 'SM-DP',
    operation: 'key_establishment_init',
    status: response.status,
    duration: response.timings.duration,
    success: keyInitSuccess
  });
  
  // Test key establishment completion if init was successful
  if (sessionId && publicKey) {
    const keyCompleteData = {
      session_id: sessionId,
      public_key: 'BG5vdGFyZWFsY3J5cHRvZ3JhcGhpY2tleWJ1dGZvcnRlc3Rpbmdwcm9wb3Nlcw=='
    };
    
    response = http.post(`${BASE_URL}/smdp/key-establishment/complete`, JSON.stringify(keyCompleteData), {
      headers: { 'Content-Type': 'application/json' },
      tags: { entity: 'SM-DP', operation: 'key_establishment_complete' }
    });
    
    tests.push({
      entity: 'SM-DP',
      operation: 'key_establishment_complete',
      status: response.status,
      duration: response.timings.duration,
      success: check(response, {
        'SM-DP key complete status is 200': (r) => r.status === 200,
        'SM-DP key complete success': (r) => {
          try {
            return JSON.parse(r.body).status === 'success';
          } catch (e) {
            return false;
          }
        }
      })
    });
  }
  
  return tests;
}

// Test SM-SR endpoints
function testSMSR() {
  const tests = [];
  const euiccId = generateEuiccId();
  
  // Test eUICC registration
  const registrationData = {
    euiccId: euiccId,
    euiccInfo: {
      euiccId: euiccId,
      manufacturerName: 'TestManufacturer',
      productionDate: '2024-01-01'
    }
  };
  
  let response = http.post(`${BASE_URL}/smsr/euicc/register`, JSON.stringify(registrationData), {
    headers: { 'Content-Type': 'application/json' },
    tags: { entity: 'SM-SR', operation: 'register_euicc' }
  });
  
  let psk = null;
  const registerSuccess = check(response, {
    'SM-SR register status is 200': (r) => r.status === 200,
    'SM-SR register has PSK': (r) => {
      try {
        const data = JSON.parse(r.body);
        psk = data.psk;
        return data.status === 'success' && psk;
      } catch (e) {
        return false;
      }
    }
  });
  
  tests.push({
    entity: 'SM-SR',
    operation: 'register_euicc',
    status: response.status,
    duration: response.timings.duration,
    success: registerSuccess
  });
  
  // Test ISD-P creation
  const isdpData = {
    euiccId: euiccId,
    memoryRequired: 256
  };
  
  response = http.post(`${BASE_URL}/smsr/isdp/create`, JSON.stringify(isdpData), {
    headers: { 'Content-Type': 'application/json' },
    tags: { entity: 'SM-SR', operation: 'create_isdp' }
  });
  
  tests.push({
    entity: 'SM-SR',
    operation: 'create_isdp',
    status: response.status,
    duration: response.timings.duration,
    success: check(response, {
      'SM-SR create ISD-P status is 200': (r) => r.status === 200,
      'SM-SR create ISD-P success': (r) => {
        try {
          return JSON.parse(r.body).status === 'success';
        } catch (e) {
          return false;
        }
      }
    })
  });
  
  // Test profile installation
  const profileId = generateProfileId();
  const installData = {
    profileId: profileId,
    installationOptions: {
      enableAfterInstall: false
    }
  };
  
  response = http.post(`${BASE_URL}/smsr/profile/install/${euiccId}`, JSON.stringify(installData), {
    headers: { 'Content-Type': 'application/json' },
    tags: { entity: 'SM-SR', operation: 'install_profile' }
  });
  
  tests.push({
    entity: 'SM-SR',
    operation: 'install_profile',
    status: response.status,
    duration: response.timings.duration,
    success: check(response, {
      'SM-SR install profile status is 200': (r) => r.status === 200,
      'SM-SR install profile success': (r) => {
        try {
          return JSON.parse(r.body).status === 'success';
        } catch (e) {
          return false;
        }
      }
    })
  });
  
  // Test profile enabling
  const enableData = {
    profileId: profileId
  };
  
  response = http.post(`${BASE_URL}/smsr/profile/enable/${euiccId}`, JSON.stringify(enableData), {
    headers: { 'Content-Type': 'application/json' },
    tags: { entity: 'SM-SR', operation: 'enable_profile' }
  });
  
  tests.push({
    entity: 'SM-SR',
    operation: 'enable_profile',
    status: response.status,
    duration: response.timings.duration,
    success: check(response, {
      'SM-SR enable profile status is 200': (r) => r.status === 200,
      'SM-SR enable profile success': (r) => {
        try {
          return JSON.parse(r.body).status === 'success';
        } catch (e) {
          return false;
        }
      }
    })
  });
  
  return { tests, euiccId, psk };
}

// Test eUICC endpoints
function testEUICC(euiccId, psk) {
  const tests = [];
  
  // Test profile installation on eUICC
  const installData = {
    euiccId: euiccId,
    encryptedData: {
      iv: 'dGVzdGl2MTIzNDU2Nzg=',
      data: 'dGVzdGVuY3J5cHRlZGRhdGE=',
      mac: 'dGVzdG1hYzEyMzQ1Njc4'
    }
  };
  
  let response = http.post(`${BASE_URL}/euicc/profile/install`, JSON.stringify(installData), {
    headers: { 'Content-Type': 'application/json' },
    tags: { entity: 'eUICC', operation: 'install_profile' }
  });
  
  tests.push({
    entity: 'eUICC',
    operation: 'install_profile',
    status: response.status,
    duration: response.timings.duration,
    success: check(response, {
      'eUICC install profile status is 200': (r) => r.status === 200,
    })
  });
  
  // Test key establishment response
  const sessionId = generateSessionId();
  const keyResponseData = {
    session_id: sessionId,
    entity: 'sm-dp',
    public_key: 'BG5vdGFyZWFsY3J5cHRvZ3JhcGhpY2tleWJ1dGZvcnRlc3Rpbmdwcm9wb3Nlcw==',
    random_challenge: 'dGVzdGNoYWxsZW5nZTE='
  };
  
  response = http.post(`${BASE_URL}/euicc/key-establishment/respond`, JSON.stringify(keyResponseData), {
    headers: { 'Content-Type': 'application/json' },
    tags: { entity: 'eUICC', operation: 'key_establishment_respond' }
  });
  
  tests.push({
    entity: 'eUICC',
    operation: 'key_establishment_respond',
    status: response.status,
    duration: response.timings.duration,
    success: check(response, {
      'eUICC key establishment status is 200': (r) => r.status === 200,
      'eUICC key establishment success': (r) => {
        try {
          return JSON.parse(r.body).status === 'success';
        } catch (e) {
          return false;
        }
      }
    })
  });
  
  return tests;
}

// Test status endpoints for all entities
function testStatusEndpoints() {
  const tests = [];
  const entities = ['smdp', 'smsr', 'euicc'];
  
  entities.forEach(entity => {
    const response = http.get(`${BASE_URL}/status/${entity}`, {
      tags: { entity: entity.toUpperCase(), operation: 'status_check' }
    });
    
    tests.push({
      entity: entity.toUpperCase(),
      operation: 'status_check',
      status: response.status,
      duration: response.timings.duration,
      success: check(response, {
        [`${entity} status is 200`]: (r) => r.status === 200,
        [`${entity} status is active`]: (r) => {
          try {
            return JSON.parse(r.body).status === 'active';
          } catch (e) {
            return false;
          }
        }
      })
    });
  });
  
  return tests;
}

// Collect system metrics
function collectSystemMetrics() {
  const response = http.get(`${BASE_URL}/system-metrics`, {
    tags: { entity: 'SYSTEM', operation: 'system_monitoring' }
  });
  
  let cpuPercent = 0;
  let memoryMb = 0;
  
  if (response.status === 200) {
    try {
      const data = JSON.parse(response.body);
      cpuPercent = data.cpu_percent || 0;
      memoryMb = data.memory_mb || 0;
    } catch (e) {
      // Use defaults
    }
  }
  
  return {
    entity: 'SYSTEM',
    operation: 'system_monitoring',
    status: response.status,
    duration: response.timings.duration,
    cpu_percent: cpuPercent,
    memory_mb: memoryMb,
    success: response.status === 200
  };
}

// Global array to store all test results
let allTestResults = [];

export default function () {
  const iterationResults = [];
  
  // Test all entities in sequence
  const smdpResults = testSMDP();
  iterationResults.push(...smdpResults);
  
  const smsrResults = testSMSR();
  iterationResults.push(...smsrResults.tests);
  
  const euiccResults = testEUICC(smsrResults.euiccId, smsrResults.psk);
  iterationResults.push(...euiccResults);
  
  const statusResults = testStatusEndpoints();
  iterationResults.push(...statusResults);
  
  const systemMetrics = collectSystemMetrics();
  iterationResults.push(systemMetrics);
  
  // Add iteration info and timestamp to each result
  const timestamp = new Date().toISOString();
  const iteration = __ITER;
  const vu = __VU;
  
  iterationResults.forEach(result => {
    result.timestamp = timestamp;
    result.iteration = iteration;
    result.vu = vu;
    result.cpu_percent = result.cpu_percent || 0;
    result.memory_mb = result.memory_mb || 0;
    
    // Update custom metrics
    errorRate.add(!result.success);
    responseTime.add(result.duration);
    requestCount.add(1);
  });
  
  // Store results globally
  allTestResults.push(...iterationResults);
  
  // Small delay between iterations
  sleep(1);
}

export function teardown() {
  // Export results to CSV
  console.log('\n=== PERFORMANCE TEST RESULTS ===');
  console.log(`Total requests: ${allTestResults.length}`);
  
  // Group by entity
  const entityStats = {};
  allTestResults.forEach(result => {
    if (!entityStats[result.entity]) {
      entityStats[result.entity] = {
        total: 0,
        success: 0,
        avgDuration: 0,
        totalDuration: 0
      };
    }
    
    entityStats[result.entity].total++;
    if (result.success) entityStats[result.entity].success++;
    entityStats[result.entity].totalDuration += result.duration;
  });
  
  // Calculate averages and print summary
  Object.keys(entityStats).forEach(entity => {
    const stats = entityStats[entity];
    stats.avgDuration = stats.totalDuration / stats.total;
    stats.successRate = (stats.success / stats.total * 100).toFixed(2);
    
    console.log(`${entity}: ${stats.total} requests, ${stats.successRate}% success, ${stats.avgDuration.toFixed(2)}ms avg`);
  });
  
  // Create CSV content
  const csvHeaders = [
    'timestamp',
    'entity', 
    'operation',
    'iteration',
    'vu',
    'status',
    'duration_ms',
    'success',
    'cpu_percent',
    'memory_mb'
  ];
  
  let csvContent = csvHeaders.join(',') + '\n';
  
  allTestResults.forEach(result => {
    const row = [
      result.timestamp,
      result.entity,
      result.operation,
      result.iteration,
      result.vu,
      result.status,
      result.duration.toFixed(2),
      result.success,
      result.cpu_percent,
      result.memory_mb
    ];
    csvContent += row.join(',') + '\n';
  });
  
  // Try to save results to server (this will also trigger server's CSV export)
  const saveResponse = http.post(`${BASE_URL}/metrics/save-csv`, JSON.stringify({
    filename: 'k6_rsp_performance_results.csv'
  }), {
    headers: { 'Content-Type': 'application/json' }
  });
  
  if (saveResponse.status === 200) {
    console.log('\n✅ Results saved to server CSV file');
  } else {
    console.log('\n❌ Failed to save to server, but results are available in console');
  }
  
  // Export server metrics as well  
  const exportResponse = http.get(`${BASE_URL}/metrics/export-csv`);
  if (exportResponse.status === 200) {
    console.log('✅ Server metrics exported successfully');
  }
  
  console.log('\n=== CSV DATA START ===');
  console.log(csvContent);
  console.log('=== CSV DATA END ===');
  
  console.log('\n📊 Performance test completed! Check server logs for detailed metrics.');
  console.log('💾 CSV data is available above and on the server.');
} 
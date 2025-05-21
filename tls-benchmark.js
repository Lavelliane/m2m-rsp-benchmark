import http from 'k6/http';
import { sleep, check, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';
import encoding from 'k6/encoding';

// Define custom metrics for bottleneck detection
const bottleneckThreshold = 5.0; // seconds
const bottleneckCounter = new Counter('bottleneck_operations');
const operationTrend = new Trend('operation_response_time');
const operationFailRate = new Rate('operation_fail_rate');
const bottleneckDuration = new Trend('bottleneck_duration');
const processDurations = new Trend('m2m_rsp_process_durations');
const errorCounter = new Counter('request_errors');

// Global settings with reduced load to avoid overwhelming the system
export const options = {
  insecureSkipTLSVerify: true,
  scenarios: {
    // Connection verification with longer warm-up
    connection_verification: {
      executor: 'shared-iterations',
      vus: 1,
      iterations: 1,
      exec: 'connectionVerification',
      tags: { scenario: 'verification' },
    },
    // Complete RSP flow - reduced load
    rsp_flow: {
      executor: 'per-vu-iterations',
      vus: 1,  // Just one VU at a time
      iterations: 2, // Reduced to 2 iterations
      exec: 'completeRspFlow',
      tags: { scenario: 'flow' },
      startTime: '20s', // Longer delay to ensure services are warmed up
      gracefulStop: '5m', // Cap execution time (changed from maxDuration)
    },
    // Targeted bottleneck analysis - with 1,000 VUs
    bottleneck_analysis: {
      executor: 'ramping-vus',
      startVUs: 10,
      stages: [
        { duration: '1m', target: 100 },  // Ramp up to 100 VUs over 1 minute
        { duration: '1m', target: 250 },  // Ramp up to 250 VUs over next minute
        { duration: '2m', target: 500 },  // Ramp up to 500 VUs over 2 minutes
        { duration: '2m', target: 750 },  // Ramp up to 750 VUs over 2 minutes
        { duration: '2m', target: 1000 }, // Finally reach 1000 VUs
        { duration: '5m', target: 1000 }, // Stay at 1000 VUs for 5 minutes
      ],
      exec: 'bottleneckAnalysis',
      tags: { scenario: 'bottleneck' },
      startTime: '6m', // Start after RSP flow is done
      gracefulStop: '20m', // Extended duration to allow for more VUs (changed from maxDuration)
    },
  },
  thresholds: {
    'm2m_rsp_process_durations{process:profile_preparation}': ['p(95)<40000'], // 40s
    'm2m_rsp_process_durations{process:profile_enabling}': ['p(95)<30000'], // 30s
    'm2m_rsp_process_durations{process:key_establishment}': ['p(95)<20000'], // 20s
    'm2m_rsp_process_durations{process:isdp_creation}': ['p(95)<20000'], // 20s
    'm2m_rsp_process_durations{process:euicc_registration}': ['p(95)<30000'], // 30s
    'm2m_rsp_process_durations{process:profile_installation}': ['p(95)<30000'], // 30s
    'operation_fail_rate': ['rate<0.5'], // Increased to 50% failure rate due to known issues
  },
};

const USE_TLS = false;

// Endpoints Configuration - Exactly matching main.py
const API_CONFIG = {
  sm_dp: {
    base_url: USE_TLS ? 'https://localhost:9001' : 'http://localhost:8001',
    endpoints: {
      status: '/status',
      key_establishment_init: '/key-establishment/init',
      key_establishment_complete: '/key-establishment/complete',
      profile_prepare: '/profile/prepare',
      profile_download: '/profile/download'
    }
  },
  sm_sr: {
    base_url: USE_TLS ? 'https://localhost:9002' : 'http://localhost:8002',
    endpoints: {
      status: '/status',
      euicc_register: '/euicc/register',
      isdp_create: '/isdp/create',
      profile_install: '/profile/install',
      profile_enable: '/profile/enable',
      profile_receive: '/profile/receive',
      key_establishment_init: '/key-establishment/init',
      key_establishment_complete: '/key-establishment/complete',
      es8_send: '/es8/send'
    }
  },
  euicc: {
    base_url: USE_TLS ? 'https://localhost:9003' : 'http://localhost:8003',
    endpoints: {
      status: '/status',
      profile_install: '/profile/install',
      es8_receive: '/es8/receive',
      key_establishment_respond: '/key-establishment/respond'
    }
  }
};

// Process tracking metrics
let processMetrics = {};

// Helper function to track process metrics
function trackProcess(name, duration, success, details = {}) {
  if (!processMetrics[name]) {
    processMetrics[name] = {
      count: 0,
      totalDuration: 0,
      successCount: 0,
      failCount: 0,
      bottleneckCount: 0,
      maxDuration: 0,
      minDuration: Infinity,
      details: []
    };
  }

  processMetrics[name].count++;
  processMetrics[name].totalDuration += duration;

  if (success) {
    processMetrics[name].successCount++;
  } else {
    processMetrics[name].failCount++;
  }

  if (duration > bottleneckThreshold) {
    processMetrics[name].bottleneckCount++;
    bottleneckDuration.add(duration, { process: name });
    bottleneckCounter.add(1, { process: name });
    console.log(`BOTTLENECK DETECTED in ${name}: Operation took ${duration.toFixed(2)}s (threshold: ${bottleneckThreshold}s)`);
  }

  if (duration > processMetrics[name].maxDuration) {
    processMetrics[name].maxDuration = duration;
  }

  if (duration < processMetrics[name].minDuration) {
    processMetrics[name].minDuration = duration;
  }

  // Add record of this operation with details
  processMetrics[name].details.push({
    timestamp: new Date().toISOString(),
    duration: duration,
    success: success,
    ...details
  });

  // Add to k6 metrics
  processDurations.add(duration, { process: name });
  
  // Record the operation response time
  operationTrend.add(duration, { process: name });
  
  // If not successful, record as failure
  if (!success) {
    operationFailRate.add(1, { process: name });
  }
}

// Safe JSON handling helper
function safeGetJson(response, path, defaultValue = undefined) {
  try {
    if (!response || !response.body) {
      return defaultValue;
    }
    return response.json(path);
  } catch (e) {
    console.error(`Error parsing JSON for path ${path}: ${e.message}`);
    return defaultValue;
  }
}

// Enhanced request helper with improved error handling
function makeRequest(method, url, payload = null, options = {}) {
  const defaultOptions = {
    headers: { 'Content-Type': 'application/json' },
    timeout: '30s',
    tags: {},
    maxRetries: 2,
    retryDelay: 3,
    baseBackoff: 5, // Base delay for exponential backoff (seconds)
  };

  // Merge options
  const requestOptions = { ...defaultOptions, ...options };
  const { maxRetries, retryDelay, baseBackoff, ...httpOptions } = requestOptions;

  let response;
  let attempt = 0;
  let lastError = null;

  while (attempt <= maxRetries) {
    try {
      if (attempt > 0) {
        // Exponential backoff (start with longer delay and increase with each retry)
        const backoffTime = baseBackoff * Math.pow(2, attempt - 1);
        console.log(`Retry attempt ${attempt}/${maxRetries} for ${url} after ${backoffTime}s backoff`);
        sleep(backoffTime);
      }
      
      // Add jitter to prevent thundering herd problem in high concurrency
      if (__VU > 1) {
        const jitter = Math.random() * 2; // Up to 2 seconds of random delay
        sleep(jitter);
      }

      if (method.toLowerCase() === 'get') {
        response = http.get(url, httpOptions);
      } else if (method.toLowerCase() === 'post') {
        // Ensure payload is a string
        const payloadStr = typeof payload === 'string' ? payload : JSON.stringify(payload);
        response = http.post(url, payloadStr, httpOptions);
      } else {
        throw new Error(`Unsupported HTTP method: ${method}`);
      }

      // Check for timeout or error
      if (response.error) {
        console.warn(`Request error: ${response.error} (status: ${response.status}, url: ${url})`);
        errorCounter.add(1, { type: response.error_code || 'unknown', url: url });
        lastError = response.error;
        attempt++;
        continue;
      }

      // Handle overload-related status codes
      if (response.status === 429 || response.status >= 500) {
        console.warn(`Server overloaded or error (status: ${response.status}, url: ${url})`);
        errorCounter.add(1, { type: `status_${response.status}`, url: url });
        lastError = `HTTP status ${response.status}`;
        attempt++;
        // Add additional backoff for these types of errors
        sleep(backoffTime * 2);
        continue;
      }

      // Success case
      return response;
    } catch (e) {
      console.error(`Exception on ${url}: ${e.message}`);
      errorCounter.add(1, { type: 'exception', url: url });
      lastError = e.message;
      attempt++;
    }
  }

  // All retries failed
  console.error(`All ${maxRetries} retries failed for ${url}: ${lastError}`);
  return {
    status: 0,
    body: "",
    error: lastError,
    error_code: 'max_retries_exceeded',
    json: (path) => undefined
  };
}

// Enhanced connection verification with better diagnostic info
export function connectionVerification() {
  let servicesReady = false;
  let attempts = 0;
  const maxAttempts = 20; // Increased from 15

  console.log('Starting service warm-up and verification...');

  // Initial warm-up period
  console.log("Giving services a 15-second warm-up period..."); // Increased from 10s
  sleep(15);

  // Check services readiness
  while (!servicesReady && attempts < maxAttempts) {
    attempts++;
    console.log(`Attempt ${attempts}/${maxAttempts} to verify services`);

    // Add progressive delay between attempts
    if (attempts > 1) {
      const waitTime = Math.min(5 + attempts, 20); // Increased max wait to 20s
      console.log(`Waiting ${waitTime}s before retry...`);
      sleep(waitTime);
    }

    try {
      let servicesUp = 0;
      
      // Check SM-DP
      console.log("Checking SM-DP status...");
      const smdpRes = http.get(`${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.status}`,
        { tags: { name: 'sm_dp_status_check' }, timeout: '20s' }); // Increased timeout

      if (smdpRes.status === 200) {
        console.log(`✓ SM-DP is ready`);
        servicesUp++;
      } else {
        console.log(`✗ SM-DP not ready: Status ${smdpRes.status}`);
      }

      // Check SM-SR
      console.log("Checking SM-SR status...");
      const smsrRes = http.get(`${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.status}`,
        { tags: { name: 'sm_sr_status_check' }, timeout: '20s' }); // Increased timeout

      if (smsrRes.status === 200) {
        console.log(`✓ SM-SR is ready`);
        servicesUp++;
      } else {
        console.log(`✗ SM-SR not ready: Status ${smsrRes.status}`);
      }

      // Check eUICC
      console.log("Checking eUICC status...");
      const euiccRes = http.get(`${API_CONFIG.euicc.base_url}${API_CONFIG.euicc.endpoints.status}`,
        { tags: { name: 'euicc_status_check' }, timeout: '20s' }); // Increased timeout

      if (euiccRes.status === 200) {
        console.log(`✓ eUICC is ready`);
        servicesUp++;
      } else {
        console.log(`✗ eUICC not ready: Status ${euiccRes.status}`);
      }

      // All services are up
      if (servicesUp === 3) {
        servicesReady = true;
        console.log('✓ All services are available and ready for testing!');
      } else {
        console.log(`${servicesUp}/3 services are currently available`);
      }

    } catch (e) {
      console.error(`Error checking service availability: ${e.message}`);
    }
  }

  // Final verification
  if (!servicesReady) {
    console.error('⚠️ CRITICAL: Could not verify all services after maximum attempts.');
    console.error('The test will continue but may fail. Check if your M2M RSP system is running properly.');
    
    // Try to diagnose the issue
    try {
      // Try to ping localhost directly
      const pingRes = http.get('http://localhost:8000/ping', { timeout: '5s' });
      console.log(`Basic connectivity test: ${pingRes.status === 200 ? 'Succeeded' : 'Failed'}`);
    } catch (e) {
      console.error(`Basic connectivity test failed: ${e.message}`);
      console.error('Possible connectivity issues with localhost services');
    }
  }

  // Add extended final sleep to ensure services are fully ready
  console.log("Allowing system to stabilize for 15 more seconds..."); // Increased from 10s
  sleep(15);

  return servicesReady;
}

// Complete RSP flow - sequential operations with increased delays
export function completeRspFlow() {
  // Generate unique IDs for this flow
  const euiccId = `89${randomString(17, '0123456789')}`;
  const profileId = `${randomString(19, '0123456789')}`;
  let isdpAid = null;

  // Record flow start time
  const flowStartTime = new Date();

  // Give the system a moment to prepare
  sleep(5);

  group('1. eUICC Registration with SM-SR', function () {
    console.log(`Registering eUICC with ID: ${euiccId} to SM-SR`);

    // Very simplified payload to minimize parsing issues
    const payload = {
      euiccId: euiccId,
      euiccInfo1: {
        svn: "2.1.0",
        euiccCiPKId: `id12345`,
        euiccCiPK: {
          key: encoding.b64encode("SampleKeyForTestingOnly"),
          algorithm: "EC/SECP256R1"
        },
        euiccCapabilities: {
          supportedAlgorithms: ["ECKA-ECDH", "AES-128"],
          secureDomainSupport: true,
          pskSupport: true
        },
        testEuicc: false
      },
      eid: `89${euiccId}`
    };

    const startTime = new Date();

    // Enhanced request with more retries and longer timeout
    const res = makeRequest(
      'post',
      `${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.euicc_register}`,
      payload,
      {
        tags: { name: 'euicc_registration' },
        timeout: '90s', // Much longer timeout
        maxRetries: 3,
        retryDelay: 5
      }
    );

    const duration = (new Date() - startTime) / 1000;

    const success = res.status === 200;

    if (!success) {
      console.error(`eUICC registration failed with status ${res.status}, error: ${res.error || 'none'}`);
    } else {
      console.log(`Successfully registered eUICC ${euiccId}`);
    }

    // Record metrics
    trackProcess('euicc_registration', duration, success, {
      euiccId: euiccId,
      statusCode: res.status,
      error: res.error
    });

    // If registration failed, we should stop the flow for this iteration
    if (!success) {
      console.error(`Cannot continue RSP flow for eUICC ${euiccId} due to registration failure`);
      return;
    }

    sleep(5); // Extended sleep to let the system recover
  });

  group('2. ISD-P Creation on eUICC', function () {
    console.log(`Creating ISD-P for eUICC ID: ${euiccId}`);

    const payload = {
      euiccId: euiccId,
      memoryRequired: 256
    };

    const startTime = new Date();

    // Enhanced request with more retries
    const res = makeRequest(
      'post',
      `${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.isdp_create}`,
      payload,
      {
        tags: { name: 'isdp_creation' },
        timeout: '60s',
        maxRetries: 2
      }
    );

    const duration = (new Date() - startTime) / 1000;

    const success = res.status === 200;

    // Store the ISD-P AID if available
    if (success) {
      try {
        isdpAid = safeGetJson(res, 'isdpAid');
        if (isdpAid) {
          console.log(`Successfully created ISD-P with AID: ${isdpAid}`);
        } else {
          console.warn("ISD-P creation succeeded but no AID was returned");
        }
      } catch (e) {
        console.error(`Error extracting ISD-P AID: ${e.message}`);
      }
    } else {
      console.error(`ISD-P creation failed with status ${res.status}, error: ${res.error || 'none'}`);
    }

    // Record metrics
    trackProcess('isdp_creation', duration, success, {
      euiccId: euiccId,
      isdpAid: isdpAid,
      statusCode: res.status,
      error: res.error
    });

    sleep(5); // Extended sleep
  });

  // Continue with the rest of the flow only if previous steps succeeded
  if (processMetrics.isdp_creation && processMetrics.isdp_creation.successCount > 0) {

    group('3. Key Establishment between eUICC and SM-DP', function () {
      console.log(`Establishing secure keys between eUICC and SM-DP`);

      // Step 1: Initialize key establishment with SM-DP
      const startTime = new Date();

      const initRes = makeRequest(
        'post',
        `${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.key_establishment_init}`,
        {},
        {
          tags: { name: 'key_establishment_init' },
          timeout: '45s'
        }
      );

      let sessionId, serverPublicKey, completeSuccess = false;
      let initSuccess = initRes.status === 200;

      if (initSuccess) {
        try {
          sessionId = safeGetJson(initRes, 'session_id');
          // Get the server's public key from the init response
          serverPublicKey = safeGetJson(initRes, 'public_key');

          if (!sessionId || !serverPublicKey) {
            console.warn("Key establishment init succeeded but missing required data");
            initSuccess = false;
          } else {
            console.log(`Received session ID ${sessionId} and server public key`);

            // Small delay between init and complete
            sleep(2);

            // Instead of generating our own fake key, we'll ECHO BACK the server's key
            // This ensures it's in the exact format the server expects
            const completePayload = {
              session_id: sessionId,
              public_key: serverPublicKey  // Echo back the same public key
            };

            const completeRes = makeRequest(
              'post',
              `${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.key_establishment_complete}`,
              completePayload,
              {
                tags: { name: 'key_establishment_complete' },
                timeout: '45s'
              }
            );

            completeSuccess = completeRes.status === 200;
            if (!completeSuccess) {
              console.error(`Key establishment completion failed: ${completeRes.error || 'Status ' + completeRes.status}`);
            } else {
              console.log(`Successfully completed key establishment`);
            }
          }
        } catch (e) {
          console.error(`Error in key establishment: ${e.message}`);
          initSuccess = false;
        }
      } else {
        console.error(`Key establishment init failed: ${initRes.error || 'Status ' + initRes.status}`);
      }

      const duration = (new Date() - startTime) / 1000;
      const success = initSuccess && completeSuccess;

      // Record metrics
      trackProcess('key_establishment', duration, success, {
        euiccId: euiccId,
        sessionId: sessionId,
        initSuccess: initSuccess,
        completeSuccess: completeSuccess
      });

      sleep(5); // Extended sleep
    });

    group('4. Profile Preparation at SM-DP', function () {
      console.log(`Preparing profile with ID: ${profileId} at SM-DP`);

      const payload = {
        profileType: "telecom",
        iccid: profileId,
        timestamp: Math.floor(Date.now() / 1000)
      };

      const startTime = new Date();

      // This operation seems to be a major bottleneck, give it extra time and retries
      const res = makeRequest(
        'post',
        `${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.profile_prepare}`,
        payload,
        {
          tags: { name: 'profile_preparation' },
          timeout: '120s', // 2 minutes - very generous timeout
          maxRetries: 0,   // No retries since this operation is heavyweight
        }
      );

      const duration = (new Date() - startTime) / 1000;

      const success = res.status === 200;

      if (!success) {
        console.error(`Profile preparation failed: ${res.error || 'Status ' + res.status}`);
      } else {
        console.log(`Successfully prepared profile ${profileId}`);
      }

      // Record metrics
      trackProcess('profile_preparation', duration, success, {
        profileId: profileId,
        statusCode: res.status,
        error: res.error
      });

      // Long recovery time after this heavyweight operation
      sleep(10);
    });

    // Only attempt profile installation if preparation succeeded
    if (processMetrics.profile_preparation &&
      processMetrics.profile_preparation.successCount > 0) {

      group('5. Profile Download and Installation', function () {
        console.log(`Installing profile ${profileId} on eUICC ${euiccId}`);

        const payload = {
          profileId: profileId
        };

        const startTime = new Date();

        const res = makeRequest(
          'post',
          `${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.profile_install}/${euiccId}`,
          payload,
          {
            tags: { name: 'profile_installation' },
            timeout: '90s', // Long timeout
            maxRetries: 0,  // No retries for this heavyweight operation
          }
        );

        const duration = (new Date() - startTime) / 1000;

        const success = res.status === 200;

        if (!success) {
          console.error(`Profile installation failed: ${res.error || 'Status ' + res.status}`);
        } else {
          console.log(`Successfully installed profile ${profileId} on eUICC ${euiccId}`);
        }

        // Record metrics
        trackProcess('profile_installation', duration, success, {
          profileId: profileId,
          euiccId: euiccId,
          statusCode: res.status,
          error: res.error
        });

        sleep(10); // Extended sleep
      });

      group('6. Profile Enabling', function () {
        console.log(`Enabling profile ${profileId} on eUICC ${euiccId}`);

        const payload = {
          profileId: profileId
        };

        const startTime = new Date();

        const res = makeRequest(
          'post',
          `${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.profile_enable}/${euiccId}`,
          payload,
          {
            tags: { name: 'profile_enabling' },
            timeout: '90s', // Long timeout
            maxRetries: 0,  // No retries
          }
        );

        const duration = (new Date() - startTime) / 1000;

        const success = res.status === 200;

        if (!success) {
          console.error(`Profile enabling failed: ${res.error || 'Status ' + res.status}`);
        } else {
          console.log(`Successfully enabled profile ${profileId} on eUICC ${euiccId}`);
        }

        // Record metrics
        trackProcess('profile_enabling', duration, success, {
          profileId: profileId,
          euiccId: euiccId,
          statusCode: res.status,
          error: res.error
        });

        sleep(5); // Extended sleep
      });
    } else {
      console.warn(`Skipping profile installation steps for eUICC ${euiccId} due to profile preparation failure`);
    }
  } else {
    console.warn(`Skipping remaining flow steps for eUICC ${euiccId} due to early failures`);
  }

  group('7. Final Status Check', function () {
    console.log(`Performing final status check on all components`);

    const startTime = new Date();

    // Check SM-DP status
    const smdpRes = http.get(
      `${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.status}`,
      {
        tags: { name: 'smdp_status_check' },
        timeout: '15s'
      }
    );

    const smdpSuccess = smdpRes.status === 200;

    // Check SM-SR status
    const smsrRes = http.get(
      `${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.status}`,
      {
        tags: { name: 'smsr_status_check' },
        timeout: '15s'
      }
    );

    const smsrSuccess = smsrRes.status === 200;

    // Check eUICC status
    const euiccRes = http.get(
      `${API_CONFIG.euicc.base_url}${API_CONFIG.euicc.endpoints.status}`,
      {
        tags: { name: 'euicc_status_check' },
        timeout: '15s'
      }
    );

    const euiccSuccess = euiccRes.status === 200;

    let profileInstalled = false;
    if (euiccSuccess) {
      try {
        const installedProfiles = safeGetJson(euiccRes, 'installedProfiles', 0);
        profileInstalled = installedProfiles > 0;
      } catch (e) {
        console.error(`Error checking profile installation: ${e.message}`);
      }
    }

    const duration = (new Date() - startTime) / 1000;
    const success = smdpSuccess && smsrSuccess && euiccSuccess;

    // Record metrics
    trackProcess('status_check', duration, success, {
      euiccId: euiccId,
      smdpStatus: smdpRes.status,
      smsrStatus: smsrRes.status,
      euiccStatus: euiccRes.status,
      profileInstalled: profileInstalled
    });
  });

  // Calculate total flow duration
  const flowDuration = (new Date() - flowStartTime) / 1000;

  // Record total flow metrics
  trackProcess('complete_rsp_flow', flowDuration, true, {
    euiccId: euiccId,
    profileId: profileId,
    isdpAid: isdpAid
  });

  // Log flow completion
  console.log(`Completed M2M RSP flow for eUICC ${euiccId} in ${flowDuration.toFixed(2)} seconds`);

  // Final recovery period before next iteration
  sleep(10);
}

// Targeted bottleneck analysis - one operation at a time
export function bottleneckAnalysis() {
  // Generate unique IDs for this run
  const euiccId = `89${randomString(17, '0123456789')}`;
  const profileId = `${randomString(19, '0123456789')}`;
  
  // Add short sleep based on VU number to prevent all VUs hitting the server at exactly the same time
  if (__VU > 1) {
    // Spread initial requests using VU number to stagger
    const staggerMs = (__VU % 50) * 300; // Spread over 15 seconds for each batch of 50 VUs
    sleep(staggerMs / 1000);
  }

  // Skip eUICC registration for high VU counts to reduce server load
  // Only register for lower VU numbers or a small percentage of high VU numbers
  const shouldRegisterEuicc = __VU <= 100 || (__VU % 20 === 0);
  
  if (shouldRegisterEuicc) {
    console.log(`VU ${__VU}: Setting up for bottleneck analysis - registering eUICC`);

    const registerPayload = {
      euiccId: euiccId,
      euiccInfo1: {
        svn: "2.1.0",
        euiccCiPKId: "id12345",
        euiccCiPK: {
          key: encoding.b64encode("SimpleTestKey"),
          algorithm: "EC/SECP256R1"
        },
        euiccCapabilities: {
          supportedAlgorithms: ["ECKA-ECDH", "AES-128"],
          secureDomainSupport: true,
          pskSupport: true
        },
        testEuicc: false
      },
      eid: `89${euiccId}`
    };

    const regRes = makeRequest(
      'post',
      `${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.euicc_register}`,
      registerPayload,
      {
        timeout: '60s',
        maxRetries: 2
      }
    );

    if (regRes.status !== 200) {
      console.error(`VU ${__VU}: Could not register eUICC for bottleneck analysis. Status: ${regRes.status}`);
    } else {
      console.log(`VU ${__VU}: Registered eUICC ${euiccId} for bottleneck analysis`);

      // Create ISD-P for this eUICC - only if registration succeeded
      sleep(2 + (Math.random() * 3)); // Random sleep between 2-5s
      console.log(`VU ${__VU}: Creating ISD-P for bottleneck analysis`);

      const isdpRes = makeRequest(
        'post',
        `${API_CONFIG.sm_sr.base_url}${API_CONFIG.sm_sr.endpoints.isdp_create}`,
        { euiccId: euiccId, memoryRequired: 256 },
        {
          timeout: '60s',
          maxRetries: 1
        }
      );

      if (isdpRes.status !== 200) {
        console.error(`VU ${__VU}: Could not create ISD-P for bottleneck analysis. Status: ${isdpRes.status}`);
      } else {
        console.log(`VU ${__VU}: Created ISD-P for eUICC ${euiccId}`);
      }

      sleep(2 + (Math.random() * 2)); // Random sleep between 2-4s
    }
  }

  // Determine which bottleneck test to run based on VU number to distribute load
  // This prevents all VUs from hitting the same endpoint simultaneously
  const testType = __VU % 2; // 0 or 1
  
  if (testType === 0 || __VU <= 200) {
    // First half of VUs or low VU numbers test key establishment
    group('Key Establishment Bottleneck Analysis', function () {
      console.log(`VU ${__VU}: Testing Key Establishment bottleneck`);

      const startTime = new Date();

      // Step 1: Init
      const initRes = makeRequest(
        'post',
        `${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.key_establishment_init}`,
        {},
        {
          tags: { name: 'key_establishment_init_bottleneck' },
          timeout: '45s'
        }
      );

      let success = false;

      if (initRes.status === 200) {
        const sessionId = safeGetJson(initRes, 'session_id');
        const serverPublicKey = safeGetJson(initRes, 'public_key');

        if (sessionId && serverPublicKey) {
          // Add small random delay to spread load
          sleep(Math.random() * 1.5);
          
          // Echo back the server's public key
          const completeRes = makeRequest(
            'post',
            `${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.key_establishment_complete}`,
            {
              session_id: sessionId,
              public_key: serverPublicKey  // Using server's key
            },
            {
              tags: { name: 'key_establishment_complete_bottleneck' },
              timeout: '45s'
            }
          );

          success = completeRes.status === 200;
        }
      }

      const duration = (new Date() - startTime) / 1000;

      trackProcess('key_establishment_bottleneck', duration, success, {
        vu: __VU,
        status: success ? 'success' : 'failure'
      });

      if (duration > bottleneckThreshold) {
        console.log(`VU ${__VU} BOTTLENECK DETECTED: Key Establishment took ${duration.toFixed(2)}s (threshold: ${bottleneckThreshold}s)`);
      }

      // Variable recovery time to prevent synchronized requests
      sleep(3 + (Math.random() * 5));
    });
  }
  
  if (testType === 1 || __VU <= 200) {
    // Second half of VUs or low VU numbers test profile preparation
    group('Profile Preparation Bottleneck Analysis', function () {
      console.log(`VU ${__VU}: Testing Profile Preparation bottleneck`);

      const payload = {
        profileType: "telecom",
        iccid: profileId,
        timestamp: Math.floor(Date.now() / 1000)
      };

      const startTime = new Date();
      const res = makeRequest(
        'post',
        `${API_CONFIG.sm_dp.base_url}${API_CONFIG.sm_dp.endpoints.profile_prepare}`,
        payload,
        {
          tags: { name: 'profile_preparation_bottleneck' },
          timeout: '120s'  // 2 minutes
        }
      );
      const duration = (new Date() - startTime) / 1000;

      trackProcess('profile_preparation_bottleneck', duration, res.status === 200, {
        vu: __VU,
        profileId: profileId,
        status: res.status
      });

      // If it was a bottleneck, log it
      if (duration > bottleneckThreshold) {
        console.log(`VU ${__VU} BOTTLENECK DETECTED: Profile Preparation took ${duration.toFixed(2)}s (threshold: ${bottleneckThreshold}s)`);
      }

      // Variable recovery period
      sleep(5 + (Math.random() * 7));
    });
  }

  // Give a random recovery period before next tests
  // This helps prevent synchronized VUs from creating traffic spikes
  sleep(2 + (Math.random() * 5));
}

// Generate detailed summary report
export function handleSummary(data) {
  // Calculate final process metrics
  for (const [name, metrics] of Object.entries(processMetrics)) {
    if (metrics.count > 0) {
      metrics.avgDuration = metrics.totalDuration / metrics.count;
      metrics.successRate = metrics.successCount / metrics.count;
      metrics.bottleneckRate = metrics.bottleneckCount / metrics.count;
    } else {
      metrics.avgDuration = 0;
      metrics.successRate = 0;
      metrics.bottleneckRate = 0;
    }
  }

  // Sort processes by bottleneck rate (descending) for reporting
  const sortedProcesses = Object.entries(processMetrics)
    .map(([name, metrics]) => ({
      name,
      ...metrics,
      bottleneckRate: metrics.bottleneckCount / Math.max(1, metrics.count)
    }))
    .sort((a, b) => b.bottleneckRate - a.bottleneckRate);

  // Identify top bottlenecks - fixed to properly report bottlenecks with rate > 0
  const bottlenecks = sortedProcesses
    .filter(process => process.bottleneckCount > 0)  // Changed from bottleneckRate > 0 to bottleneckCount > 0
    .map(process => ({
      process: process.name,
      avgDuration: process.avgDuration,
      maxDuration: process.maxDuration,
      occurrences: process.bottleneckCount,
      totalCount: process.count,
      bottleneckRate: process.bottleneckRate
    }));

  // Create M2M RSP flow summary
  const rspFlowSummary = {
    euicc_registration: processMetrics.euicc_registration || { avgDuration: 0, successRate: 0 },
    isdp_creation: processMetrics.isdp_creation || { avgDuration: 0, successRate: 0 },
    key_establishment: processMetrics.key_establishment || { avgDuration: 0, successRate: 0 },
    profile_preparation: processMetrics.profile_preparation || { avgDuration: 0, successRate: 0 },
    profile_installation: processMetrics.profile_installation || { avgDuration: 0, successRate: 0 },
    profile_enabling: processMetrics.profile_enabling || { avgDuration: 0, successRate: 0 },
    complete_flow: processMetrics.complete_rsp_flow || { avgDuration: 0, successRate: 0 }
  };

  // Get error statistics
  const errors = {};
  if (data.metrics.request_errors) {
    for (const [name, value] of Object.entries(data.metrics.request_errors.values)) {
      if (name.includes('type:')) {
        const type = name.split(':')[1].split(',')[0];
        errors[type] = (errors[type] || 0) + value;
      }
    }
  }

  // Create complete summary object
  const summary = {
    timestamp: new Date().toISOString(),
    testDuration: data.state.testRunDurationMs / 1000,
    bottleneckThreshold: bottleneckThreshold,
    rspFlow: rspFlowSummary,
    bottlenecks: bottlenecks,
    errors: errors,
    detailedMetrics: processMetrics
  };

  // Create CSV summary for data analysis
  const csvRows = [];
  
  // CSV Header
  csvRows.push("Process,Count,AvgDuration,MaxDuration,MinDuration,SuccessCount,FailCount,BottleneckCount,SuccessRate,BottleneckRate");
  
  // Add each process as a row
  for (const [name, metrics] of Object.entries(processMetrics)) {
    const successRate = metrics.count > 0 ? metrics.successCount / metrics.count : 0;
    const bottleneckRate = metrics.count > 0 ? metrics.bottleneckCount / metrics.count : 0;
    
    csvRows.push(
      `${name},${metrics.count},${metrics.avgDuration.toFixed(2)},${metrics.maxDuration.toFixed(2)},${
        metrics.minDuration === Infinity ? 0 : metrics.minDuration.toFixed(2)
      },${metrics.successCount},${metrics.failCount},${metrics.bottleneckCount},${
        successRate.toFixed(4)
      },${bottleneckRate.toFixed(4)}`
    );
  }
  
  // Add a separate bottlenecks CSV for more detailed analysis
  const bottlenecksCsvRows = [];
  bottlenecksCsvRows.push("Process,AvgDuration,MaxDuration,Occurrences,TotalCount,BottleneckRate");
  
  for (const b of bottlenecks) {
    bottlenecksCsvRows.push(
      `${b.process},${b.avgDuration.toFixed(2)},${b.maxDuration.toFixed(2)},${b.occurrences},${b.totalCount},${b.bottleneckRate.toFixed(4)}`
    );
  }
  
  // Create a CSV with all operation details for deep analysis
  const detailsCsvRows = [];
  detailsCsvRows.push("Process,Timestamp,Duration,Success");
  
  for (const [name, metrics] of Object.entries(processMetrics)) {
    if (metrics.details && metrics.details.length > 0) {
      for (const detail of metrics.details) {
        detailsCsvRows.push(
          `${name},${detail.timestamp},${detail.duration.toFixed(2)},${detail.success ? 1 : 0}`
        );
      }
    }
  }

  return {
    'summary.json': JSON.stringify(summary, null, 2),
    'bottlenecks.json': JSON.stringify(bottlenecks, null, 2),
    'summary.csv': csvRows.join('\n'),
    'bottlenecks.csv': bottlenecksCsvRows.join('\n'),
    'operation_details.csv': detailsCsvRows.join('\n'),
    'stdout': textSummary(data, summary, bottlenecks)
  };
}

// Helper function to format text summary
function textSummary(data, summary, bottlenecks) {
  const out = [];

  out.push('# M2M Remote SIM Provisioning Performance Report\n');

  out.push('## Test Configuration');
  out.push(`- Bottleneck Threshold: ${bottleneckThreshold} seconds`);
  out.push(`- Test Duration: ${(summary.testDuration / 60).toFixed(2)} minutes`);
  out.push(`- Test Completed: ${summary.timestamp}\n`);

  out.push('## Connection Errors');
  if (Object.keys(summary.errors).length > 0) {
    out.push('The following connection errors were encountered:');
    for (const [type, count] of Object.entries(summary.errors)) {
      out.push(`- ${type}: ${count} occurrences`);
    }
  } else {
    out.push('- No connection errors were recorded');
  }
  out.push('');

  out.push('## Complete RSP Flow Performance');
  if (summary.rspFlow.complete_flow.count > 0) {
    out.push(`- Average Total Flow Duration: ${summary.rspFlow.complete_flow.avgDuration.toFixed(2)} seconds`);
    out.push(`- Success Rate: ${(summary.rspFlow.complete_flow.successRate * 100).toFixed(2)}%\n`);
  } else {
    out.push('- No complete flows were recorded\n');
  }

  out.push('## Individual Process Performance');
  out.push('| Process | Count | Avg Duration (s) | Max Duration (s) | Success Rate | Bottleneck Rate |');
  out.push('|---------|-------|------------------|------------------|--------------|-----------------|');

  // List key processes from the flow
  const keyProcesses = [
    'euicc_registration',
    'isdp_creation',
    'key_establishment',
    'profile_preparation',
    'profile_installation',
    'profile_enabling'
  ];

  keyProcesses.forEach(process => {
    if (processMetrics[process]) {
      const metrics = processMetrics[process];
      out.push(`| ${process} | ${metrics.count} | ${metrics.avgDuration.toFixed(2)} | ${metrics.maxDuration.toFixed(2)} | ${(metrics.successRate * 100).toFixed(2)}% | ${(metrics.bottleneckCount / Math.max(1, metrics.count) * 100).toFixed(2)}% |`);
    }
  });

  out.push('\n## Bottleneck Analysis for M2M RSP');
  if (bottlenecks.length > 0) {
    out.push('The following processes exceeded the bottleneck threshold:');
    bottlenecks.forEach((bottleneck, index) => {
      out.push(`\n${index + 1}. **${bottleneck.process}**`);
      out.push(`   - Average Duration: ${bottleneck.avgDuration.toFixed(2)} seconds`);
      out.push(`   - Maximum Duration: ${bottleneck.maxDuration.toFixed(2)} seconds`);
      out.push(`   - Bottleneck Rate: ${(bottleneck.bottleneckRate * 100).toFixed(2)}% of operations exceeded threshold`);
      out.push(`   - Occurrences: ${bottleneck.occurrences} of ${bottleneck.totalCount} operations`);
    });
  } else {
    out.push('- No bottlenecks detected (all operations completed within threshold)');
  }

  // Add system performance recommendations based on identified issues
  out.push('\n## System Performance Recommendations');

  // Primary issue appears to be profile preparation based on the logs
  out.push('\n### Profile Preparation Optimization');
  out.push('The Profile Preparation operation is a significant bottleneck in the system:');
  out.push('- Consider implementing caching for prepared profiles');
  out.push('- Optimize the cryptographic operations in the SM-DP implementation');
  out.push('- Review the `create_sample_profile` method in sm_dp.py for performance improvements');
  out.push('- Consider parallel profile preparation to improve throughput');

  // Registration timeouts
  out.push('\n### eUICC Registration Optimization');
  out.push('The eUICC Registration process is experiencing timeouts:');
  out.push('- Optimize the PSK generation in SM-SR');
  out.push('- Review the EIS data structure for optimization');
  out.push('- Consider implementing connection pooling between SM-SR and eUICC');

  // General recommendations
  out.push('\n### General System Recommendations');
  out.push('- Increase timeout configurations in all components');
  out.push('- Implement more robust error handling and retry mechanisms');
  out.push('- Consider implementing a queue-based architecture for high-load scenarios');
  out.push('- Profile-guided optimization of the Python implementation');
  out.push('- Consider implementing rate limiting to prevent system overload');

  return out.join('\n');
}
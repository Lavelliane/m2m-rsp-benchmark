import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
export let errorRate = new Rate('errors');
export let responseTime = new Trend('response_time');
export let rspOperationDuration = new Trend('rsp_operation_duration');
export let throughput = new Counter('operations_completed');

// Zone configurations for microk8s NodePort services
const zones = [
    {
        name: 'zone-a',
        baseUrl: 'http://localhost:30080',
        region: 'us-east-1'
    },
    {
        name: 'zone-b', 
        baseUrl: 'http://localhost:30081',
        region: 'us-west-2'
    },
    {
        name: 'zone-c',
        baseUrl: 'http://localhost:30082', 
        region: 'eu-central-1'
    }
];

// Test configuration - will be overridden by command line options
export let options = {
    stages: [
        { duration: '30s', target: 5 },   // Ramp up to 5 users over 30s
        { duration: '60s', target: 5 },   // Stay at 5 users for 60s
        { duration: '30s', target: 10 },  // Ramp up to 10 users over 30s
        { duration: '60s', target: 10 },  // Stay at 10 users for 60s
        { duration: '30s', target: 15 },  // Ramp up to 15 users over 30s
        { duration: '60s', target: 15 },  // Stay at 15 users for 60s
        { duration: '30s', target: 0 },   // Ramp down over 30s
    ],
    thresholds: {
        'http_req_duration': ['p(95)<1000'], // 95% of requests should be below 1000ms
        'errors': ['rate<0.1'],              // Error rate should be less than 10%
    },
};

// Global variables for test data
let euiccCounter = 0;
let profileCounter = 0;

// Generate unique identifiers
function generateEuiccId() {
    return `EUICC_${Date.now()}_${++euiccCounter}_${__VU}`;
}

function generateProfileId() {
    return `PROF_${Date.now()}_${++profileCounter}_${__VU}`;
}

function generateIccid() {
    const timestamp = Date.now().toString().slice(-10);
    const vu = __VU.toString().padStart(3, '0');
    const iter = __ITER.toString().padStart(4, '0');
    return `8901${timestamp}${vu}${iter}`.slice(0, 20);
}

// Select a random zone for load balancing
function getRandomZone() {
    return zones[Math.floor(Math.random() * zones.length)];
}

// RSP Operation: Register eUICC
function registerEuicc(zone, euiccId) {
    const startTime = Date.now();
    
    const payload = {
        euiccId: euiccId,
        deviceInfo: {
            deviceType: 'IoT_Sensor',
            manufacturer: 'TestCorp',
            model: 'TC-001'
        },
        eis: {
            euiccCapabilities: ['PROFILE_DOWNLOAD', 'PROFILE_MANAGEMENT'],
            platformLabel: 'TestPlatform_1.0'
        }
    };

    const response = http.post(
        `${zone.baseUrl}/smsr/euicc/register`,
        JSON.stringify(payload),
        {
            headers: { 'Content-Type': 'application/json' },
            tags: { 
                operation: 'register_euicc',
                zone: zone.name,
                region: zone.region
            }
        }
    );

    const duration = Date.now() - startTime;
    
    const success = check(response, {
        'register_euicc_status_200': (r) => r.status === 200,
        'register_euicc_response_time_ok': (r) => r.timings.duration < 2000,
        'register_euicc_has_psk': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'success' && body.psk;
            } catch {
                return false;
            }
        }
    });

    errorRate.add(!success);
    responseTime.add(response.timings.duration);
    rspOperationDuration.add(duration, { operation: 'register_euicc', zone: zone.name });
    
    if (success) {
        throughput.add(1, { operation: 'register_euicc', zone: zone.name });
        try {
            const body = JSON.parse(response.body);
            return { success: true, psk: body.psk, smsrId: body.smsrId };
        } catch {
            return { success: false };
        }
    }
    
    return { success: false };
}

// RSP Operation: Create ISD-P
function createIsdp(zone, euiccId) {
    const startTime = Date.now();
    
    const payload = {
        euiccId: euiccId,
        memoryRequired: 256,
        profileType: 'telecom'
    };

    const response = http.post(
        `${zone.baseUrl}/smsr/isdp/create`,
        JSON.stringify(payload),
        {
            headers: { 'Content-Type': 'application/json' },
            tags: { 
                operation: 'create_isdp',
                zone: zone.name,
                region: zone.region
            }
        }
    );

    const duration = Date.now() - startTime;
    
    const success = check(response, {
        'create_isdp_status_200': (r) => r.status === 200,
        'create_isdp_response_time_ok': (r) => r.timings.duration < 2000,
        'create_isdp_has_aid': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'success' && body.isdpAid;
            } catch {
                return false;
            }
        }
    });

    errorRate.add(!success);
    responseTime.add(response.timings.duration);
    rspOperationDuration.add(duration, { operation: 'create_isdp', zone: zone.name });
    
    if (success) {
        throughput.add(1, { operation: 'create_isdp', zone: zone.name });
        try {
            const body = JSON.parse(response.body);
            return { success: true, isdpAid: body.isdpAid };
        } catch {
            return { success: false };
        }
    }
    
    return { success: false };
}

// RSP Operation: Prepare Profile
function prepareProfile(zone, profileId) {
    const startTime = Date.now();
    
    const payload = {
        profileType: 'telecom',
        iccid: generateIccid(),
        operator: {
            name: 'TestOperator',
            mcc: '001',
            mnc: '01'
        }
    };

    const response = http.post(
        `${zone.baseUrl}/smdp/profile/prepare`,
        JSON.stringify(payload),
        {
            headers: { 'Content-Type': 'application/json' },
            tags: { 
                operation: 'prepare_profile',
                zone: zone.name,
                region: zone.region
            }
        }
    );

    const duration = Date.now() - startTime;
    
    const success = check(response, {
        'prepare_profile_status_200': (r) => r.status === 200,
        'prepare_profile_response_time_ok': (r) => r.timings.duration < 3000,
        'prepare_profile_success': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'success' && body.profileId;
            } catch {
                return false;
            }
        }
    });

    errorRate.add(!success);
    responseTime.add(response.timings.duration);
    rspOperationDuration.add(duration, { operation: 'prepare_profile', zone: zone.name });
    
    if (success) {
        throughput.add(1, { operation: 'prepare_profile', zone: zone.name });
        try {
            const body = JSON.parse(response.body);
            return { success: true, profileId: body.profileId };
        } catch {
            return { success: false };
        }
    }
    
    return { success: false };
}

// RSP Operation: Install Profile
function installProfile(zone, euiccId, profileId) {
    const startTime = Date.now();
    
    const payload = {
        profileId: profileId,
        installationType: 'download'
    };

    const response = http.post(
        `${zone.baseUrl}/smsr/profile/install/${euiccId}`,
        JSON.stringify(payload),
        {
            headers: { 'Content-Type': 'application/json' },
            tags: { 
                operation: 'install_profile',
                zone: zone.name,
                region: zone.region
            }
        }
    );

    const duration = Date.now() - startTime;
    
    const success = check(response, {
        'install_profile_status_200': (r) => r.status === 200,
        'install_profile_response_time_ok': (r) => r.timings.duration < 5000,
        'install_profile_success': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'success' && body.encryptedData;
            } catch {
                return false;
            }
        }
    });

    errorRate.add(!success);
    responseTime.add(response.timings.duration);
    rspOperationDuration.add(duration, { operation: 'install_profile', zone: zone.name });
    
    if (success) {
        throughput.add(1, { operation: 'install_profile', zone: zone.name });
    }
    
    return success;
}

// RSP Operation: Key Establishment
function keyEstablishment(zone) {
    const startTime = Date.now();
    
    // Step 1: Initialize key establishment
    const initResponse = http.post(
        `${zone.baseUrl}/smdp/key-establishment/init`,
        JSON.stringify({}),
        {
            headers: { 'Content-Type': 'application/json' },
            tags: { 
                operation: 'key_establishment_init',
                zone: zone.name,
                region: zone.region
            }
        }
    );

    if (initResponse.status !== 200) {
        errorRate.add(true);
        return { success: false };
    }

    let sessionData;
    try {
        sessionData = JSON.parse(initResponse.body);
    } catch {
        errorRate.add(true);
        return { success: false };
    }

    // Step 2: Respond to key establishment
    const respondPayload = {
        session_id: sessionData.session_id,
        entity: 'sm-dp',
        public_key: sessionData.public_key,
        random_challenge: sessionData.random_challenge
    };

    const respondResponse = http.post(
        `${zone.baseUrl}/euicc/key-establishment/respond`,
        JSON.stringify(respondPayload),
        {
            headers: { 'Content-Type': 'application/json' },
            tags: { 
                operation: 'key_establishment_respond',
                zone: zone.name,
                region: zone.region
            }
        }
    );

    const duration = Date.now() - startTime;
    
    const success = check(respondResponse, {
        'key_establishment_status_200': (r) => r.status === 200,
        'key_establishment_response_time_ok': (r) => r.timings.duration < 3000,
        'key_establishment_success': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'success' && body.public_key;
            } catch {
                return false;
            }
        }
    });

    errorRate.add(!success);
    responseTime.add(respondResponse.timings.duration);
    rspOperationDuration.add(duration, { operation: 'key_establishment', zone: zone.name });
    
    if (success) {
        throughput.add(1, { operation: 'key_establishment', zone: zone.name });
    }
    
    return { success: success };
}

// RSP Operation: Status Check
function checkStatus(zone, entityType = 'smdp') {
    const startTime = Date.now();
    
    const response = http.get(
        `${zone.baseUrl}/status/${entityType}`,
        {
            tags: { 
                operation: 'status_check',
                zone: zone.name,
                region: zone.region,
                entity: entityType
            }
        }
    );

    const duration = Date.now() - startTime;
    
    const success = check(response, {
        'status_check_200': (r) => r.status === 200,
        'status_check_response_time_ok': (r) => r.timings.duration < 1000,
        'status_check_active': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'active';
            } catch {
                return false;
            }
        }
    });

    errorRate.add(!success);
    responseTime.add(response.timings.duration);
    rspOperationDuration.add(duration, { operation: 'status_check', zone: zone.name });
    
    if (success) {
        throughput.add(1, { operation: 'status_check', zone: zone.name });
    }
    
    return success;
}

// Complete RSP Flow: End-to-end test
function completeRspFlow(zone) {
    const flowStartTime = Date.now();
    
    // Generate test identifiers
    const euiccId = generateEuiccId();
    const profileId = generateProfileId();
    
    // Step 1: Register eUICC
    const regResult = registerEuicc(zone, euiccId);
    if (!regResult.success) {
        return { success: false, step: 'register_euicc' };
    }
    
    sleep(0.1); // Small delay between operations
    
    // Step 2: Create ISD-P
    const isdpResult = createIsdp(zone, euiccId);
    if (!isdpResult.success) {
        return { success: false, step: 'create_isdp' };
    }
    
    sleep(0.1);
    
    // Step 3: Key Establishment
    const keyResult = keyEstablishment(zone);
    if (!keyResult.success) {
        return { success: false, step: 'key_establishment' };
    }
    
    sleep(0.1);
    
    // Step 4: Prepare Profile
    const profileResult = prepareProfile(zone, profileId);
    if (!profileResult.success) {
        return { success: false, step: 'prepare_profile' };
    }
    
    sleep(0.1);
    
    // Step 5: Install Profile
    const installResult = installProfile(zone, euiccId, profileResult.profileId || profileId);
    if (!installResult) {
        return { success: false, step: 'install_profile' };
    }
    
    const totalDuration = Date.now() - flowStartTime;
    rspOperationDuration.add(totalDuration, { operation: 'complete_rsp_flow', zone: zone.name });
    throughput.add(1, { operation: 'complete_rsp_flow', zone: zone.name });
    
    return { success: true, duration: totalDuration };
}

// Main test function
export default function () {
    const zone = getRandomZone();
    
    // Randomly choose test scenario based on weights
    const scenario = Math.random();
    
    if (scenario < 0.3) {
        // 30% - Complete RSP flow
        completeRspFlow(zone);
    } else if (scenario < 0.5) {
        // 20% - Individual operations
        const euiccId = generateEuiccId();
        registerEuicc(zone, euiccId);
        sleep(0.1);
        createIsdp(zone, euiccId);
    } else if (scenario < 0.7) {
        // 20% - Profile operations
        const profileId = generateProfileId();
        prepareProfile(zone, profileId);
        sleep(0.1);
        keyEstablishment(zone);
    } else if (scenario < 0.9) {
        // 20% - Status checks across entity types
        const entityTypes = ['smdp', 'smsr', 'euicc'];
        entityTypes.forEach(entityType => {
            checkStatus(zone, entityType);
            sleep(0.05);
        });
    } else {
        // 10% - Mixed operations
        checkStatus(zone, 'smdp');
        sleep(0.1);
        keyEstablishment(zone);
    }
    
    // Random sleep between iterations (0.1 to 0.5 seconds)
    sleep(Math.random() * 0.4 + 0.1);
}

// Setup function - called once at the beginning
export function setup() {
    console.log('Starting RSP Load Test...');
    console.log(`Testing zones: ${zones.map(z => z.name).join(', ')}`);
    
    // Verify all zones are accessible
    for (const zone of zones) {
        const response = http.get(`${zone.baseUrl}/status/smdp`);
        if (response.status !== 200) {
            console.error(`Zone ${zone.name} is not accessible at ${zone.baseUrl}`);
        } else {
            console.log(`Zone ${zone.name} is accessible`);
        }
    }
    
    return { startTime: Date.now() };
}

// Teardown function - called once at the end
export function teardown(data) {
    const testDuration = Date.now() - data.startTime;
    console.log(`Test completed in ${testDuration/1000} seconds`);
    console.log('RSP Load Test finished');
} 
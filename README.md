# M2M Remote SIM Provisioning Implementation

Eraser: [Documentation](https://app.eraser.io/workspace/ihuLHEN4p22TXWvbk9Th?origin=share)

A comprehensive implementation of Machine-to-Machine Remote SIM Provisioning (M2M RSP) as defined by GSMA SGP.02 specifications, featuring proper cryptographic operations and secure communication channels.

## Overview

This project demonstrates a complete M2M RSP ecosystem with the following components:
- SM-DP (Subscription Manager - Data Preparation)
- SM-SR (Subscription Manager - Secure Routing)
- eUICC (embedded Universal Integrated Circuit Card)
- Root CA for certificate management

The implementation follows the GSMA SGP.02 standard with:
- TLS security for SM-DP to SM-SR communication
- PSK-TLS security for SM-SR to eUICC communication
- ECDH key establishment for mutual authentication
- Profile encryption, installation, and enabling

## Process Flow

The M2M RSP implementation follows this secure process flow:

1. **eUICC Registration at SM-SR**
   - eUICC sends EIS (eUICC Information Set) to SM-SR
   - SM-SR verifies the eUICC and generates PSK
   - SM-SR returns PSK and SM-SR ID to eUICC
   - Establishes secure PSK-TLS channel for future communications

2. **ISD-P Creation**
   - SM-SR creates an ISD-P (Issuer Security Domain - Profile) on the eUICC
   - ISD-P serves as a secure container for profile storage
   - SM-SR assigns a unique AID (Application ID) to the ISD-P
   - SM-SR updates the EIS with new ISD-P information

3. **Key Establishment with Mutual Authentication**
   - SM-DP and eUICC perform ECDH key exchange via SM-SR
   - Both parties authenticate each other through the process
   - Shared secret established for secure profile transmission
   - Session keys derived for encryption and MAC verification

4. **Profile Download and Installation**
   - SM-DP prepares the profile with necessary credentials and applications
   - Profile is encrypted and sent to SM-SR over TLS channel
   - SM-SR forwards the encrypted profile to eUICC over PSK-TLS
   - eUICC decrypts and installs the profile in the designated ISD-P
   - Profile verified and installation confirmed

5. **Profile Enabling**
   - SM-SR sends profile enabling command to eUICC over PSK-TLS
   - eUICC activates the installed profile
   - Profile status updated to "enabled"
   - Process completion confirmed

## Security Implementation

### Communication Channels

- **SM-DP ↔ SM-SR**: TLS with certificates issued by Root CA
- **SM-SR ↔ eUICC**: PSK-TLS with pre-shared key established during registration

### Cryptographic Components

- **Certificate Management**: Self-signed Root CA issuing certificates
- **ECDH Key Agreement**: Using NIST P-256 curve for key establishment
- **PSK-TLS**: Custom implementation for secure communication with eUICC
- **Profile Encryption**: AES-CBC with HMAC for integrity verification
- **Key Derivation**: NIST SP 800-56C Rev 2 KDF for secure key derivation

## Project Structure

```
m2m-benchmark/
│
├── certs/              # Certificate management
│   ├── root_ca.py      # Root CA implementation
│   └── __init__.py
│
├── crypto/             # Cryptographic operations
│   ├── ecdh.py         # ECDH key agreement
│   ├── kdf.py          # NIST SP 800-56C Rev 2 KDF
│   ├── psk_tls.py      # PSK-TLS implementation
│   ├── scp03t.py       # SCP03t implementation
│   └── __init__.py
│
├── entities/           # RSP entities
│   ├── euicc.py        # eUICC implementation
│   ├── sm_dp.py        # SM-DP implementation
│   ├── sm_sr.py        # SM-SR implementation
│   └── __init__.py
│
├── utils/              # Utilities
│   ├── timing.py       # Performance measurement
│   ├── debug.py        # System diagnostics
│   └── __init__.py
│
├── main.py             # Main application
├── run_benchmark_report.py  # Benchmark and report generation
└── generate_report.py  # PDF report generator
```

## M2M RSP Entities

1. **Root CA**
   - Issues certificates for SM-DP and SM-SR
   - Serves as the trust anchor for the system

2. **SM-DP (Subscription Manager - Data Preparation)**
   - Prepares subscription profiles with needed parameters (IMSI, Ki, OPc)
   - Communicates with SM-SR over TLS using certificates
   - Implements ECDH key establishment with eUICC for mutual authentication
   - Encrypts and securely transmits profiles to SM-SR

3. **SM-SR (Subscription Manager - Secure Routing)**
   - Routes messages between SM-DP and eUICC
   - Manages eUICC registration and PSK establishment
   - Creates and manages ISD-P containers on eUICC
   - Handles profile delivery and enabling commands over PSK-TLS

4. **eUICC (embedded Universal Integrated Circuit Card)**
   - Generates and stores cryptographic keys
   - Establishes secure PSK-TLS channel with SM-SR
   - Creates ISD-P secure containers for profiles
   - Securely installs and enables profiles

## Running the Application

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the application:
   ```
   python main.py
   ```

The application demonstrates the complete M2M RSP process with detailed timing information for each step.

## Benchmarking and Reporting

To generate a performance report of the process:

```
python run_benchmark_report.py
```

This will:
1. Run the M2M RSP demo process
2. Collect timing data for each step
3. Generate a PDF report with performance metrics
4. Provide diagnostics for any failed steps

## Performance Considerations

The implementation includes timing measurements for critical operations:
- Key generation and certificate issuance
- Profile preparation and encryption
- Communication between components
- Profile installation and enabling

On average, a complete RSP process takes 30-60 seconds, with the following breakdown:
- Registration: ~2 seconds
- ISD-P Creation: ~2 seconds
- Key Establishment: ~4 seconds
- Profile Preparation: ~20 seconds
- Profile Installation: ~2 seconds
- Profile Enabling: ~10 seconds

## Security Considerations

- In a production environment, proper certificate validation should be implemented
- The PSK should be delivered securely to the eUICC
- Additional security measures like secure storage of keys should be included
- Key rotation and certificate revocation should be implemented
- Timeouts and fallback mechanisms are implemented for process reliability

# TLS Load Testing with k6

This project contains a load testing script for TLS-enabled API endpoints using Grafana k6. The script is designed to identify bottlenecks in the system by measuring response times of various operations.

## Features

- TLS support with self-signed certificates
- Multiple test scenarios (infrastructure, performance, stress testing)
- Bottleneck detection and reporting
- Comprehensive metrics collection

## Prerequisites

- [k6](https://k6.io/docs/getting-started/installation/) installed on your system
- Docker and Docker Compose for running the TLS proxy

## Getting Started

### 1. Start the TLS Proxy

The TLS proxy provides HTTPS endpoints for your services. Start it with:

```bash
cd tls-proxy
docker-compose up -d
```

### 2. Run the Load Test

To run the load test script:

```bash
k6 run tls-benchmark.js
```

For saving the results to a JSON file:

```bash
k6 run --out json=results.json tls-benchmark.js
```

## Test Scenarios

The script includes three test scenarios:

1. **Infrastructure Test** - Verifies all services are responsive
2. **Performance Test** - Simulates realistic user flows with ramping VUs
3. **Stress Test** - Focuses on suspected bottleneck operations

## Bottleneck Detection

Operations that exceed the 5-second threshold are flagged as bottlenecks. The test generates a report showing:

- Count of bottleneck occurrences by operation
- Response time statistics
- Failure rates

## Customization

Edit the script to adjust:

- Endpoint URLs and paths
- Bottleneck threshold (default: 5 seconds)
- VU (Virtual User) counts and test durations
- Test scenarios and stages

## Analyzing Results

After running the test, review:

1. The summary output in the console
2. The JSON results file if you used the `--out json` flag
3. Import JSON results into Grafana for visualization

## Troubleshooting

If you encounter TLS issues, ensure your certificates are properly configured in the TLS proxy. 
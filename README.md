# M2M Remote SIM Provisioning Protocol Implementation

A Python implementation of the GSMA M2M Remote SIM Provisioning (RSP) Protocol for embedded Universal Integrated Circuit Cards (eUICCs). This project simulates the key phases of the M2M RSP protocol with timing metrics for benchmarking purposes.

## Overview

M2M Remote SIM Provisioning enables the remote provisioning and management of embedded SIM cards (eUICC) in IoT and M2M devices. This implementation follows the GSMA specification and includes the following protocol phases:

1. **ISDP Creation**: Creation of the Issuer Security Domain - Profile (ISD-P) on the eUICC
2. **Key Establishment**: Secure key exchange between SM-DP and eUICC 
3. **Profile Download & Installation**: Secure transmission and installation of the operator profile using ES8 interface and SCP03t

## Repository Structure

```
├── app.py                             # Main application and common classes
├── isdp_creation.py                   # ISD-P Creation process implementation
├── key_establishment.py               # Key Establishment Protocol implementation
├── profile_download_installation.py   # Profile Download & Installation implementation
├── benchmark.py                       # Performance benchmarking utilities
├── rsp_benchmark_results.txt          # Sample benchmark results
└── README.md                          # This file
```

## Protocol Entities

The implementation simulates the following entities:

- **SM-DP** (Subscription Manager - Data Preparation): Securely prepares profiles and manages their download to eUICCs
- **SM-SR** (Subscription Manager - Secure Routing): Routes messages securely between SM-DP and eUICC
- **eUICC** (embedded Universal Integrated Circuit Card): The secure element in the device that receives and installs profiles

## Security Features

The implementation uses:
- ECDSA for digital signatures
- ECDH for key agreement
- NIST SP 800-56C Rev 2 for key derivation functions
- Secure Channel Protocol 03 for APDU transmission (SCP03t)
- ES8 interface for profile management

## Dependencies

- Python 3.7+
- cryptography
- secrets
- hashlib
- statistics (for benchmarking)

Install dependencies using:
```bash
pip install cryptography
```

## Usage

### Running the Protocol

```bash
python app.py
```

This will execute all three phases of the protocol in sequence:
1. ISDP Creation 
2. Key Establishment
3. Profile Download and Installation

### Running Benchmarks

```bash
python benchmark.py
```

This will run the protocol for multiple iterations and report average timing statistics for each phase and operation. Results will be saved to `rsp_benchmark_results.txt`.

## Protocol Flow

1. **ISDP Creation**:
   - SM-DP allocates resources for the profile
   - SM-DP prepares and sends ISDP creation request
   - eUICC processes the request and creates the ISDP
   - SM-DP confirms and registers the ISDP

2. **Key Establishment**:
   - Certificate exchange between SM-DP and eUICC
   - Random challenge generation
   - Ephemeral key generation and exchange
   - Shared secret computation and key derivation

3. **Profile Download and Installation**:
   - SM-DP prepares the profile package
   - SM-DP creates the Bound Profile Package (BPP) using SCP03t
   - Profile is downloaded in segments using ES8 interface and SCP03t
   - eUICC installs and enables the downloaded profile

## Implementation Notes

This is a simulation implementation focused on benchmarking the protocol performance. It includes:

- Timing measurements for each protocol phase and operation
- Simulated cryptographic operations with realistic timing characteristics
- End-to-end protocol flow according to GSMA specifications

The implementation simplifies some aspects of the real protocol while maintaining the core security and procedural elements.

## Benchmark Results

Sample benchmark results from 100 iterations show:

- **Average Total Protocol Time**: ~0.46 seconds
- **ISDP Creation**: ~0.46 seconds
- **Key Establishment**: ~0.41 seconds
- **Profile Download & Installation**: ~0.41 seconds

Most time-consuming operations:
1. Profile Installation in ISD-P: ~0.19 seconds
2. Segmented Profile Download: ~0.16 seconds
3. Profile Enabling: ~0.05 seconds

For detailed benchmark results, see the `rsp_benchmark_results.txt` file.

## License

MIT License

## Contributing

Contributions to improve the protocol implementation or benchmarking methodology are welcome. 
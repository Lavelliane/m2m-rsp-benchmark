# M2M Remote SIM Provisioning Implementation

A comprehensive implementation of Machine-to-Machine Remote SIM Provisioning (M2M RSP) as defined by GSMA SGP.02 specifications, featuring proper cryptographic operations and secure communication channels.

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
│   └── __init__.py
│
└── main.py             # Main application
```

## Cryptographic Components

1. **Certificate Management**
   - Self-signed Root CA issuing certificates for SM-DP and SM-SR

2. **TLS Communication**
   - Secure communication between SM-DP and SM-SR using certificates

3. **PSK-TLS Communication**
   - Secure communication between SM-SR and eUICC using pre-shared keys

4. **ECDH Key Agreement**
   - Elliptic Curve Diffie-Hellman for secure key establishment
   - Uses NIST P-256 curve as specified in GSMA SGP.02

5. **NIST KDF**
   - Key Derivation Function based on NIST SP 800-56C Rev 2
   - Used to derive encryption and MAC keys from shared secrets

## M2M RSP Entities

1. **Root CA**
   - Issues certificates for SM-DP and SM-SR
   - Serves as the trust anchor for the system

2. **SM-DP (Subscription Manager - Data Preparation)**
   - Prepares subscription profiles
   - Communicates with SM-SR over TLS
   - Implements key establishment protocol with eUICC
   - Provides profile download functionality

3. **SM-SR (Subscription Manager - Secure Routing)**
   - Routes messages between SM-DP and eUICC
   - Communicates with SM-DP over TLS
   - Communicates with eUICC over PSK-TLS
   - Manages ISD-P creation and profile installation

4. **eUICC (embedded Universal Integrated Circuit Card)**
   - Receives and installs profiles
   - Communicates with SM-SR over PSK-TLS
   - Implements key establishment protocol
   - Manages installed profiles and ISD-Ps

## Protocol Implementation

The implementation follows the GSMA SGP.02 specifications for M2M RSP:

1. **PSK Establishment**
   - Initial registration of eUICC with SM-SR
   - Establishment of pre-shared key for secure communication

2. **ISD-P Creation**
   - Creation of Issuer Security Domain - Profile on the eUICC
   - Resource allocation and preparation for profile installation

3. **Key Establishment**
   - ECDH key agreement between SM-DP and eUICC through SM-SR
   - Generation of session keys for secure channel protocol

4. **Profile Download and Installation**
   - Secure download of profile from SM-DP to eUICC through SM-SR
   - Profile installation in the ISD-P on the eUICC

## Running the Application

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the application:
   ```
   python main.py
   ```

The application will:
1. Start the Root CA, SM-DP, SM-SR, and eUICC
2. Register the eUICC with the SM-SR
3. Prepare a profile at the SM-DP
4. Establish secure keys using ECDH
5. Install the profile on the eUICC
6. Create an ISD-P for the profile
7. Display the status of all components

## Performance Measurement

The application includes a timing utility for measuring the performance of cryptographic operations and protocol steps. The timing data is displayed during execution.

## Security Considerations

- In a production environment, proper certificate validation should be implemented
- The PSK should be delivered securely to the eUICC
- Additional security measures like mutual authentication should be included
- Key rotation and certificate revocation should be implemented 
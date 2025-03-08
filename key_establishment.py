import binascii
import time
import secrets
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

# Import classes from app.py
from app import TimingContext, SMDP, EUICC, SMSR

def simulate_key_establishment(entities, silent=False):
    """
    Simulate the complete key establishment protocol
    
    Args:
        entities: Tuple containing (euicc, smdp, smsr, isdp_id) from ISDP Creation
        silent: If True, suppress console output (for benchmarking)
    """
    # Unpack entities
    if isinstance(entities, tuple) and len(entities) >= 4:
        euicc, smdp, smsr, isdp_id = entities[:4]
    else:
        if not silent:
            print("Error: Invalid entities provided to Key Establishment")
        return None
    
    if not silent:
        print(f"\n=== Starting Key Establishment Protocol for ISDP {isdp_id} ===\n")
    
    # Use the established entities from ISDP Creation
    # No need to reinitialize the entities
    
    if not silent:
        print("\n--- Phase 1: Certificate Exchange ---\n")
    
    # SM-DP sends certificate to eUICC
    with TimingContext("Certificate Exchange"):
        cert_dp = smdp.cert
        euicc.verify_cert_dp(cert_dp)
        euicc.store_pk_dp(cert_dp)
    
    if not silent:
        print("\n--- Phase 2: Random Challenge Generation ---\n")
    
    # SM-DP generates and sends random challenge
    with TimingContext("Random Challenge Handling"):
        rc = smdp.generate_random_challenge()
        euicc.store_random_challenge(rc)
    
    if not silent:
        print("\n--- Phase 3: Ephemeral Key Generation ---\n")
    
    # eUICC generates ephemeral key pair
    epk_euicc_bytes = euicc.generate_keys()
    
    # SM-DP generates ephemeral key pair
    epk_dp_bytes = smdp.generate_keys()
    
    # SM-DP signs ephemeral public key and random challenge
    with TimingContext("SM-DP Signature of ephemeral key"):
        # Include the ISDP ID in the signed data to bind the keys to this specific ISDP
        isdp_id_bytes = isdp_id.encode() if isinstance(isdp_id, str) else isdp_id
        data_to_sign = epk_dp_bytes + rc + isdp_id_bytes
        sigma_dp = smdp.sign_data(data_to_sign)
    
    # SM-DP sends ephemeral public key and signature to eUICC
    message = {
        "epk_dp": epk_dp_bytes,
        "sigma_dp": sigma_dp,
        "isdp_id": isdp_id
    }
    
    # Use ES8 interface through SM-SR for communication
    with TimingContext("ES8 Communication (SM-DP to eUICC)"):
        routed_message = smsr.route_message("SM-DP", "eUICC", message)
    
    # eUICC verifies signature
    with TimingContext("eUICC Signature Verification"):
        # Include the ISDP ID in verification
        isdp_id_bytes = isdp_id.encode() if isinstance(isdp_id, str) else isdp_id
        data_to_verify = routed_message["epk_dp"] + rc + isdp_id_bytes
        verification_result = euicc.verify_signature(
            routed_message["sigma_dp"],
            data_to_verify
        )
        
        if not verification_result:
            if not silent:
                print("Signature verification failed")
            return False
    
    if not silent:
        print("\n--- Phase 4: Shared Secret and Key Derivation (SCP03t) ---\n")
    
    # eUICC computes shared secret and derives keys
    with TimingContext("SCP03t Key Establishment"):
        euicc.compute_shared_secret(epk_dp_bytes)
        euicc.derive_keys()
    
    # eUICC generates receipt
    receipt = euicc.generate_receipt()
    
    # eUICC sends ephemeral public key and receipt to SM-DP
    response = {
        "epk_euicc": epk_euicc_bytes,
        "receipt": receipt,
        "isdp_id": isdp_id
    }
    
    # Route response through SM-SR using ES8 interface
    with TimingContext("ES8 Communication (eUICC to SM-DP)"):
        routed_response = smsr.route_message("eUICC", "SM-DP", response)
    
    # SM-DP computes shared secret
    smdp.compute_shared_secret(routed_response["epk_euicc"])
    
    # SM-DP verifies receipt
    smdp.verify_receipt(routed_response["receipt"], None)
    
    if not silent:
        print("\n=== Key Establishment Protocol for SCP03t Completed ===\n")
        print("SCP03t Keys established:")
        print(f"  eUICC Ku (MAC): {binascii.hexlify(euicc.ku).decode()[:16]}...")
        print(f"  eUICC Ke (ENC): {binascii.hexlify(euicc.ke).decode()[:16]}...")
        print(f"  eUICC Km (DEK): {binascii.hexlify(euicc.km).decode()[:16]}...")
    
    return euicc, smdp, smsr  # Return the entities for use in subsequent phases 
"""
M2M Remote SIM Provisioning Key Establishment Protocol Implementation
Protocol entities: SM-DP (Subscription Manager - Data Preparation),
                  SM-SR (Subscription Manager - Secure Routing),
                  eUICC (embedded Universal Integrated Circuit Card)

Using:
- ECDSA for digital signatures
- ECDH for key agreement
- NIST SP 800-56C Rev 2 for key derivation functions
- Timing mechanisms for benchmarking
"""

import time
import secrets
import hashlib
import binascii
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
from datetime import datetime, timedelta

# Configuration parameters
EC_CURVE = ec.SECP256R1()  # P-256 curve
HASH_ALGORITHM = hashes.SHA256()
RC_SIZE = 32  # 32-bit random challenge


class TimingContext:
    """Context manager for timing operations"""
    
    def __init__(self, name):
        self.name = name
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        print(f"{self.name}: {self.duration:.6f} seconds")


class Certificate:
    """Simplified certificate implementation"""
    
    def __init__(self, subject_name, private_key=None):
        self.subject_name = subject_name
        
        # Generate a new private key if none provided
        if private_key is None:
            self.private_key = ec.generate_private_key(EC_CURVE, default_backend())
        else:
            self.private_key = private_key
            
        self.public_key = self.private_key.public_key()
        self.cert = self._generate_certificate()
        
    def _generate_certificate(self):
        """Generate a self-signed certificate"""
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, self.subject_name)
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            self.public_key
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)
        ).sign(self.private_key, HASH_ALGORITHM, default_backend())
        
        return cert
    
    def get_public_key(self):
        """Extract public key from certificate"""
        return self.cert.public_key()
    
    def verify_signature(self, signature, data):
        """Verify a signature using certificate's public key"""
        try:
            self.get_public_key().verify(
                signature,
                data,
                ec.ECDSA(HASH_ALGORITHM)
            )
            return True
        except InvalidSignature:
            return False
    
    def pem(self):
        """Return PEM encoded certificate"""
        return self.cert.public_bytes(serialization.Encoding.PEM)


class NIST_KDF:
    """Implementation of NIST SP 800-56C Rev 2 KDF"""
    
    @staticmethod
    def derive_key(shared_secret, key_len, label, context=None):
        """
        Key Derivation Function following NIST SP 800-56C Rev 2
        using HKDF (Hash-based Key Derivation Function)
        
        Args:
            shared_secret: The shared secret from key agreement
            key_len: Length of the key to be derived in bytes
            label: Label string for the derivation
            context: Optional context information
            
        Returns:
            Derived key material
        """
        if context is None:
            context = b""
            
        label_bytes = label.encode('utf-8') if isinstance(label, str) else label
        
        # Two-step KDF as described in NIST SP 800-56C Rev 2
        # Step 1: Extract using salt as all zeros (simplified)
        salt = b'\x00' * 32  # Using 32 bytes of zeros as salt
        
        with TimingContext("KDF Extract Phase"):
            prk = HKDF(
                algorithm=HASH_ALGORITHM,
                length=32,  # Output length of extraction phase
                salt=salt,
                info=None,
                backend=default_backend()
            ).derive(shared_secret)
        
        # Step 2: Expand using label and context
        info = label_bytes + b'\x00' + context
        
        with TimingContext("KDF Expand Phase"):
            key_material = HKDF(
                algorithm=HASH_ALGORITHM,
                length=key_len,
                salt=None,
                info=info,
                backend=default_backend()
            ).derive(prk)
        
        return key_material


class SMDP:
    """Subscription Manager - Data Preparation entity"""
    
    def __init__(self):
        with TimingContext("SM-DP Certificate Generation"):
            self.cert = Certificate("SM-DP")
        self.private_key = self.cert.private_key
        self.sk_dp = None  # Static private key
        self.ek_dp = None  # Ephemeral private key
        self.epk_dp = None  # Ephemeral public key
        self.rc = None  # Random challenge
        self.shared_secret = None  # ECDH shared secret
        self.receipt = None  # Receipt from eUICC
    
    def generate_keys(self):
        """Generate ephemeral key pair for ECDH"""
        with TimingContext("SM-DP Ephemeral Key Generation"):
            self.ek_dp = ec.generate_private_key(EC_CURVE, default_backend())
            self.epk_dp = self.ek_dp.public_key()
        
        # Convert to bytes for transmission
        self.epk_dp_bytes = self.epk_dp.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
        return self.epk_dp_bytes
    
    def generate_random_challenge(self):
        """Generate random challenge for eUICC"""
        with TimingContext("SM-DP Random Challenge Generation"):
            self.rc = secrets.token_bytes(RC_SIZE)
        return self.rc
    
    def sign_data(self, data):
        """Sign data using SM-DP private key"""
        with TimingContext("SM-DP Signature Generation"):
            signature = self.private_key.sign(
                data,
                ec.ECDSA(HASH_ALGORITHM)
            )
        return signature
    
    def compute_shared_secret(self, epk_euicc_bytes):
        """Compute ECDH shared secret with eUICC's ephemeral public key"""
        try:
            epk_euicc = ec.EllipticCurvePublicKey.from_encoded_point(
                EC_CURVE,
                epk_euicc_bytes
            )
            
            with TimingContext("SM-DP Shared Secret Computation"):
                self.shared_secret = self.ek_dp.exchange(ec.ECDH(), epk_euicc)
            
            return True
        except Exception as e:
            print(f"Error computing shared secret: {e}")
            return False
    
    def verify_receipt(self, receipt, shs):
        """Verify receipt from eUICC"""
        with TimingContext("SM-DP Receipt Verification"):
            # In a real implementation, this would be more complex
            # and would use cryptographic verification
            self.receipt = receipt
            return True


class EUICC:
    """Embedded Universal Integrated Circuit Card entity"""
    
    def __init__(self):
        with TimingContext("eUICC Certificate Generation"):
            self.cert = Certificate("eUICC")
        self.private_key = self.cert.private_key
        self.sk_euicc = None  # Static private key
        self.ek_euicc = None  # Ephemeral private key
        self.epk_euicc = None  # Ephemeral public key
        self.shared_secret = None  # ECDH shared secret
        self.pk_dp = None  # SM-DP public key
        self.rc = None  # Random challenge received
        
        # Keys derived from shared secret
        self.shs = None  # Shared secret
        self.ku = None  # Key for usage
        self.ke = None  # Key for encryption
        self.km = None  # Key for MAC
    
    def verify_cert_dp(self, cert_dp):
        """Verify SM-DP certificate"""
        with TimingContext("eUICC Certificate Verification"):
            # In a real implementation, this would check against a trusted CA
            # and validate the certificate chain
            return True
    
    def store_pk_dp(self, cert_dp):
        """Store SM-DP public key from certificate"""
        # Extract public key from certificate
        self.pk_dp = cert_dp.get_public_key()
        return True
    
    def verify_signature(self, signature, data, public_key=None):
        """Verify signature from SM-DP"""
        if public_key is None:
            public_key = self.pk_dp
            
        with TimingContext("eUICC Signature Verification"):
            try:
                public_key.verify(
                    signature,
                    data,
                    ec.ECDSA(HASH_ALGORITHM)
                )
                return True
            except InvalidSignature:
                return False
    
    def store_random_challenge(self, rc):
        """Store random challenge from SM-DP"""
        self.rc = rc
        return True
    
    def generate_keys(self):
        """Generate ephemeral key pair for ECDH"""
        with TimingContext("eUICC Ephemeral Key Generation"):
            self.ek_euicc = ec.generate_private_key(EC_CURVE, default_backend())
            self.epk_euicc = self.ek_euicc.public_key()
        
        # Convert to bytes for transmission
        self.epk_euicc_bytes = self.epk_euicc.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
        return self.epk_euicc_bytes
    
    def sign_data(self, data):
        """Sign data using eUICC private key"""
        with TimingContext("eUICC Signature Generation"):
            signature = self.private_key.sign(
                data,
                ec.ECDSA(HASH_ALGORITHM)
            )
        return signature
    
    def compute_shared_secret(self, epk_dp_bytes):
        """Compute ECDH shared secret with SM-DP's ephemeral public key"""
        try:
            epk_dp = ec.EllipticCurvePublicKey.from_encoded_point(
                EC_CURVE,
                epk_dp_bytes
            )
            
            with TimingContext("eUICC Shared Secret Computation"):
                self.shared_secret = self.ek_euicc.exchange(ec.ECDH(), epk_dp)
            
            # Compute SHS = sk_euicc * pk_dp (simplified)
            self.shs = self.shared_secret
            
            return True
        except Exception as e:
            print(f"Error computing shared secret: {e}")
            return False
    
    def derive_keys(self):
        """Derive keys using KDF"""
        if not self.shared_secret:
            print("Shared secret not established")
            return False
        
        with TimingContext("eUICC Key Derivation"):
            # Derive three keys from shared secret
            self.ku = NIST_KDF.derive_key(
                self.shared_secret, 
                32, 
                "usage_key", 
                b"unique_label1"
            )
            
            self.ke = NIST_KDF.derive_key(
                self.shared_secret, 
                32, 
                "encryption_key", 
                b"unique_label2"
            )
            
            self.km = NIST_KDF.derive_key(
                self.shared_secret, 
                32, 
                "mac_key", 
                b"unique_label3"
            )
        
        return True
    
    def generate_receipt(self):
        """Generate receipt for SM-DP"""
        with TimingContext("eUICC Receipt Generation"):
            if not all([self.ku, self.ke, self.km, self.rc]):
                print("Missing data for receipt generation")
                return None
                
            # In a real implementation, this would create a cryptographic receipt
            # that proves the eUICC has derived the correct keys
            receipt_data = b"receipt_" + self.rc
            receipt_signature = self.sign_data(receipt_data)
            receipt = {
                "data": receipt_data,
                "signature": receipt_signature
            }
            
        return receipt


class SMSR:
    """Subscription Manager - Secure Routing entity"""
    
    def __init__(self):
        with TimingContext("SM-SR Certificate Generation"):
            self.cert = Certificate("SM-SR")
        self.private_key = self.cert.private_key
    
    def route_message(self, source, destination, message):
        """Route message between SM-DP and eUICC"""
        with TimingContext(f"SM-SR Routing: {source} to {destination}"):
            # In a real implementation, this would handle secure routing
            # between the SM-DP and eUICC
            return message


if __name__ == "__main__":
    # Import modules here to avoid circular imports
    from key_establishment import simulate_key_establishment
    from isdp_creation import isdp_creation
    from profile_download_installation import profile_download_and_installation
    
    with TimingContext("Complete Protocol Execution"):
        # Execute key establishment
        print("\n=== PHASE I: KEY ESTABLISHMENT ===\n")
        entities = simulate_key_establishment()
        
        if entities:
            euicc, smdp, smsr = entities
            
            # Execute ISDP creation with the established entities
            print("\n=== PHASE II: ISDP CREATION ===\n")
            isdp_result = isdp_creation(entities)
            
            if isdp_result and len(isdp_result) >= 4:
                euicc, smdp, smsr, isdp_id = isdp_result
                
                # Execute profile download and installation with established entities and ISDP
                print("\n=== PHASE III: PROFILE DOWNLOAD AND INSTALLATION ===\n")
                profile_download_and_installation((euicc, smdp, smsr, isdp_id))
            else:
                print("ISDP Creation failed, aborting protocol")
        else:
            print("Key Establishment failed, aborting protocol")
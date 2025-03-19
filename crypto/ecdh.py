"""
ECDH (Elliptic Curve Diffie-Hellman) key agreement implementation
"""

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import os
import time
import hashlib
from utils.timing import TimingContext

class ECDH:
    @staticmethod
    def generate_keypair():
        """
        Generate an ECDH key pair (private key and serialized public key)
        
        Returns:
            tuple: (private_key, serialized_public_key_bytes)
        """
        with TimingContext("ECDH Key Generation"):
            private_key = ec.generate_private_key(
                curve=ec.SECP256R1()
            )
            
            # Serialize public key to raw format
            public_key_bytes = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint
            )
            
            return private_key, public_key_bytes
    
    @staticmethod
    def compute_shared_secret(private_key, peer_public_key_bytes):
        """
        Compute a shared secret using ECDH key agreement
        
        Args:
            private_key: Local private key
            peer_public_key_bytes: Serialized public key bytes from peer
            
        Returns:
            bytes: The shared secret
        """
        with TimingContext("ECDH Shared Secret Computation"):
            # Convert the peer's public key bytes to a public key object
            peer_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
                curve=ec.SECP256R1(),
                data=peer_public_key_bytes
            )
            
            # Compute the shared secret
            shared_key = private_key.exchange(
                ec.ECDH(),
                peer_public_key
            )
            
            return shared_key
    
    @staticmethod
    def generate_random_challenge():
        """
        Generate a random challenge for authentication
        
        Returns:
            bytes: Random challenge
        """
        return os.urandom(16)
    
    @staticmethod
    def derive_profile_keys(shared_secret, profile_info, euicc_info, smdp_info):
        """
        Derive keys for profile protection using the shared secret
        
        Args:
            shared_secret (bytes): The ECDH shared secret
            profile_info (dict): Profile information (ICCID, etc.)
            euicc_info (dict): eUICC information (EID, etc.)
            smdp_info (dict): SM-DP information
            
        Returns:
            dict: Dict containing encryption key (ke), MAC key (km), and key protection key (ku)
        """
        # Import here to avoid circular imports
        from crypto.kdf import NIST_KDF
        
        # Convert info objects to bytes
        profile_bytes = profile_info.get("iccid", "").encode()
        euicc_bytes = euicc_info.get("eid", "").encode()
        smdp_bytes = smdp_info.get("smdpId", "").encode()
        
        # Combine all info as context
        additional_info = b'|'.join([profile_bytes, euicc_bytes, smdp_bytes])
        
        # Derive encryption key (Ke)
        ke = NIST_KDF.derive_key(
            shared_secret=shared_secret,
            key_length=32,  # 256 bits
            key_type="encryption_key",
            additional_info=additional_info
        )
        
        # Derive MAC key (Km)
        km = NIST_KDF.derive_key(
            shared_secret=shared_secret,
            key_length=32,  # 256 bits
            key_type="mac_key",
            additional_info=additional_info
        )
        
        # Derive key protection key (Ku)
        ku = NIST_KDF.derive_key(
            shared_secret=shared_secret,
            key_length=32,  # 256 bits
            key_type="key_protection_key",
            additional_info=additional_info
        )
        
        # Return all derived keys
        return {
            "ke": ke,
            "km": km,
            "ku": ku
        }
    
    @staticmethod
    def generate_receipt(km, device_id, operator_id, nonce):
        """
        Generate a receipt for key confirmation
        
        Args:
            km (bytes): MAC key
            device_id (bytes): Device identifier
            operator_id (bytes): Operator identifier
            nonce (bytes): Random nonce for freshness
            
        Returns:
            bytes: Receipt (HMAC)
        """
        # Combine data for the receipt
        receipt_data = device_id + operator_id + nonce
        
        # Calculate HMAC using SHA-256
        hmac_obj = hashlib.new('sha256', km)
        hmac_obj.update(receipt_data)
        receipt = hmac_obj.digest()
        
        return receipt 
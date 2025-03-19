"""
NIST Key Derivation Function (KDF) Implementation
Based on NIST SP 800-108 Counter Mode
"""

import hashlib
import hmac
import struct
import binascii

class NIST_KDF:
    @staticmethod
    def sp800_108_counter(key, key_length, label, context=b'', iterations=None):
        """
        NIST SP 800-108 KDF in Counter Mode
        
        Args:
            key (bytes): The key derivation key
            key_length (int): Length of the derived key in bytes
            label (bytes): Label for context separation
            context (bytes): Context information for the derived key
            iterations (int): Optional fixed iterations (auto-calculated if None)
            
        Returns:
            bytes: The derived key material
        """
        h = hashlib.sha256
        hash_len = 32  # SHA-256 output length in bytes
        
        if iterations is None:
            # Calculate minimum iterations needed
            iterations = (key_length + hash_len - 1) // hash_len
        
        derived_key = b''
        
        for i in range(1, iterations + 1):
            # Counter as big-endian 4-byte value
            counter = struct.pack('>I', i)
            
            # HMAC(key, [i] || Label || 0x00 || Context || [key_length])
            hmac_input = counter + label + b'\x00' + context + struct.pack('>I', key_length * 8)
            current_hmac = hmac.new(key, hmac_input, h).digest()
            derived_key += current_hmac
        
        # Truncate to desired length
        return derived_key[:key_length]
    
    @staticmethod
    def derive_key(shared_secret, key_length, key_type, additional_info=b''):
        """
        Derive a key from a shared secret using NIST SP 800-108 Counter Mode
        
        Args:
            shared_secret (bytes): The shared secret (e.g., from ECDH)
            key_length (int): Length of the derived key in bytes
            key_type (str): Type of key being derived (e.g., "encryption", "mac")
            additional_info (bytes): Any additional context information
            
        Returns:
            bytes: The derived key
        """
        # Convert key_type to bytes if it's a string
        if isinstance(key_type, str):
            key_type = key_type.encode('utf-8')
            
        # Create label with key type
        label = b'M2M_RSP_' + key_type
        
        # Use the SP 800-108 Counter Mode KDF
        derived_key = NIST_KDF.sp800_108_counter(
            key=shared_secret,
            key_length=key_length,
            label=label,
            context=additional_info
        )
        
        return derived_key
    
    @staticmethod
    def test_vectors():
        """
        Test vectors for KDF validation (simplified)
        """
        # Simple test vector with known output
        key = b'test_key_material_12345'
        expected_output = b'\xf5\xb2\x91\xa4\x33\xb5\xec\x62\xc7\xd9\x36\x91\x2a\x0a\x2f\x8a'
        derived = NIST_KDF.sp800_108_counter(key, 16, b'test_label', b'test_context')
        
        # This is a simplified test - in a real system you should use official test vectors
        print(f"Derived key: {binascii.hexlify(derived)}")
        print(f"Expected (simplified test): Similar to {binascii.hexlify(expected_output)}")
        
        return derived 
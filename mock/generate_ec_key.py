#!/usr/bin/env python3

import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

def generate_valid_ec_key():
    """Generate a valid SECP256R1 EC key pair and return the public key in Base64 format"""
    
    # Generate a new EC key pair
    private_key = ec.generate_private_key(curve=ec.SECP256R1())
    
    # Get the public key in X9.62 uncompressed format (65 bytes)
    public_key_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    
    # Convert to Base64 for use in k6 script
    public_key_base64 = base64.b64encode(public_key_bytes).decode()
    
    print(f"Generated EC Public Key (Base64): {public_key_base64}")
    print(f"Key length: {len(public_key_bytes)} bytes")
    print(f"First byte (should be 0x04): 0x{public_key_bytes[0]:02x}")
    
    return public_key_base64

if __name__ == "__main__":
    # Generate a few keys for testing
    for i in range(3):
        print(f"\n=== Key {i+1} ===")
        generate_valid_ec_key() 
import os
import json
import base64
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.hmac import HMAC
from utils.timing import TimingContext


class PSK_TLS:
    """
    PSK-TLS implementation for eUICC communication
    Based on RFC 4279 and GSMA SGP.02 specifications
    """
    
    @staticmethod
    def encrypt(data, psk, include_mac=True):
        """
        Encrypt data using PSK in TLS-PSK style
        
        Args:
            data: Data to encrypt (bytes or dict/list to be JSON encoded)
            psk: Pre-shared key (bytes)
            include_mac: Whether to include MAC in the result
            
        Returns:
            Dictionary with IV, ciphertext, and optionally MAC
        """
        with TimingContext("PSK-TLS Encryption"):
            # Convert data to bytes if it's not already
            if isinstance(data, (dict, list)):
                data_bytes = json.dumps(data).encode()
            elif isinstance(data, str):
                data_bytes = data.encode()
            else:
                data_bytes = data
            
            # Verify key length - supports both AES-128 (16 bytes) and AES-256 (32 bytes)
            if len(psk) != 16 and len(psk) != 32:
                raise ValueError(f"Invalid PSK length: {len(psk)} bytes. Must be 16 bytes (AES-128) or 32 bytes (AES-256)")
            
            if len(psk) == 16:
                key_type = "AES-128"
            else:
                key_type = "AES-256"
                
            # Generate a random IV
            iv = os.urandom(16)
            
            # Derive encryption key and MAC key from PSK
            with TimingContext(f"PSK Key Derivation ({key_type})"):
                # In real TLS-PSK, this would use TLS PRF
                # Here we use PBKDF2 as a simplified approach
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,  # 256-bit key
                    salt=iv,
                    iterations=10000,
                )
                encryption_key = kdf.derive(psk)
                
                if include_mac:
                    # Use different context for MAC key
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA256(),
                        length=32,  # 256-bit key
                        salt=iv + b"mac_key",  # Use a different salt instead of info
                        iterations=10000,
                    )
                    mac_key = kdf.derive(psk)
            
            # Pad the data
            padder = padding.PKCS7(algorithms.AES.block_size).padder()
            padded_data = padder.update(data_bytes) + padder.finalize()
            
            # Encrypt with AES-CBC
            with TimingContext(f"{key_type} Encryption"):
                cipher = Cipher(algorithms.AES(encryption_key), modes.CBC(iv))
                encryptor = cipher.encryptor()
                ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            
            result = {
                "iv": base64.b64encode(iv).decode(),
                "data": base64.b64encode(ciphertext).decode(),
                "key_type": key_type  # Include information about the key type used
            }
            
            # Add MAC if requested
            if include_mac:
                with TimingContext("HMAC Generation"):
                    h = HMAC(mac_key, hashes.SHA256())
                    h.update(iv + ciphertext)
                    mac = h.finalize()
                    result["mac"] = base64.b64encode(mac).decode()
            
            return result
    
    @staticmethod
    def decrypt(encrypted_data, psk, verify_mac=True):
        """
        Decrypt data that was encrypted using PSK-TLS style encryption
        
        Args:
            encrypted_data: Dictionary with IV, ciphertext, and optionally MAC
            psk: Pre-shared key (bytes)
            verify_mac: Whether to verify MAC if present
            
        Returns:
            Decrypted data as bytes
        """
        with TimingContext("PSK-TLS Decryption"):
            # Extract IV and ciphertext
            iv = base64.b64decode(encrypted_data.get("iv", ""))
            ciphertext = base64.b64decode(encrypted_data.get("data", ""))
            
            # Verify key length - supports both AES-128 (16 bytes) and AES-256 (32 bytes)
            if len(psk) != 16 and len(psk) != 32:
                raise ValueError(f"Invalid PSK length: {len(psk)} bytes. Must be 16 bytes (AES-128) or 32 bytes (AES-256)")
            
            key_type = "AES-128" if len(psk) == 16 else "AES-256"
            
            # Verify MAC if requested and present
            if verify_mac and "mac" in encrypted_data:
                mac = base64.b64decode(encrypted_data.get("mac", ""))
                
                # Derive MAC key from PSK
                with TimingContext(f"PSK Key Derivation for MAC ({key_type})"):
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA256(),
                        length=32,
                        salt=iv + b"mac_key",  # Use a different salt instead of info
                        iterations=10000,
                    )
                    mac_key = kdf.derive(psk)
                
                # Verify MAC
                with TimingContext("HMAC Verification"):
                    h = HMAC(mac_key, hashes.SHA256())
                    h.update(iv + ciphertext)
                    try:
                        h.verify(mac)
                    except Exception:
                        raise ValueError("MAC verification failed")
            
            # Derive encryption key from PSK
            with TimingContext(f"PSK Key Derivation for Decryption ({key_type})"):
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=iv,
                    iterations=10000,
                )
                encryption_key = kdf.derive(psk)
            
            # Decrypt with AES-CBC
            with TimingContext(f"{key_type} Decryption"):
                cipher = Cipher(algorithms.AES(encryption_key), modes.CBC(iv))
                decryptor = cipher.decryptor()
                decrypted_padded = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Unpad the data
            unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
            decrypted_data = unpadder.update(decrypted_padded) + unpadder.finalize()
            
            return decrypted_data
    
    @staticmethod
    def try_json_decode(data):
        """
        Try to decode data as JSON, return as-is if not JSON
        """
        try:
            if isinstance(data, bytes):
                return json.loads(data.decode())
            return data
        except Exception:
            return data 
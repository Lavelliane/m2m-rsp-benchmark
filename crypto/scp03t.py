"""
SCP03t (Secure Channel Protocol '03' for Transport) Implementation
Based on GlobalPlatform Card Specification Amendment F Version 1.1.2
Used for secure profile download and installation in M2M RSP
"""

import os
import hmac
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from utils.timing import TimingContext

class SCP03t:
    """SCP03t for securing profile download and installation"""
    
    # Class constants
    BLOCK_SIZE = 16  # AES block size in bytes
    
    @staticmethod
    def derive_session_keys(shared_secret, host_id, card_id, host_challenge, card_challenge):
        """
        Derive session keys for SCP03t
        
        Args:
            shared_secret (bytes): Shared secret from ECDH
            host_id (bytes): Host identification (SM-DP/SM-SR)
            card_id (bytes): Card identification (eUICC)
            host_challenge (bytes): Random challenge from host
            card_challenge (bytes): Random challenge from card
            
        Returns:
            dict: Session keys (S-ENC, S-MAC, S-RMAC)
        """
        with TimingContext("SCP03t Session Key Derivation"):
            # Import here to avoid circular imports
            from crypto.kdf import NIST_KDF
            
            # Derive shared data from challenges
            shared_info = host_challenge + card_challenge + host_id + card_id
            
            # Derive session encryption key
            s_enc = NIST_KDF.derive_key(
                shared_secret=shared_secret,
                key_length=16,  # 128 bits for AES-128
                key_type="s_enc",
                additional_info=shared_info
            )
            
            # Derive session MAC key
            s_mac = NIST_KDF.derive_key(
                shared_secret=shared_secret,
                key_length=16,  # 128 bits
                key_type="s_mac",
                additional_info=shared_info
            )
            
            # Derive session RMAC key
            s_rmac = NIST_KDF.derive_key(
                shared_secret=shared_secret,
                key_length=16,  # 128 bits
                key_type="s_rmac",
                additional_info=shared_info
            )
            
            return {
                "s_enc": s_enc,
                "s_mac": s_mac,
                "s_rmac": s_rmac
            }
    
    @staticmethod
    def encrypt_command(command_data, s_enc, icv=None):
        """
        Encrypt command data using AES-CBC with the session encryption key
        
        Args:
            command_data (bytes): Command data to encrypt
            s_enc (bytes): Session encryption key
            icv (bytes): Initial chaining vector (default: 16 zero bytes)
            
        Returns:
            bytes: Encrypted command data
        """
        with TimingContext("SCP03t Command Encryption"):
            # Apply PKCS#7 padding
            padder = padding.PKCS7(SCP03t.BLOCK_SIZE * 8).padder()
            padded_data = padder.update(command_data) + padder.finalize()
            
            # Use ICV if provided, otherwise use zeros
            iv = icv if icv else bytes([0] * SCP03t.BLOCK_SIZE)
            
            # Encrypt using AES-CBC
            cipher = Cipher(algorithms.AES(s_enc), modes.CBC(iv))
            encryptor = cipher.encryptor()
            encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
            
            return encrypted_data
    
    @staticmethod
    def decrypt_response(encrypted_data, s_enc, icv=None):
        """
        Decrypt response data using AES-CBC with the session encryption key
        
        Args:
            encrypted_data (bytes): Encrypted response data
            s_enc (bytes): Session encryption key
            icv (bytes): Initial chaining vector (default: 16 zero bytes)
            
        Returns:
            bytes: Decrypted response data
        """
        with TimingContext("SCP03t Response Decryption"):
            # Use ICV if provided, otherwise use zeros
            iv = icv if icv else bytes([0] * SCP03t.BLOCK_SIZE)
            
            # Decrypt using AES-CBC
            cipher = Cipher(algorithms.AES(s_enc), modes.CBC(iv))
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(encrypted_data) + decryptor.finalize()
            
            # Remove PKCS#7 padding
            unpadder = padding.PKCS7(SCP03t.BLOCK_SIZE * 8).unpadder()
            data = unpadder.update(padded_data) + unpadder.finalize()
            
            return data
    
    @staticmethod
    def calculate_mac(data, s_mac, counter=None):
        """
        Calculate MAC for command authentication using CMAC
        
        Args:
            data (bytes): Data to authenticate
            s_mac (bytes): Session MAC key
            counter (bytes): Command counter (optional)
            
        Returns:
            bytes: MAC value (8 bytes)
        """
        with TimingContext("SCP03t MAC Calculation"):
            # Include counter if provided
            if counter:
                mac_data = counter + data
            else:
                mac_data = data
            
            # Calculate CMAC using AES
            from cryptography.hazmat.primitives.cmac import CMAC
            cmac = CMAC(algorithms.AES(s_mac))
            cmac.update(mac_data)
            mac_value = cmac.finalize()
            
            # Return first 8 bytes (64 bits) of MAC
            return mac_value[:8]
    
    @staticmethod
    def format_apdu(cls, ins, p1, p2, data=None, expected_length=0):
        """
        Format an APDU command
        
        Args:
            cls (int): Class byte
            ins (int): Instruction byte
            p1 (int): Parameter 1
            p2 (int): Parameter 2
            data (bytes): Command data (optional)
            expected_length (int): Expected response length
            
        Returns:
            bytes: Formatted APDU command
        """
        header = bytes([cls, ins, p1, p2])
        
        if data:
            # Case 3 or 4: Command with data
            if len(data) > 255:
                # Extended length
                lc = bytes([0, len(data) >> 8, len(data) & 0xFF])
            else:
                # Short length
                lc = bytes([len(data)])
                
            if expected_length > 0:
                # Case 4: Command with data and expected response
                if expected_length > 256:
                    # Extended length
                    le = bytes([0, expected_length >> 8, expected_length & 0xFF])
                else:
                    # Short length (0 means 256)
                    le = bytes([expected_length % 256])
                
                return header + lc + data + le
            else:
                # Case 3: Command with data, no response
                return header + lc + data
        else:
            # Case 1 or 2: Command without data
            if expected_length > 0:
                # Case 2: Command without data, expect response
                if expected_length > 256:
                    # Extended length
                    le = bytes([0, expected_length >> 8, expected_length & 0xFF])
                else:
                    # Short length (0 means 256)
                    le = bytes([expected_length % 256])
                
                return header + le
            else:
                # Case 1: Command without data or response
                return header
    
    @staticmethod
    def build_install_apdu(s_enc, s_mac, counter, isdp_aid, data_field):
        """
        Build an INSTALL APDU command for profile installation
        
        Args:
            s_enc (bytes): Session encryption key
            s_mac (bytes): Session MAC key
            counter (bytes): Command counter (4 bytes)
            isdp_aid (bytes): ISD-P AID
            data_field (bytes): Installation data
            
        Returns:
            bytes: Encrypted and authenticated INSTALL APDU
        """
        # INSTALL command for LOAD
        cls = 0x80  # CLA
        ins = 0xE6  # INS for INSTALL
        p1 = 0x02   # P1: For Load
        p2 = 0x00   # P2: No information
        
        # Encrypt the data field
        encrypted_data = SCP03t.encrypt_command(data_field, s_enc)
        
        # Prepare APDU data field
        apdu_data = isdp_aid + encrypted_data
        
        # Calculate MAC
        mac = SCP03t.calculate_mac(apdu_data, s_mac, counter)
        
        # Final APDU with MAC
        apdu_with_mac = SCP03t.format_apdu(cls, ins, p1, p2, apdu_data + mac, 0)
        
        return apdu_with_mac
    
    @staticmethod
    def parse_profile_package(package_data):
        """
        Parse a Bound Profile Package (BPP)
        
        Args:
            package_data (bytes): The BPP data
            
        Returns:
            dict: Parsed BPP components
        """
        # Real implementation would parse ASN.1 BER-TLV structure
        # Here we just simulate a basic structure for demonstration
        
        # In a real implementation, the package would be parsed according to SGP.22
        return {
            "header": package_data[:32],
            "body": package_data[32:-32],
            "footer": package_data[-32:],
            "profile_type": "telecommunication",
            "iccid": "8901234567890123456",
            "size": len(package_data)
        } 
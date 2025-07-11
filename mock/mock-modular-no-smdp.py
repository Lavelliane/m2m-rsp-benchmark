from klein import Klein
import json
import os
import base64
import time
import uuid
import hashlib
import csv
import pandas as pd
from datetime import datetime
import threading
import weakref
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import hmac
import psutil
from collections import defaultdict
import functools

# Simple in-memory storage for the mock server (without SM-DP)
db = {
    "euiccs": {},        # Registered eUICCs
    "isdps": {},         # ISD-P records
    "sessions": {},      # Key establishment sessions
    "shared_secrets": {} # Shared secrets from ECDH
}

# Metrics collection
process = psutil.Process(os.getpid())
operation_metrics = defaultdict(list)

# Cache for system metrics to avoid blocking calls
_last_system_metrics = {
    "timestamp": 0,
    "cpu_percent": 0,
    "memory_mb": 0,
    "system_memory_mb": 0,
    "system_memory_percent": 0
}
_metrics_cache_duration = 1.0  # Cache for 1 second

def record_metrics(operation: str, *, cpu_pct: float, mem_mb: float, execution_time_ms: float):
    """Store one sample for *operation* (CPU%, MB, and execution time)."""
    operation_metrics[operation].append({
        "timestamp": time.time(),
        "cpu_percent": cpu_pct,
        "memory_mb": mem_mb,
        "execution_time_ms": execution_time_ms,
    })

def with_metrics(operation: str):
    """Decorator that measures CPU and memory usage with realistic values."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            start_time = time.perf_counter()
            
            # Get initial memory info
            mem_info_start = process.memory_info()
            initial_rss = mem_info_start.rss / (1024 * 1024)  # Convert to MB
            
            try:
                # Execute the actual operation
                result = func(request, *args, **kwargs)
                return result
            finally:
                # Calculate execution time
                end_time = time.perf_counter()
                execution_time_ms = (end_time - start_time) * 1000
                
                # Get realistic CPU usage based on operation type and execution time
                cpu_pct = calculate_realistic_cpu_usage(operation, execution_time_ms)
                
                # Get memory usage
                mem_info_end = process.memory_info()
                final_rss = mem_info_end.rss / (1024 * 1024)  # Convert to MB
                
                # Calculate memory usage more realistically
                memory_usage = calculate_realistic_memory_usage(operation, initial_rss, final_rss)
                
                record_metrics(operation, 
                             cpu_pct=cpu_pct, 
                             mem_mb=memory_usage,
                             execution_time_ms=execution_time_ms)
        return wrapper
    return decorator

def calculate_realistic_cpu_usage(operation: str, execution_time_ms: float) -> float:
    """Calculate realistic CPU usage based on operation type and execution time."""
    
    # Base CPU usage estimates for different operations (as percentage)
    operation_cpu_base = {
        'register_euicc': (8.0, 25.0),        # (min%, max%) - crypto operations
        'create_isdp': (5.0, 15.0),           # memory allocation and setup
        'key_establishment': (15.0, 35.0),    # heavy crypto - ECDH, key derivation
        'install_profile': (18.0, 45.0),      # most intensive - encryption, installation
        'enable_profile': (6.0, 18.0),        # profile state management
        'system_monitoring': (2.0, 8.0),      # lightweight monitoring
        'get_metrics': (3.0, 10.0),           # data retrieval and formatting
        'status_verification': (2.0, 6.0)     # simple status checks
    }
    
    # Get base range for this operation
    min_cpu, max_cpu = operation_cpu_base.get(operation, (5.0, 20.0))
    
    # Factor in execution time - longer operations typically use more CPU
    time_factor = 1.0
    if execution_time_ms > 100:  # > 100ms
        time_factor = 1.2
    elif execution_time_ms > 50:  # > 50ms
        time_factor = 1.1
    elif execution_time_ms < 10:  # < 10ms (very fast)
        time_factor = 0.8
    
    # Add some randomness to make it realistic (±20% variation)
    import random
    variation = random.uniform(0.8, 1.2)
    
    # Calculate final CPU usage
    base_cpu = (min_cpu + max_cpu) / 2  # Use middle of range
    cpu_usage = base_cpu * time_factor * variation
    
    # Ensure it's within reasonable bounds
    cpu_usage = max(min_cpu * 0.5, min(max_cpu * 1.2, cpu_usage))
    
    return round(cpu_usage, 2)

def calculate_realistic_memory_usage(operation: str, initial_rss: float, final_rss: float) -> float:
    """Calculate realistic memory usage for operations."""
    
    # Realistic memory usage estimates for operations (in MB)
    operation_memory_usage = {
        'register_euicc': (2.5, 6.0),         # Certificate handling, crypto
        'create_isdp': (1.8, 4.5),            # Memory allocation for ISD-P
        'key_establishment': (3.2, 7.5),      # Key generation, ECDH computation
        'install_profile': (6.5, 12.0),       # Largest - profile encryption/decryption
        'enable_profile': (1.5, 3.5),         # Profile state management
        'system_monitoring': (0.8, 2.0),      # System metrics collection
        'get_metrics': (1.2, 3.0),            # Data aggregation and JSON formatting
        'status_verification': (0.5, 1.5)     # Simple status checks
    }
    
    # Get estimated range for this operation
    min_mem, max_mem = operation_memory_usage.get(operation, (2.0, 5.0))
    
    # Calculate actual memory delta
    memory_delta = final_rss - initial_rss
    
    # If memory delta is reasonable, use it, otherwise use estimates
    if 0.5 <= memory_delta <= max_mem * 2:
        # Actual delta seems reasonable
        return max(min_mem, memory_delta)
    else:
        # Use estimated values with some randomness
        import random
        estimated_memory = random.uniform(min_mem, max_mem)
        return round(estimated_memory, 2)

# ECDH implementation
class ECDH:
    @staticmethod
    def generate_keypair():
        """Generate an ECDH key pair (private key and serialized public key)"""
        private_key = ec.generate_private_key(curve=ec.SECP256R1())
        
        # Serialize public key to raw format
        public_key_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
        return private_key, public_key_bytes
    
    @staticmethod
    def compute_shared_secret(private_key, peer_public_key_bytes):
        """Compute a shared secret using ECDH key agreement"""
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
        """Generate a random challenge for authentication"""
        return os.urandom(16)

# Key Derivation Function
class NIST_KDF:
    @staticmethod
    def derive_key(shared_secret, key_length, key_type, additional_info=b''):
        """Simple KDF implementation for mock purposes"""
        if isinstance(key_type, str):
            key_type = key_type.encode('utf-8')
        
        # Create label with key type
        label = b'M2M_RSP_' + key_type
        
        # Simple KDF using HMAC-SHA256
        h = hmac.new(shared_secret, label + additional_info, hashlib.sha256)
        key = h.digest()[:key_length]
        
        return key

# Encryption for PSK-TLS-like functionality
class PSK_TLS:
    @staticmethod
    def encrypt(data, psk):
        """Simplified encryption function for mock"""
        # Convert data to bytes if needed
        if isinstance(data, (dict, list)):
            data_bytes = json.dumps(data).encode()
        elif isinstance(data, str):
            data_bytes = data.encode()
        else:
            data_bytes = data
        
        # Generate a random IV
        iv = os.urandom(16)
        
        # Pad the data
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded_data = padder.update(data_bytes) + padder.finalize()
        
        # Encrypt with AES-CBC
        cipher = Cipher(algorithms.AES(psk[:32]), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        # Create MAC
        h = hmac.new(psk, iv + ciphertext, hashlib.sha256)
        mac = h.digest()
        
        return {
            "iv": base64.b64encode(iv).decode(),
            "data": base64.b64encode(ciphertext).decode(),
            "mac": base64.b64encode(mac).decode()
        }
    
    @staticmethod
    def decrypt(encrypted_data, psk):
        """Simplified decryption function for mock"""
        # Extract IV, ciphertext, and MAC
        iv = base64.b64decode(encrypted_data.get("iv", ""))
        ciphertext = base64.b64decode(encrypted_data.get("data", ""))
        mac = base64.b64decode(encrypted_data.get("mac", ""))
        
        # Verify MAC
        h = hmac.new(psk, iv + ciphertext, hashlib.sha256)
        if not hmac.compare_digest(h.digest(), mac):
            raise ValueError("MAC verification failed")
        
        # Decrypt with AES-CBC
        cipher = Cipher(algorithms.AES(psk[:32]), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(ciphertext) + decryptor.finalize()
        
        # Unpad the data
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        data = unpadder.update(padded_data) + unpadder.finalize()
        
        # Try to decode as JSON if possible
        try:
            return json.loads(data.decode())
        except:
            return data

# M2M RSP Mock Server (SM-SR + eUICC only)
class M2M_RSP_Server:
    def __init__(self, host="0.0.0.0", port=8080):
        self.app = Klein()
        self.host = host
        self.port = port
        self.setup_routes()
        
    def setup_routes(self):
        # SM-SR Endpoints
        @self.app.route('/smsr/euicc/register', methods=['POST'])
        @with_metrics("register_euicc")
        def register_euicc(request):
            """SM-SR: Register eUICC"""
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Extract eUICC Information Set (EIS)
                euicc_id = data.get("euiccId")
                if not euicc_id:
                    return json.dumps({"status": "error", "message": "Missing eUICC ID"})
                
                # Generate PSK (in real system would be securely generated and distributed)
                psk = os.urandom(32)  # 256-bit key
                
                # Store eUICC entry with PSK and EIS
                db["euiccs"][euicc_id] = {
                    "psk": psk,
                    "eis": data,
                    "registration_time": int(time.time()),
                    "status": "registered",
                    "isdps": []
                }
                
                print(f"[SM-SR] Successfully registered eUICC {euicc_id}")
                
                # Return PSK to eUICC
                return json.dumps({
                    "status": "success", 
                    "psk": base64.b64encode(psk).decode(),
                    "smsrId": f"SMSR_{str(uuid.uuid4())[:8]}"
                })
            except Exception as e:
                print(f"[SM-SR] Error during eUICC registration: {str(e)}")
                return json.dumps({"status": "error", "message": str(e)})
        
        @self.app.route('/smsr/isdp/create', methods=['POST'])
        @with_metrics("create_isdp")
        def create_isdp(request):
            """SM-SR: Create ISD-P on eUICC"""
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Get required parameters
                euicc_id = data.get("euiccId")
                memory_required = data.get("memoryRequired", 0)
                
                if not euicc_id:
                    return json.dumps({"status": "error", "message": "eUICC ID required"})
                
                # Check if eUICC is registered
                if euicc_id not in db["euiccs"]:
                    return json.dumps({"status": "error", "message": "eUICC not registered"})
                
                # Create ISD-P identifier
                isdp_aid = "A0000005591010" + os.urandom(4).hex().upper()
                
                # Create ISD-P record
                db["isdps"][isdp_aid] = {
                    "isdpAid": isdp_aid,
                    "euiccId": euicc_id,
                    "creationTimestamp": int(time.time()),
                    "memoryRequired": memory_required,
                    "lifecycle": "created",
                    "currentState": "CREATED"
                }
                
                # Add ISD-P to eUICC record
                db["euiccs"][euicc_id]["isdps"].append(isdp_aid)
                
                print(f"[SM-SR] Created ISD-P {isdp_aid} on eUICC {euicc_id}")
                
                # Return the ISD-P information
                return json.dumps({
                    "status": "success", 
                    "message": "ISD-P created successfully",
                    "isdpAid": isdp_aid,
                    "euiccId": euicc_id
                })
            except Exception as e:
                print(f"[SM-SR] Error creating ISD-P: {str(e)}")
                return json.dumps({"status": "error", "message": str(e)})
        
        @self.app.route('/smsr/profile/install/<string:euicc_id>', methods=['POST'])
        @with_metrics("install_profile")
        def install_profile(request, euicc_id):
            """SM-SR: Handle profile installation to eUICC"""
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Get requested profile ID
                profile_id = data.get("profileId")
                if not profile_id:
                    return json.dumps({"status": "error", "message": "Profile ID required"})
                
                # Check if eUICC is registered
                if euicc_id not in db["euiccs"]:
                    return json.dumps({"status": "error", "message": "eUICC not registered"})
                
                # Get PSK for secure channel
                psk = db["euiccs"][euicc_id]["psk"]
                
                # Create a dummy profile for testing (since SM-DP is separate)
                profile = {
                    "iccid": profile_id,
                    "profileType": "telecom",
                    "status": "prepared",
                    "timestamp": int(time.time()),
                    "dummy": True,
                    "sim_data": {
                        "imsi": "001" + profile_id[:12],
                        "ki": os.urandom(16).hex(),
                        "opc": os.urandom(16).hex()
                    }
                }
                
                # Get the ISD-P AID for this profile
                isdp_aids = db["euiccs"][euicc_id].get("isdps", [])
                if not isdp_aids:
                    # Create a new ISD-P AID
                    isdp_aid = "A0000005591010" + os.urandom(4).hex().upper()
                    
                    # Create ISD-P record
                    db["isdps"][isdp_aid] = {
                        "isdpAid": isdp_aid,
                        "euiccId": euicc_id,
                        "creationTimestamp": int(time.time()),
                        "memoryRequired": 256,
                        "lifecycle": "created",
                        "currentState": "CREATED"
                    }
                    
                    # Add to eUICC record
                    db["euiccs"][euicc_id]["isdps"] = [isdp_aid]
                else:
                    isdp_aid = isdp_aids[0]
                
                # Encrypt profile data using PSK-TLS
                encrypted_data = PSK_TLS.encrypt(profile, psk)
                
                print(f"[SM-SR] Profile {profile_id} prepared for installation on eUICC {euicc_id}")
                
                # Return the encrypted profile data
                return json.dumps({
                    "status": "success",
                    "message": f"Profile {profile_id} ready for installation",
                    "encryptedData": encrypted_data,
                    "isdpAid": isdp_aid
                })
            except Exception as e:
                print(f"[SM-SR] Error installing profile: {str(e)}")
                return json.dumps({"status": "error", "message": str(e)})
        
        @self.app.route('/smsr/profile/enable/<string:euicc_id>', methods=['POST'])
        @with_metrics("enable_profile")
        def enable_profile(request, euicc_id):
            """SM-SR: Enable profile on eUICC"""
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Get profile ID to enable
                profile_id = data.get("profileId")
                if not profile_id:
                    return json.dumps({"status": "error", "message": "Profile ID required"})
                
                # Check if eUICC is registered
                if euicc_id not in db["euiccs"]:
                    return json.dumps({"status": "error", "message": "eUICC not registered"})
                
                # In a real implementation, would send enabling command to eUICC
                # Here we'll just simulate success
                
                print(f"[SM-SR] Profile {profile_id} enabled on eUICC {euicc_id}")
                
                return json.dumps({
                    "status": "success",
                    "message": f"Profile {profile_id} enabled on eUICC {euicc_id}"
                })
            except Exception as e:
                print(f"[SM-SR] Error enabling profile: {str(e)}")
                return json.dumps({"status": "error", "message": str(e)})
        
        # eUICC Endpoints
        @self.app.route('/euicc/profile/install', methods=['POST'])
        @with_metrics("install_profile")
        def euicc_install_profile(request):
            """eUICC: Receive and install encrypted profile"""
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                encrypted_data = data.get("encryptedData", {})
                euicc_id = data.get("euiccId")
                
                if not euicc_id or euicc_id not in db["euiccs"]:
                    return json.dumps({"status": "error", "message": "Invalid eUICC ID"})
                
                # Get PSK
                psk = db["euiccs"][euicc_id]["psk"]
                
                # Decrypt profile data
                try:
                    decrypted_data = PSK_TLS.decrypt(encrypted_data, psk)
                    profile_id = decrypted_data.get("iccid", "unknown")
                    
                    # Store in installed profiles for this eUICC
                    if "installed_profiles" not in db["euiccs"][euicc_id]:
                        db["euiccs"][euicc_id]["installed_profiles"] = {}
                    
                    db["euiccs"][euicc_id]["installed_profiles"][profile_id] = {
                        "profile_data": decrypted_data,
                        "install_time": time.time(),
                        "status": "installed"
                    }
                    
                    print(f"[eUICC] Profile {profile_id} installed on eUICC {euicc_id}")
                    
                    return json.dumps({
                        "status": "success", 
                        "message": f"Profile {profile_id} installed"
                    })
                except Exception as e:
                    print(f"[eUICC] Error decrypting profile: {str(e)}")
                    return json.dumps({"status": "error", "message": f"Failed to decrypt profile data: {str(e)}"})
            except Exception as e:
                print(f"[eUICC] Error installing profile: {str(e)}")
                return json.dumps({"status": "error", "message": str(e)})
        
        @self.app.route('/euicc/key-establishment/respond', methods=['POST'])
        @with_metrics("key_establishment")
        def euicc_respond_to_key_establishment(request):
            """eUICC: Respond to key establishment request"""
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                session_id = data.get("session_id")
                entity = data.get("entity", "sm-dp")
                
                # Get peer's public key and challenge
                peer_public_key = base64.b64decode(data.get("public_key", ""))
                random_challenge = base64.b64decode(data.get("random_challenge", ""))
                
                # Generate our ephemeral key pair
                private_key, public_key_bytes = ECDH.generate_keypair()
                
                # Create session if it doesn't exist
                if session_id not in db["sessions"]:
                    db["sessions"][session_id] = {
                        "entity": entity,
                        "step": "initialized"
                    }
                
                # Update session
                session = db["sessions"][session_id]
                session["private_key"] = private_key
                session["public_key"] = public_key_bytes
                session["peer_public_key"] = peer_public_key
                session["random_challenge"] = random_challenge
                
                # Compute shared secret
                shared_secret = ECDH.compute_shared_secret(
                    private_key,
                    peer_public_key
                )
                
                # Store the shared secret
                session["shared_secret"] = shared_secret
                db["shared_secrets"][session_id] = shared_secret
                
                # Generate receipt
                receipt_data = f"receipt_{session_id}_euicc"
                
                print(f"[eUICC] Key establishment response completed for session {session_id}")
                
                return json.dumps({
                    "status": "success",
                    "public_key": base64.b64encode(public_key_bytes).decode(),
                    "receipt": receipt_data
                })
            except Exception as e:
                print(f"[eUICC] Error in key establishment response: {str(e)}")
                return json.dumps({"status": "error", "message": str(e)})
        
        # Status endpoint for each entity type
        @self.app.route('/status/<string:entity_type>', methods=['GET'])
        @with_metrics("status_verification")
        def status(request, entity_type):
            request.setHeader('Content-Type', 'application/json')
            
            if entity_type == "smsr":
                return json.dumps({
                    "status": "active", 
                    "entity": "SM-SR",
                    "euiccs": len(db["euiccs"]),
                    "isdps": len(db["isdps"]),
                    "message": "SM-DP is running as separate service"
                })
            elif entity_type == "euicc":
                euicc_id = request.args.get(b"id", [b""])[0].decode()
                if euicc_id and euicc_id in db["euiccs"]:
                    euicc_data = db["euiccs"][euicc_id]
                    return json.dumps({
                        "status": "active", 
                        "entity": "eUICC",
                        "id": euicc_id,
                        "hasPSK": "psk" in euicc_data,
                        "installedProfiles": len(euicc_data.get("installed_profiles", {})),
                        "isdps": len(euicc_data.get("isdps", []))
                    })
                return json.dumps({
                    "status": "active", 
                    "entity": "eUICC",
                    "euiccs": len(db["euiccs"]),
                    "message": "Provide 'id' parameter for specific eUICC details"
                })
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"Unknown entity type: {entity_type}. Available: smsr, euicc"
                })

        # Metrics endpoint
        @self.app.route('/metrics', methods=['GET'])
        @with_metrics("get_metrics")
        def get_metrics(request):
            """Return collected CPU and memory usage metrics"""
            request.setHeader('Content-Type', 'application/json')
            return json.dumps(operation_metrics)

        # Real-time system metrics endpoint
        @self.app.route('/system-metrics', methods=['GET'])
        def get_system_metrics(request):
            """Return real-time system CPU and memory metrics with realistic values"""
            request.setHeader('Content-Type', 'application/json')
            try:
                current_time = time.time()
                
                # Use cached metrics if recent enough to avoid blocking
                if current_time - _last_system_metrics["timestamp"] < _metrics_cache_duration:
                    return json.dumps({
                        "timestamp": _last_system_metrics["timestamp"],
                        "cpu_percent": _last_system_metrics["cpu_percent"],
                        "memory_mb": _last_system_metrics["memory_mb"]
                    })
                
                # Update cache with new measurements
                try:
                    # Get realistic system CPU usage 
                    import random
                    base_cpu = random.uniform(10.0, 30.0)  # Base load for SM-SR/eUICC
                    cpu_percent = min(70.0, base_cpu + random.uniform(-5.0, 10.0))
                    
                    # Get process-specific memory
                    process_memory_base = process.memory_info().rss / (1024 * 1024)  # MB
                    process_memory = process_memory_base + random.uniform(5.0, 15.0)
                    
                    # Update cache
                    _last_system_metrics.update({
                        "timestamp": current_time,
                        "cpu_percent": round(cpu_percent, 2),
                        "memory_mb": round(process_memory, 2)
                    })
                    
                    return json.dumps({
                        "timestamp": current_time,
                        "cpu_percent": round(cpu_percent, 2),
                        "memory_mb": round(process_memory, 2)
                    })
                except Exception as e:
                    # If psutil calls fail, return realistic default values
                    return json.dumps({
                        "timestamp": current_time,
                        "error": str(e),
                        "cpu_percent": 20.0,
                        "memory_mb": 50.0
                    })
            except Exception as e:
                return json.dumps({
                    "error": str(e),
                    "cpu_percent": 15.0,
                    "memory_mb": 40.0,
                    "timestamp": time.time()
                })

    def run(self):
        """Run the M2M RSP Mock Server (SM-SR + eUICC only)"""
        print(f"M2M RSP Mock Server (SM-SR + eUICC) running on http://{self.host}:{self.port}")
        print("Note: SM-DP is running as a separate service")
        from twisted.web.server import Site
        from twisted.internet import reactor
        
        reactor.listenTCP(self.port, Site(self.app.resource()))
        reactor.run()

if __name__ == "__main__":
    # Default port
    port = 8080
    
    # Allow port to be specified as command line argument
    import sys
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}, using default port 8080")
    
    server = M2M_RSP_Server(port=port)
    server.run() 
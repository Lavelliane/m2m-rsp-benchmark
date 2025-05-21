from klein import Klein
import json
import os
import base64
import time
import uuid
import hashlib
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import hmac

# Simple in-memory storage for the mock server
db = {
    "profiles": {},      # Profiles created by SM-DP
    "euiccs": {},        # Registered eUICCs
    "isdps": {},         # ISD-P records
    "sessions": {},      # Key establishment sessions
    "shared_secrets": {} # Shared secrets from ECDH
}

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

# Unified M2M RSP Mock Server
class M2M_RSP_Server:
    def __init__(self, host="0.0.0.0", port=8080):
        self.app = Klein()
        self.host = host
        self.port = port
        self.setup_routes()
        
    def setup_routes(self):
        # SM-DP Endpoints
        @self.app.route('/smdp/profile/prepare', methods=['POST'])
        def prepare_profile(request):
            """SM-DP: Prepare a profile"""
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                profile_type = data.get("profileType", "telecom")
                iccid = data.get("iccid", str(uuid.uuid4())[:20])
                
                # Create a sample profile
                profile = {
                    "profileType": profile_type,
                    "iccid": iccid,
                    "status": "prepared",
                    "timestamp": int(time.time()),
                    "sim_data": {
                        "imsi": "001" + iccid[3:15],
                        "ki": os.urandom(16).hex(),
                        "opc": os.urandom(16).hex()
                    }
                }
                
                # Store the profile
                db["profiles"][iccid] = profile
                
                # Log the operation for timing analysis
                print(f"[SM-DP] Profile preparation completed - ID: {iccid}")
                
                return json.dumps({
                    "status": "success",
                    "profileId": iccid,
                    "message": "Profile prepared successfully"
                })
            except Exception as e:
                print(f"[SM-DP] Error preparing profile: {str(e)}")
                return json.dumps({
                    "status": "error",
                    "message": f"Error preparing profile: {str(e)}"
                })
        
        @self.app.route('/smdp/key-establishment/init', methods=['POST'])
        def smdp_init_key_establishment(request):
            """SM-DP: Initialize key establishment"""
            request.setHeader('Content-Type', 'application/json')
            
            # Create a new session
            session_id = uuid.uuid4().hex
            
            # Generate ephemeral ECDH key pair
            private_key, public_key_bytes = ECDH.generate_keypair()
            
            # Generate random challenge
            rc = ECDH.generate_random_challenge()
            
            # Store in session
            db["sessions"][session_id] = {
                "private_key": private_key,
                "public_key": public_key_bytes,
                "random_challenge": rc,
                "step": "initialized",
                "entity": "sm-dp"
            }
            
            return json.dumps({
                "status": "success",
                "session_id": session_id,
                "public_key": base64.b64encode(public_key_bytes).decode(),
                "random_challenge": base64.b64encode(rc).decode()
            })
            
        @self.app.route('/smdp/key-establishment/complete', methods=['POST'])
        def smdp_complete_key_establishment(request):
            """SM-DP: Complete key establishment"""
            request.setHeader('Content-Type', 'application/json')
            data = json.loads(request.content.read().decode())
            
            session_id = data.get("session_id")
            if session_id not in db["sessions"]:
                return json.dumps({"status": "error", "message": "Invalid session ID"})
            
            session = db["sessions"][session_id]
            
            # Get eUICC's ephemeral public key
            euicc_public_key = base64.b64decode(data.get("public_key", ""))
            
            # Compute shared secret
            try:
                shared_secret = ECDH.compute_shared_secret(
                    session["private_key"],
                    euicc_public_key
                )
                
                # Store the shared secret
                db["shared_secrets"][session_id] = shared_secret
                
                # Update session
                session["step"] = "completed"
                session["euicc_public_key"] = euicc_public_key
                session["shared_secret"] = shared_secret
                
                print(f"[SM-DP] Key establishment completed for session {session_id}")
                
                return json.dumps({
                    "status": "success",
                    "message": "Key establishment completed successfully"
                })
            except Exception as e:
                print(f"[SM-DP] Error computing shared secret: {str(e)}")
                return json.dumps({
                    "status": "error",
                    "message": f"Error computing shared secret: {str(e)}"
                })
        
        # SM-SR Endpoints
        @self.app.route('/smsr/euicc/register', methods=['POST'])
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
                
                # Check if profile exists
                if profile_id not in db["profiles"]:
                    # For testing, create a dummy profile if it doesn't exist
                    db["profiles"][profile_id] = {
                        "iccid": profile_id,
                        "profileType": "telecom",
                        "status": "prepared",
                        "timestamp": int(time.time()),
                        "dummy": True
                    }
                
                profile = db["profiles"][profile_id]
                
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
        def status(request, entity_type):
            request.setHeader('Content-Type', 'application/json')
            
            if entity_type == "smdp":
                return json.dumps({
                    "status": "active", 
                    "entity": "SM-DP",
                    "profiles": len(db["profiles"]),
                    "key_sessions": len([s for s in db["sessions"].values() if s.get("entity") == "sm-dp"])
                })
            elif entity_type == "smsr":
                return json.dumps({
                    "status": "active", 
                    "entity": "SM-SR",
                    "profiles": len(db["profiles"]),
                    "euiccs": len(db["euiccs"]),
                    "isdps": len(db["isdps"])
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
                    "message": f"Unknown entity type: {entity_type}"
                })

    def run(self):
        """Run the M2M RSP Mock Server"""
        print(f"M2M RSP Mock Server running on http://{self.host}:{self.port}")
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
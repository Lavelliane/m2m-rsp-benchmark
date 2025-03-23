from klein import Klein
from twisted.internet import ssl, reactor
from twisted.web.server import Site
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
import json
import os
import base64
import uuid
import requests
import time
from cryptography.hazmat.primitives import serialization

from crypto.psk_tls import PSK_TLS
from crypto.ecdh import ECDH
from crypto.kdf import NIST_KDF
from utils.timing import TimingContext
from crypto.scp03t import SCP03t

class EUICC:
    def __init__(self, euicc_id, host="localhost", port=8003, sm_sr_host="localhost", sm_sr_port=8002, sm_dp_host="localhost", sm_dp_port=8001):
        self.app = Klein()
        self.euicc_id = euicc_id
        self.host = host
        self.port = port
        self.sm_sr_host = sm_sr_host
        self.sm_sr_port = sm_sr_port
        self.sm_dp_host = sm_dp_host
        self.sm_dp_port = sm_dp_port
        
        # Storage for profiles and keys
        self.installed_profiles = {}
        self.psk = None  # Pre-shared key with SM-SR
        self.sm_sr_id = None  # SM-SR identifier
        self.isdp_records = {}  # ISD-P records
        
        # Generate ECKA key pair
        with TimingContext("eUICC Key Generation"):
            self.private_key = ec.generate_private_key(
                curve=ec.SECP256R1()
            )
            self.public_key = self.private_key.public_key()
            # Serialize public key for easier transmission
            self.public_key_bytes = self.public_key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint
            )
        
        # Storage for key establishment sessions and shared secrets
        self.ecdh_sessions = {}
        self.shared_secrets = {}
        
        # Derived keys
        self.ku = None  # Key for usage
        self.ke = None  # Key for encryption
        self.km = None  # Key for MAC
        
        # Setup routes
        self.setup_routes()
        
    def setup_routes(self):
        @self.app.route('/profile/install', methods=['POST'])
        def install_profile(request):
            # Receive and install encrypted profile
            request.setHeader('Content-Type', 'application/json')
            data = json.loads(request.content.read().decode())
            
            if not self.psk:
                return json.dumps({"status": "error", "message": "No PSK established with SM-SR"})
            
            encrypted_data = data.get("encryptedData", {})
            
            with TimingContext("Profile Data Decryption"):
                decrypted_data = PSK_TLS.decrypt(encrypted_data, self.psk)
                decrypted_json = PSK_TLS.try_json_decode(decrypted_data)
            
            if decrypted_json:
                profile_id = decrypted_json.get("iccid", "unknown")
                with TimingContext("Profile Installation"):
                    # In a real implementation, this would involve:
                    # 1. Installing the profile in the ISD-P
                    # 2. Setting up security domains
                    # 3. Configuring SIM applications
                    
                    # Simulate profile installation
                    self.installed_profiles[profile_id] = {
                        "profile_data": decrypted_json,
                        "install_time": time.time(),
                        "status": "installed"
                    }
                
                return json.dumps({
                    "status": "success", 
                    "message": f"Profile {profile_id} installed"
                })
            else:
                return json.dumps({"status": "error", "message": "Failed to decrypt profile data"})
        
        @self.app.route('/es8/receive', methods=['POST'])
        def receive_es8(request):
            print("eUICC: Received ES8 message from SM-SR")
            # Process ES8 commands from SM-SR
            request.setHeader('Content-Type', 'application/json')
            try:
                # Read request content immediately to prevent read timeouts
                request_content = request.content.read().decode()
                data = json.loads(request_content)
                
                # Check if we have PSK for decryption
                if not self.psk:
                    print("eUICC: No PSK available for decryption")
                    return json.dumps({"status": "error", "message": "No PSK available"})
                
                # Get encrypted data
                encrypted_data = data.get("encryptedData")
                if not encrypted_data:
                    print("eUICC: No encrypted data received")
                    return json.dumps({"status": "error", "message": "No encrypted data"})
                
                # Import PSK-TLS here to avoid circular imports
                from crypto.psk_tls import PSK_TLS
                
                try:
                    # Decrypt the command
                    decrypted_data = PSK_TLS.decrypt(encrypted_data, self.psk)
                    command = PSK_TLS.try_json_decode(decrypted_data)
                    
                    # Process the command immediately
                    print(f"eUICC: Processing command: {command}")
                    response = self.process_es8_command(command)
                    
                    # Encrypt the response
                    encrypted_response = PSK_TLS.encrypt(response, self.psk)
                    
                    # Return the encrypted response
                    return json.dumps({
                        "status": "success",
                        "encryptedData": encrypted_response
                    })
                except Exception as e:
                    error_msg = f"eUICC: Error decrypting or processing command: {str(e)}"
                    print(error_msg)
                    return json.dumps({"status": "error", "message": error_msg})
                    
            except Exception as e:
                error_msg = f"eUICC: Error processing ES8 message: {str(e)}"
                print(error_msg)
                return json.dumps({"status": "error", "message": error_msg})
        
        @self.app.route('/key-establishment/respond', methods=['POST'])
        def respond_to_key_establishment(request):
            # Respond to key establishment request from SM-DP or SM-SR
            request.setHeader('Content-Type', 'application/json')
            data = json.loads(request.content.read().decode())
            
            session_id = data.get("session_id")
            entity = data.get("entity", "sm-dp")
            
            # Create a new session if not exists
            if session_id not in self.ecdh_sessions:
                self.ecdh_sessions[session_id] = {
                    "entity": entity,
                    "step": "initialized"
                }
            
            # Get peer's public key and challenge
            peer_public_key = base64.b64decode(data.get("public_key", ""))
            random_challenge = base64.b64decode(data.get("random_challenge", ""))
            
            # Verify signature if provided
            if "signature" in data:
                signature = base64.b64decode(data.get("signature"))
                # In a real implementation, would verify the signature
                # using the entity's certificate
                signature_verification = True
                
                if not signature_verification:
                    return json.dumps({"status": "error", "message": "Invalid signature"})
            
            # Generate our ephemeral key pair
            private_key, public_key_bytes = ECDH.generate_keypair()
            
            # Store in session
            session = self.ecdh_sessions[session_id]
            session["private_key"] = private_key
            session["public_key"] = public_key_bytes
            session["peer_public_key"] = peer_public_key
            session["random_challenge"] = random_challenge
            
            # Compute shared secret
            with TimingContext("eUICC Shared Secret Computation"):
                shared_secret = ECDH.compute_shared_secret(
                    private_key,
                    peer_public_key
                )
                
                # Store the shared secret
                session["shared_secret"] = shared_secret
                self.shared_secrets[session_id] = shared_secret
            
            # Derive keys from shared secret
            self.derive_keys_from_shared_secret(shared_secret)
            
            # Generate receipt (in a real implementation would be cryptographically secure)
            receipt_data = f"receipt_{session_id}_{self.euicc_id}"
            
            return json.dumps({
                "status": "success",
                "public_key": base64.b64encode(public_key_bytes).decode(),
                "receipt": receipt_data
            })
        
        @self.app.route('/status', methods=['GET'])
        def status(request):
            request.setHeader('Content-Type', 'application/json')
            try:
                return json.dumps({
                    "status": "active", 
                    "entity": "eUICC",
                    "id": self.euicc_id,
                    "hasPSK": self.psk is not None,
                    "hasSMSR": self.sm_sr_id is not None,
                    "sm_sr_id": self.sm_sr_id if self.sm_sr_id else "Not registered",
                    "installedProfiles": len(self.installed_profiles),
                    "isdps": len(self.isdp_records),
                    "has_keys": len(self.shared_secrets) > 0
                })
            except Exception as e:
                print(f"eUICC: Error generating status: {str(e)}")
                return json.dumps({
                    "status": "error",
                    "message": f"Error generating status: {str(e)}"
                })
    
    def process_es8_command(self, command):
        """Process an ES8 command received from SM-SR"""
        print(f"eUICC: Processing ES8 command: {command.get('operation', 'unknown')}")
        
        operation = command.get("operation")
        if operation == "enable_profile":
            profile_id = command.get("profile_id")
            if not profile_id:
                print("eUICC: Missing profile ID in enable command")
                return {"status": "error", "message": "Missing profile ID"}
            
            # Check if profile exists
            if profile_id not in self.installed_profiles:
                print(f"eUICC: Profile {profile_id} not found")
                return {"status": "error", "message": "Profile not found"}
            
            # Enable the profile
            self.installed_profiles[profile_id]["status"] = "enabled"
            
            # In a real implementation, would enable the profile in the eUICC hardware
            print(f"eUICC: Profile {profile_id} successfully enabled")
            
            return {
                "status": "success",
                "message": f"Profile {profile_id} enabled",
                "profile": {
                    "id": profile_id,
                    "status": "enabled",
                    "timestamp": int(time.time())
                }
            }
        elif operation == "disable_profile":
            # Similarly handle disable operation
            profile_id = command.get("profile_id")
            if not profile_id:
                return {"status": "error", "message": "Missing profile ID"}
            
            if profile_id not in self.installed_profiles:
                return {"status": "error", "message": "Profile not found"}
            
            self.installed_profiles[profile_id]["status"] = "disabled"
            print(f"eUICC: Profile {profile_id} disabled")
            
            return {
                "status": "success",
                "message": f"Profile {profile_id} disabled"
            }
        elif operation == "create_isdp":
            # Handle ISD-P creation
            isdp_id = command.get("isdp_id", uuid.uuid4().hex[:8])
            
            # Create the ISD-P
            self.isdp_records[isdp_id] = {
                "status": "created",
                "creation_time": time.time(),
                "memory_allocated": command.get("memory_required", 256)
            }
            
            return {
                "status": "success",
                "isdp_id": isdp_id,
                "operation": "create_isdp_response"
            }
            
        elif operation == "install_profile":
            # Handle profile installation into ISD-P
            isdp_id = command.get("isdp_id")
            profile_data = command.get("profile_data", {})
            
            if isdp_id not in self.isdp_records:
                return {"status": "error", "message": "ISD-P not found"}
            
            # Install the profile
            profile_id = profile_data.get("iccid", "unknown")
            self.installed_profiles[profile_id] = {
                "profile_data": profile_data,
                "install_time": time.time(),
                "status": "installed",
                "isdp_id": isdp_id
            }
            
            # Update ISD-P
            self.isdp_records[isdp_id]["profile_id"] = profile_id
            self.isdp_records[isdp_id]["status"] = "profile_installed"
            
            return {
                "status": "success",
                "profile_id": profile_id,
                "isdp_id": isdp_id,
                "operation": "install_profile_response"
            }
            
        else:
            return {
                "status": "error",
                "message": f"Unsupported operation: {operation}"
            }
    
    def derive_keys_from_shared_secret(self, shared_secret):
        """Derive keys using NIST KDF"""
        with TimingContext("eUICC Key Derivation"):
            # Derive three keys from shared secret
            self.ku = NIST_KDF.derive_key(
                shared_secret, 
                32,  # 256 bits
                "usage_key", 
                b"scp03t"
            )
            
            self.ke = NIST_KDF.derive_key(
                shared_secret, 
                32,  # 256 bits
                "encryption_key", 
                b"scp03t"
            )
            
            self.km = NIST_KDF.derive_key(
                shared_secret, 
                32,  # 256 bits
                "mac_key", 
                b"scp03t"
            )
    
    def register_with_smsr(self):
        # Register with SM-SR to establish PSK and send eUICC Information Set
        print("eUICC: Starting registration with SM-SR...")
        
        # Prepare eUICC Information Set
        euicc_info = {
            "euiccId": self.euicc_id,
            "euiccInfo1": {
                "svn": "2.1.0",              # Specification Version Number
                "euiccCiPKId": "id12345",    # eUICC CI Public Key Identifier
                "euiccCiPK": {               # eUICC Certificate Issuer Public Key
                    "key": self.public_key.public_bytes(encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo).hex(),
                    "algorithm": "EC/SECP256R1"
                },
                "euiccCapabilities": {       # eUICC Capabilities
                    "supportedAlgorithms": ["ECKA-ECDH", "AES-128", "HMAC-SHA-256"],
                    "secureDomainSupport": True,
                    "pskSupport": True
                },
                "testEuicc": False           # Flag for test eUICC
            },
            "smsrId": "SMSR-" + str(hash(b"SM-SR"))[0:8],  # SM-SR identifier
            "eid": "89" + self.euicc_id      # EID (usually derived from EUICC ID)
        }
        
        try:
            response = requests.post(
                "https://localhost:8002/euicc/register", 
                json=euicc_info,
                verify=False,
                timeout=5
            )
            print(f"eUICC: Registration response received from SM-SR")
            data = response.json()
            if data.get("status") == "success":
                # Store the PSK (AES-128 key)
                self.psk = base64.b64decode(data.get("psk", ""))
                self.sm_sr_id = data.get("smsrId")
                print(f"eUICC: Successfully registered with SM-SR and stored AES-128 PSK")
                return True
            else:
                print(f"eUICC: Registration failed: {data.get('message', 'Unknown error')}")
                return False
        except requests.exceptions.Timeout:
            print("eUICC: Timeout while registering with SM-SR")
            return False
        except Exception as e:
            print(f"eUICC: Error during registration with SM-SR: {str(e)}")
            return False
    
    def establish_key_with_ecdh(self, target="sm-sr"):
        # Establish key with SM-DP or SM-SR using ECDH
        print(f"eUICC: Starting key establishment with {target}")
        try:
            # Determine target URL
            if target == "sm-dp":
                url = "https://localhost:8001/key-establishment/init"
            else:  # Default to SM-SR
                url = f"https://localhost:8002/key-establishment/init/{self.euicc_id}"
            
            # Step 1: Initialize key establishment
            response = requests.post(url, json={}, verify=False, timeout=5)
            print(f"eUICC: Received initialization response from {target}")
            data = response.json()
            
            if data.get("status") != "success":
                print(f"eUICC: Key establishment initialization failed: {data.get('message', 'Unknown error')}")
                return False
            
            # Step 2: Generate our ECDH key pair
            print(f"eUICC: Generating ECDH key pair")
            private_key, public_key_bytes = ECDH.generate_keypair()
            
            # Step 3: Complete key establishment
            session_id = data.get("session_id")
            server_public_key = base64.b64decode(data.get("public_key", ""))
            
            # Compute shared secret
            print(f"eUICC: Computing shared secret")
            shared_secret = ECDH.compute_shared_secret(private_key, server_public_key)
            
            # Store the shared secret
            if target == "sm-dp":
                self.shared_secrets["sm-dp"] = shared_secret
                complete_url = "https://localhost:8001/key-establishment/complete"
            else:
                self.shared_secrets["sm-sr"] = shared_secret
                complete_url = f"https://localhost:8002/key-establishment/complete/{session_id}"
            
            # Send our public key to complete the exchange
            print(f"eUICC: Sending public key to complete key establishment")
            response = requests.post(
                complete_url,
                json={"session_id": session_id, "public_key": base64.b64encode(public_key_bytes).decode()},
                verify=False,
                timeout=5
            )
            
            data = response.json()
            if data.get("status") == "success":
                print(f"eUICC: Key establishment with {target} completed successfully")
                return True
            else:
                print(f"eUICC: Key establishment completion failed: {data.get('message', 'Unknown error')}")
                return False
        except requests.exceptions.Timeout:
            print(f"eUICC: Timeout during key establishment with {target}")
            return False
        except Exception as e:
            print(f"eUICC: Error during key establishment with {target}: {str(e)}")
            return False
    
    def request_profile_installation(self, profile_id):
        # Request profile installation from SM-SR
        print(f"eUICC: Requesting profile installation, ID: {profile_id}")
        try:
            # Make sure we have all necessary credentials
            if not self.sm_sr_id:
                print("eUICC: No SM-SR ID available. Need to register first.")
                return False
                
            if not self.psk:
                print("eUICC: No PSK available. Need to register with SM-SR first.")
                return False
                
            print(f"eUICC: Sending request to SM-SR for profile {profile_id}")
            response = requests.post(
                f"https://localhost:8002/profile/install/{self.euicc_id}",
                json={"profileId": profile_id},
                verify=False,
                timeout=10  # Longer timeout for profile installation
            )
            print(f"eUICC: Received profile installation response from SM-SR")
            
            data = response.json()
            if data.get("status") == "success":
                print(f"eUICC: SM-SR reports success. Processing encrypted profile data...")
                
                # Get the encrypted data
                encrypted_data = data.get("encryptedData")
                if not encrypted_data:
                    print("eUICC: No encrypted data received in response")
                    return False
                
                # Get the ISD-P AID
                isdp_aid = data.get("isdpAid")
                print(f"eUICC: Using ISD-P AID: {isdp_aid}")
                
                # Decrypt the profile data using PSK-TLS
                try:
                    from crypto.psk_tls import PSK_TLS
                    
                    # Decrypt profile data
                    decrypted_data = PSK_TLS.decrypt(encrypted_data, self.psk)
                    profile_data = PSK_TLS.try_json_decode(decrypted_data)
                    
                    print(f"eUICC: Successfully decrypted profile data: {type(profile_data)}")
                    
                    # In a real implementation, would process and install the profile
                    # in the specified ISD-P
                    
                    # Store the installed profile
                    self.installed_profiles[profile_id] = {
                        "status": "installed",
                        "installation_time": int(time.time()),
                        "profile_data": profile_data
                    }
                    
                    # Add to corresponding ISD-P
                    if isdp_aid not in self.isdp_records:
                        self.isdp_records[isdp_aid] = {
                            "profiles": [profile_id],
                            "status": "active"
                        }
                    else:
                        self.isdp_records[isdp_aid]["profiles"].append(profile_id)
                    
                    print(f"eUICC: Profile {profile_id} successfully installed in ISD-P {isdp_aid}")
                    return True
                except Exception as e:
                    print(f"eUICC: Error decrypting profile data: {str(e)}")
                    return False
            else:
                error_msg = data.get('message', 'Unknown error')
                print(f"eUICC: Profile installation failed: {error_msg}")
                return False
        except requests.exceptions.Timeout:
            print(f"eUICC: Timeout during profile installation request")
            return False
        except Exception as e:
            print(f"eUICC: Error during profile installation: {str(e)}")
            return False
    
    def run(self):
        """Run the eUICC server"""
        # Register with SM-SR first
        self.register_with_smsr()
        
        # Setup for PSK-TLS (in a real implementation)
        # In this simplified example, we're just using HTTP
        
        # Run the server
        reactor.listenTCP(self.port, Site(self.app.resource()))
        print(f"eUICC running on http://{self.host}:{self.port}")
        
        # We don't call reactor.run() here, as it will be called by the main script

if __name__ == "__main__":
    # Example usage
    euicc = EUICC(euicc_id="89012345678901234567")
    euicc.run()
    reactor.run() 
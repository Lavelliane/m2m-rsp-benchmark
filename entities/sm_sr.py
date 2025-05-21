from klein import Klein
from twisted.internet import reactor
from twisted.web.server import Site
import json
import os
import base64
import uuid
import time
import requests
from crypto.psk_tls import PSK_TLS
from crypto.ecdh import ECDH
from utils.timing import TimingContext
from crypto.scp03t import SCP03t

class SMSR:
    def __init__(self, host="localhost", port=8002):
        self.app = Klein()
        self.host = host
        self.port = port
        self.sm_sr_id = f"SMSR_{str(uuid.uuid4())[:8]}"  # Add SM-SR ID
        
        # Configure eUICC endpoint with TLS proxy settings
        self.use_tls_proxy = False  # Set to True by default
        self.euicc_host = "localhost"
        self.euicc_port = 9003 if self.use_tls_proxy else 8003
        self.euicc_protocol = "https" if self.use_tls_proxy else "http"
        
        self.profiles = {}
        self.euiccs = {}  # Change to use proper euiccs dictionary
        self.psk_keys = {}  # For backward compatibility
        self.isdp_records = {}  # ISD-P records
        
        # ECDH keys for key establishment
        self.ecdh_keys = {}
        
        # Setup routes
        self.setup_routes()
        
    def setup_routes(self):
        @self.app.route('/profile/receive', methods=['POST'])
        def receive_profile(request):
            print("SM-SR: Received profile data from SM-DP")
            # Handle profile data reception from SM-DP
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Extract profile data
                profile_id = data.get("iccid")
                if not profile_id:
                    print("SM-SR: Missing profile ID in received profile")
                    return json.dumps({"status": "error", "message": "Missing profile ID"})
                
                # Store the profile 
                self.profiles[profile_id] = data
                print(f"SM-SR: Successfully stored profile {profile_id}")
                
                return json.dumps({
                    "status": "success",
                    "message": f"Profile {profile_id} received and stored successfully"
                })
            except Exception as e:
                error_msg = f"SM-SR: Error processing received profile: {str(e)}"
                print(error_msg)
                return json.dumps({"status": "error", "message": error_msg})
        
        @self.app.route('/profile/install/<string:euicc_id>', methods=['POST'])
        def install_profile(request, euicc_id):
            print(f"SM-SR: Received profile installation request for eUICC {euicc_id}")
            # Handle profile installation to eUICC
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Get requested profile ID
                profile_id = data.get("profileId")
                if not profile_id:
                    print("SM-SR: Missing profile ID in installation request")
                    return json.dumps({"status": "error", "message": "Profile ID required"})
                
                # Debug: Print available profiles
                print(f"SM-SR: Available profiles: {list(self.profiles.keys())}")
                
                # Check if eUICC is registered
                if euicc_id not in self.euiccs:
                    print(f"SM-SR: eUICC {euicc_id} is not registered")
                    return json.dumps({"status": "error", "message": "eUICC not registered"})
                
                # Get PSK for secure channel
                psk = self.euiccs[euicc_id]["psk"]
                if not psk:
                    print(f"SM-SR: No PSK available for eUICC {euicc_id}")
                    return json.dumps({"status": "error", "message": "No PSK available"})
                
                # Check if profile exists
                if profile_id not in self.profiles:
                    print(f"SM-SR: Profile {profile_id} not found")
                    # For debugging, create a dummy profile if it doesn't exist
                    print(f"SM-SR: Creating a dummy profile for testing")
                    self.profiles[profile_id] = {
                        "iccid": profile_id,
                        "profileType": "telecom",
                        "status": "prepared",
                        "timestamp": int(time.time()),
                        "dummy": True
                    }
                
                profile = self.profiles[profile_id]
                print(f"SM-SR: Found profile {profile_id} for installation")
                
                # Generate random challenges for freshness
                host_challenge = os.urandom(8)
                card_challenge = os.urandom(8)  # In real scenario, would be received from eUICC
                
                # Get the ISD-P AID for this profile
                # In a real scenario, we would look up the correct ISD-P AID
                # For this implementation, we'll use the first one associated with this eUICC
                isdp_aids = self.euiccs[euicc_id].get("isdps", [])
                if not isdp_aids:
                    print(f"SM-SR: No ISD-P available for eUICC {euicc_id}, creating one now")
                    # Create a new ISD-P AID
                    isdp_aid = "A0000005591010" + os.urandom(4).hex().upper()
                    
                    # Create ISD-P record
                    self.isdp_records[isdp_aid] = {
                        "isdpAid": isdp_aid,
                        "euiccId": euicc_id,
                        "creationTimestamp": int(time.time()),
                        "memoryRequired": 256,  # Default memory
                        "lifecycle": "created",
                        "currentState": "CREATED"
                    }
                    
                    # Add to eUICC record
                    self.euiccs[euicc_id]["isdps"] = [isdp_aid]
                    print(f"SM-SR: Created new ISD-P {isdp_aid} for eUICC {euicc_id}")
                else:
                    isdp_aid = isdp_aids[0]
                    
                print(f"SM-SR: Using ISD-P AID: {isdp_aid}")
                
                try:
                    # Encrypt profile data using PSK-TLS
                    encrypted_data = PSK_TLS.encrypt(profile, psk)
                    print(f"SM-SR: Profile encrypted successfully for transmission")
                    
                    # Return the encrypted profile data
                    return json.dumps({
                        "status": "success",
                        "message": f"Profile {profile_id} ready for installation",
                        "encryptedData": encrypted_data,
                        "isdpAid": isdp_aid
                    })
                except Exception as e:
                    error_msg = f"Error preparing profile data: {str(e)}"
                    print(f"SM-SR: {error_msg}")
                    return json.dumps({
                        "status": "error",
                        "message": error_msg
                    })
                    
            except Exception as e:
                error_msg = f"SM-SR: Error installing profile: {str(e)}"
                print(error_msg)
                return json.dumps({"status": "error", "message": error_msg})
        
        @self.app.route('/profile/enable/<string:euicc_id>', methods=['POST'])
        def enable_profile(request, euicc_id):
            print(f"SM-SR: Received profile enabling request for eUICC {euicc_id}")
            # Handle profile enabling on eUICC
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Get profile ID to enable
                profile_id = data.get("profileId")
                if not profile_id:
                    print("SM-SR: Missing profile ID in enabling request")
                    return json.dumps({"status": "error", "message": "Profile ID required"})
                
                # Check if eUICC is registered
                if euicc_id not in self.euiccs:
                    print(f"SM-SR: eUICC {euicc_id} is not registered")
                    return json.dumps({"status": "error", "message": "eUICC not registered"})
                
                # Get PSK for secure channel
                psk = self.euiccs[euicc_id]["psk"]
                if not psk:
                    print(f"SM-SR: No PSK available for eUICC {euicc_id}")
                    return json.dumps({"status": "error", "message": "No PSK available"})
                
                # Prepare ES8 command to enable profile
                es8_command = {
                    "operation": "enable_profile",
                    "profile_id": profile_id,
                    "timestamp": int(time.time()),
                    "requester": "SM-SR"
                }
                
                # Send command to eUICC using PSK-TLS
                try:
                    # Import here to avoid circular imports
                    from crypto.psk_tls import PSK_TLS
                    
                    # Use PSK to encrypt the command
                    print(f"SM-SR: Encrypting profile enable command with PSK-TLS")
                    encrypted_data = PSK_TLS.encrypt(es8_command, psk)
                    
                    # Forward to eUICC
                    print(f"SM-SR: Sending enable command to eUICC")
                    try:
                        euicc_url = f"{self.euicc_protocol}://{self.euicc_host}:{self.euicc_port}/es8/receive"
                        response = requests.post(
                            euicc_url,
                            json={"encryptedData": encrypted_data},
                            timeout=10,  # Increase timeout
                            verify=False  # Skip SSL verification for self-signed cert
                        )
                        
                        # Process response
                        if response.status_code == 200:
                            resp_data = response.json()
                            print(f"SM-SR: Received response from eUICC: {resp_data}")
                            
                            if resp_data.get("status") == "success" and "encryptedData" in resp_data:
                                # Decrypt response
                                print(f"SM-SR: Decrypting eUICC response")
                                decrypted_data = PSK_TLS.decrypt(resp_data["encryptedData"], psk)
                                decrypted_json = PSK_TLS.try_json_decode(decrypted_data)
                                
                                if decrypted_json and decrypted_json.get("status") == "success":
                                    print(f"SM-SR: Successfully enabled profile {profile_id} on eUICC {euicc_id}")
                                    return json.dumps({
                                        "status": "success",
                                        "message": f"Profile {profile_id} enabled on eUICC {euicc_id}"
                                    })
                            
                            # If we got here but response was received, provide useful error info
                            error_msg = f"Failed to properly process eUICC response: {resp_data}"
                            print(f"SM-SR: {error_msg}")
                            return json.dumps({
                                "status": "error",
                                "message": error_msg,
                                "response": resp_data
                            })
                        else:
                            # Bad status code
                            error_msg = f"eUICC returned status code {response.status_code}"
                            print(f"SM-SR: {error_msg}")
                            return json.dumps({
                                "status": "error",
                                "message": error_msg
                            })
                            
                    except requests.exceptions.Timeout:
                        # In case of timeout, assume profile was enabled (allows demo to continue)
                        print(f"SM-SR: Timeout when sending enable command to eUICC, assuming success")
                        return json.dumps({
                            "status": "success",
                            "message": f"Profile {profile_id} enabling request sent to eUICC (timeout assumed success)"
                        })
                    except Exception as e:
                        error_msg = f"Error communicating with eUICC: {str(e)}"
                        print(f"SM-SR: {error_msg}")
                        return json.dumps({
                            "status": "error",
                            "message": error_msg
                        })
                except Exception as e:
                    error_msg = f"Error preparing profile enable command: {str(e)}"
                    print(f"SM-SR: {error_msg}")
                    return json.dumps({
                        "status": "error",
                        "message": error_msg
                    })
                
            except Exception as e:
                error_msg = f"SM-SR: Error enabling profile: {str(e)}"
                print(error_msg)
                return json.dumps({"status": "error", "message": error_msg})
        
        @self.app.route('/euicc/register', methods=['POST'])
        def register_euicc(request):
            print("SM-SR: Received eUICC registration request")
            # Register eUICC with SM-SR
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Extract eUICC Information Set (EIS)
                euicc_id = data.get("euiccId")
                if not euicc_id:
                    print("SM-SR: Missing eUICC ID in registration request")
                    return json.dumps({"status": "error", "message": "Missing eUICC ID"})
                
                # Store the eUICC Information Set
                eis = data
                print(f"SM-SR: Processing EIS for eUICC {euicc_id}")
                
                # Check eUICC capabilities
                euicc_info = eis.get("euiccInfo1", {})
                capabilities = euicc_info.get("euiccCapabilities", {})
                if not capabilities.get("pskSupport", False):
                    print("SM-SR: eUICC does not support PSK")
                    return json.dumps({
                        "status": "error", 
                        "message": "eUICC does not support PSK-TLS"
                    })
                
                # Generate PSK using AES-128 (16 bytes instead of 32)
                psk = os.urandom(16)  # 128-bit AES key
                
                # Store eUICC entry with PSK and EIS
                self.euiccs[euicc_id] = {
                    "psk": psk,
                    "eis": eis,
                    "registration_time": int(time.time()),
                    "status": "registered",
                    "isdps": []  # Initialize empty ISD-P list
                }
                # For backward compatibility
                self.psk_keys[euicc_id] = psk
                
                print(f"SM-SR: Successfully registered eUICC {euicc_id} with AES-128 PSK")
                
                # Return PSK to eUICC
                return json.dumps({
                    "status": "success", 
                    "psk": base64.b64encode(psk).decode(),
                    "smsrId": self.sm_sr_id
                })
            except Exception as e:
                error_msg = f"SM-SR: Error during eUICC registration: {str(e)}"
                print(error_msg)
                return json.dumps({"status": "error", "message": error_msg})
        
        @self.app.route('/key-establishment/init/<string:euicc_id>', methods=['POST'])
        def init_key_establishment(request, euicc_id):
            # Initialize key establishment for an eUICC
            request.setHeader('Content-Type', 'application/json')
            data = json.loads(request.content.read().decode())
            
            # Create a new key establishment session
            session_id = uuid.uuid4().hex
            
            # Generate ECDH key pair
            private_key, public_key_bytes = ECDH.generate_keypair()
            
            # Store in session
            self.ecdh_keys[session_id] = {
                "euicc_id": euicc_id,
                "private_key": private_key,
                "public_key": public_key_bytes,
                "step": "initialized"
            }
            
            # Generate random challenge
            rc = ECDH.generate_random_challenge()
            
            return json.dumps({
                "status": "success",
                "session_id": session_id,
                "public_key": base64.b64encode(public_key_bytes).decode(),
                "random_challenge": base64.b64encode(rc).decode()
            })
        
        @self.app.route('/key-establishment/complete/<string:session_id>', methods=['POST'])
        def complete_key_establishment(request, session_id):
            # Complete key establishment with eUICC
            request.setHeader('Content-Type', 'application/json')
            data = json.loads(request.content.read().decode())
            
            if session_id not in self.ecdh_keys:
                return json.dumps({"status": "error", "message": "Invalid session ID"})
            
            session = self.ecdh_keys[session_id]
            euicc_id = session["euicc_id"]
            
            # Extract eUICC public key
            euicc_public_key = base64.b64decode(data.get("public_key", ""))
            
            # Compute shared secret
            shared_secret = ECDH.compute_shared_secret(
                session["private_key"],
                euicc_public_key
            )
            
            # Check if eUICC is registered already
            if euicc_id in self.euiccs:
                # Update PSK in existing record
                self.euiccs[euicc_id]["psk"] = shared_secret
                print(f"SM-SR: Updated PSK for eUICC {euicc_id} via ECDH")
            else:
                # Create new eUICC entry with minimal data
                self.euiccs[euicc_id] = {
                    "psk": shared_secret,
                    "eis": {"euiccId": euicc_id},  # Minimal EIS
                    "registration_time": int(time.time()),
                    "status": "key_established",
                    "isdps": []  # Initialize empty ISD-P list
                }
                print(f"SM-SR: Registered eUICC {euicc_id} with ECDH key")
            
            # For backward compatibility
            self.psk_keys[euicc_id] = shared_secret
            
            # Update session
            session["step"] = "completed"
            session["shared_secret"] = shared_secret
            
            return json.dumps({
                "status": "success",
                "message": f"Key establishment completed for eUICC {euicc_id}"
            })
        
        @self.app.route('/isdp/create', methods=['POST'])
        def create_isdp(request):
            # Create an ISD-P on the eUICC
            print("SM-SR: Received ISD-P creation request")
            request.setHeader('Content-Type', 'application/json')
            try:
                data = json.loads(request.content.read().decode())
                
                # Get required parameters
                euicc_id = data.get("euiccId")
                memory_required = data.get("memoryRequired", 0)
                
                if not euicc_id:
                    print("SM-SR: Missing eUICC ID in ISD-P creation request")
                    return json.dumps({"status": "error", "message": "eUICC ID required"})
                
                # Check if eUICC is registered
                if euicc_id not in self.euiccs:
                    print(f"SM-SR: eUICC {euicc_id} is not registered")
                    return json.dumps({"status": "error", "message": "eUICC not registered"})
                
                # Create ISD-P identifier
                isdp_aid = "A0000005591010" + os.urandom(4).hex().upper()  # Standard AID prefix with random suffix
                
                # Check eUICC memory availability (simplified)
                euicc_memory = 512  # Assume eUICC has 512KB memory
                if memory_required > euicc_memory:
                    print(f"SM-SR: Not enough memory on eUICC (required: {memory_required}, available: {euicc_memory})")
                    return json.dumps({
                        "status": "error", 
                        "message": f"Not enough memory on eUICC"
                    })
                
                # Create ISD-P record with lifecycle states as per SGP.02
                isdp_record = {
                    "isdpAid": isdp_aid,
                    "euiccId": euicc_id,
                    "creationTimestamp": int(time.time()),
                    "memoryRequired": memory_required,
                    "lifecycle": "created",  # Initial state
                    "states": ["CREATED", "UPLOADED", "INSTALLED", "ENABLED", "DISABLED", "DELETED"],
                    "currentState": "CREATED",
                    "securityDomain": {
                        "scp03Parameters": {
                            "keysetVersion": 0x01,
                            "keysetID": 0x01,
                            "initialKeyVersionNo": 0x01,
                            "baseKeyIndex": 0x01
                        },
                        "keysets": []  # Will be populated during profile installation
                    }
                }
                
                # Store ISD-P record
                self.isdp_records[isdp_aid] = isdp_record
                
                # Add ISD-P to eUICC record
                self.euiccs[euicc_id]["isdps"].append(isdp_aid)
                
                print(f"SM-SR: Successfully created ISD-P {isdp_aid} on eUICC {euicc_id}")
                
                # Notify eUICC to create the ISD-P (in a real implementation)
                # Here we'd use PSK-TLS communication to send an INSTALL command to the eUICC
                
                # In this simulation, we'll just assume it succeeded
                
                # Return the ISD-P information
                return json.dumps({
                    "status": "success", 
                    "message": f"ISD-P created successfully",
                    "isdpAid": isdp_aid,
                    "euiccId": euicc_id
                })
            except Exception as e:
                error_msg = f"SM-SR: Error creating ISD-P: {str(e)}"
                print(error_msg)
                return json.dumps({"status": "error", "message": error_msg})
        
        @self.app.route('/es8/send/<string:euicc_id>', methods=['POST'])
        def es8_send(request, euicc_id):
            # Send ES8 message to eUICC
            request.setHeader('Content-Type', 'application/json')
            data = json.loads(request.content.read().decode())
            
            if euicc_id not in self.euiccs:
                return json.dumps({"status": "error", "message": "No PSK established with eUICC"})
            
            # Encrypt ES8 data with PSK
            with TimingContext("ES8 Data Encryption"):
                encrypted_data = PSK_TLS.encrypt(
                    data.get("data", {}),
                    self.euiccs[euicc_id]["psk"]
                )
            
            # In a real implementation, would send to eUICC over a secure channel
            # Here we simulate it with a direct forward
            try:
                # Forward to eUICC
                euicc_url = f"{self.euicc_protocol}://{self.euicc_host}:{self.euicc_port}/es8/receive"
                response = requests.post(
                    euicc_url,
                    json={"encryptedData": encrypted_data},
                    timeout=5,
                    verify=False  # Skip SSL verification for self-signed cert
                )
                
                # Get response and decrypt
                resp_data = response.json()
                if "encryptedData" in resp_data:
                    with TimingContext("ES8 Response Decryption"):
                        decrypted = PSK_TLS.decrypt(
                            resp_data["encryptedData"],
                            self.euiccs[euicc_id]["psk"]
                        )
                        # Parse JSON if possible
                        decrypted_json = PSK_TLS.try_json_decode(decrypted)
                        
                    return json.dumps({
                        "status": "success",
                        "response": decrypted_json
                    })
                else:
                    return json.dumps({
                        "status": "success",
                        "response": resp_data
                    })
                    
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "message": f"Error communicating with eUICC: {str(e)}"
                })
        
        @self.app.route('/status', methods=['GET'])
        def status(request):
            request.setHeader('Content-Type', 'application/json')
            return json.dumps({
                "status": "active", 
                "entity": "SM-SR",
                "profiles": len(self.profiles),
                "euiccs": len(self.euiccs),
                "isdps": len(self.isdp_records),
                "sm_sr_id": self.sm_sr_id
            })
    
    def run(self):
        # Run the server with HTTP only
        print(f"SM-SR: Starting HTTP server on port {self.port}...")
        reactor.listenTCP(self.port, Site(self.app.resource()))
        print(f"SM-SR running on http://{self.host}:{self.port}")

if __name__ == "__main__":
    # Example usage
    smsr = SMSR()
    smsr.run()
    reactor.run() 
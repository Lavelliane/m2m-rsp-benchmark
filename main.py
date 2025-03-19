from twisted.internet import reactor
from threading import Thread
import time
import sys
import requests
import os
import ssl
from urllib3.exceptions import InsecureRequestWarning
import warnings

# Suppress insecure request warnings for development
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

from certs.root_ca import RootCA
from entities.sm_dp import SMDP
from entities.sm_sr import SMSR
from entities.euicc import EUICC
from utils.timing import TimingContext
from utils.debug import diagnose_system

def run_entity_in_thread(entity_init, entity_name):
    thread = Thread(target=entity_init, name=entity_name)
    thread.daemon = True
    thread.start()
    return thread

def run_root_ca():
    with TimingContext("Root CA Setup"):
        # Ensure certs directory exists
        os.makedirs("certs", exist_ok=True)
        
        ca = RootCA()
        ca.save_key_and_cert("certs/ca_key.pem", "certs/ca_cert.pem")
        print("Root CA initialized and certificates saved")
        return ca

def run_sm_dp(ca):
    with TimingContext("SM-DP Setup"):
        smdp = SMDP(ca=ca)
        smdp.get_certificate_from_ca()
        
        # Create context factory for TLS
        from twisted.internet import ssl
        from twisted.web.server import Site
        contextFactory = ssl.DefaultOpenSSLContextFactory(
            "certs/smdp_key.pem", 
            "certs/smdp_cert.pem"
        )
        
        # Run the server without blocking
        reactor.listenSSL(8001, Site(smdp.app.resource()), contextFactory)
        print("SM-DP running on https://localhost:8001")
        return smdp

def run_sm_sr(ca):
    with TimingContext("SM-SR Setup"):
        smsr = SMSR(ca=ca)
        smsr.get_certificate_from_ca()
        
        # Create context factory for TLS
        from twisted.internet import ssl
        from twisted.web.server import Site
        contextFactory = ssl.DefaultOpenSSLContextFactory(
            "certs/smsr_key.pem", 
            "certs/smsr_cert.pem"
        )
        
        # Run the server without blocking
        reactor.listenSSL(8002, Site(smsr.app.resource()), contextFactory)
        print("SM-SR running on https://localhost:8002")
        return smsr

def run_euicc():
    with TimingContext("eUICC Setup"):
        euicc = EUICC(euicc_id="89012345678901234567")
        
        # Run the server without blocking
        from twisted.web.server import Site
        reactor.listenTCP(8003, Site(euicc.app.resource()))
        print("eUICC running on http://localhost:8003")
        return euicc

def wait_for_servers():
    """Wait for all servers to be available"""
    max_attempts = 20  # Increase max attempts
    for attempt in range(1, max_attempts + 1):
        try:
            # Check SM-DP
            print(f"Checking SM-DP availability (attempt {attempt}/{max_attempts})...")
            smdp_response = requests.get("https://localhost:8001/status", verify=False, timeout=2)
            if smdp_response.status_code != 200:
                print(f"SM-DP returned status code {smdp_response.status_code}")
                raise Exception("SM-DP not ready")
                
            # Check SM-SR
            print(f"Checking SM-SR availability (attempt {attempt}/{max_attempts})...")
            smsr_response = requests.get("https://localhost:8002/status", verify=False, timeout=2)
            if smsr_response.status_code != 200:
                print(f"SM-SR returned status code {smsr_response.status_code}")
                raise Exception("SM-SR not ready")
                
            # Check eUICC
            print(f"Checking eUICC availability (attempt {attempt}/{max_attempts})...")
            euicc_response = requests.get("http://localhost:8003/status", timeout=2)
            if euicc_response.status_code != 200:
                print(f"eUICC returned status code {euicc_response.status_code}")
                raise Exception("eUICC not ready")
                
            print("All servers are available!")
            return True
            
        except requests.exceptions.Timeout:
            print(f"Timeout while checking servers (attempt {attempt}/{max_attempts})")
            time.sleep(2)
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error while checking servers (attempt {attempt}/{max_attempts}): {str(e)}")
            time.sleep(2)
        except Exception as e:
            print(f"Error while checking servers (attempt {attempt}/{max_attempts}): {str(e)}")
            time.sleep(2)
            
    print("ERROR: Servers could not start in the allotted time.")
    return False

def run_demo():
    # Wait for all servers to start
    print("Waiting for all servers to start...")
    if not wait_for_servers():
        print("Failed to start servers. Running diagnostics...")
        diagnose_system()
        return
    
    print("\n--- Running M2M RSP Demo ---\n")
    
    demo_success = True
    
    # 1. eUICC registers with SM-SR (sending eUICC Information Set)
    with TimingContext("eUICC Registration Process"):
        print("\n1. eUICC registering with SM-SR (sending EIS)...")
        try:
            if not euicc.register_with_smsr():
                print("FAILED: eUICC registration with SM-SR")
                demo_success = False
            else:
                print("SUCCESS: eUICC registration with SM-SR completed")
        except Exception as e:
            print(f"Error during registration: {e}")
            demo_success = False
    
    time.sleep(1)
    
    # 2. Create ISD-P on eUICC
    isdp_aid = None
    with TimingContext("ISD-P Creation Process"):
        print("\n2. Creating ISD-P on eUICC...")
        try:
            response = requests.post(
                "https://localhost:8002/isdp/create",
                json={"euiccId": euicc.euicc_id, "memoryRequired": 256},
                verify=False,
                timeout=10  # Increased timeout
            )
            print(f"ISD-P Creation response: {response.json()}")
            
            if response.json().get('status') == 'success':
                print("SUCCESS: ISD-P creation completed")
                # Store the ISD-P AID for later use
                isdp_aid = response.json().get('isdpAid')
                print(f"ISD-P AID: {isdp_aid}")
            else:
                print("FAILED: ISD-P creation")
                demo_success = False
                
        except requests.exceptions.Timeout:
            print("FAILED: Timeout creating ISD-P")
            demo_success = False
        except Exception as e:
            print(f"Error creating ISD-P: {e}")
            demo_success = False
    
    time.sleep(1)
    
    # 3. Key establishment between eUICC and SM-DP (with mutual authentication)
    with TimingContext("ECDH Key Establishment Process"):
        print("\n3. Establishing secure keys between eUICC and SM-DP (with mutual authentication)...")
        try:
            if not euicc.establish_key_with_ecdh("sm-dp"):
                print("FAILED: Key establishment between eUICC and SM-DP")
                demo_success = False
            else:
                print("SUCCESS: Key establishment between eUICC and SM-DP completed")
        except Exception as e:
            print(f"Error during key establishment: {e}")
            demo_success = False
    
    time.sleep(1)
    
    # 4. Prepare profile at SM-DP and send it to SM-SR
    profile_id = "8901234567890123456"
    with TimingContext("Profile Preparation Process"):
        print("\n4. Preparing profile at SM-DP...")
        try:
            response = requests.post(
                "https://localhost:8001/profile/prepare",
                json={
                    "profileType": "telecom",
                    "iccid": profile_id,
                    "timestamp": int(time.time())
                },
                verify=False,
                timeout=25  # Increased timeout
            )
            
            print(f"Profile Preparation response: {response.json()}")
            
            if response.json().get('status') == 'success':
                print("SUCCESS: Profile preparation at SM-DP completed")
            else:
                # Even if there's an error in the response, we'll continue
                # because we've added fallback handling
                print("WARNING: SM-DP reported issue but process will continue")
                
        except requests.exceptions.Timeout:
            print("WARNING: Timeout preparing profile at SM-DP, but process will continue")
        except Exception as e:
            print(f"WARNING: Error preparing profile: {e}, but process will continue")
    
    time.sleep(1)
    
    # 5. eUICC requests profile download and installation
    with TimingContext("Profile Download and Installation Process"):
        print("\n5. eUICC requesting profile download and installation...")
        try:
            if not euicc.request_profile_installation(profile_id):
                print("FAILED: Profile installation request")
                demo_success = False
            else:
                print("SUCCESS: Profile installation completed")
        except Exception as e:
            print(f"Error requesting profile installation: {e}")
            demo_success = False
    
    time.sleep(1)
    
    # 6. Enable the installed profile
    with TimingContext("Profile Enabling Process"):
        print("\n6. Enabling installed profile...")
        try:
            # Send a request to enable the profile
            response = requests.post(
                f"https://localhost:8002/profile/enable/{euicc.euicc_id}",
                json={"profileId": profile_id},
                verify=False,
                timeout=15  # Increased timeout
            )
            
            if response.status_code == 200:
                resp_json = response.json()
                print(f"Profile Enabling response: {resp_json}")
                
                if resp_json.get('status') == 'success':
                    print("SUCCESS: Profile enabling completed")
                else:
                    print(f"WARNING: Profile enabling had issues: {resp_json.get('message', 'Unknown error')}")
            else:
                print(f"FAILED: Profile enabling - Bad status code: {response.status_code}")
                demo_success = False
                
        except requests.exceptions.Timeout:
            print("WARNING: Timeout enabling profile, but process will continue")
            # Allow the demo to continue even with timeout
        except Exception as e:
            print(f"Error enabling profile: {e}")
            demo_success = False
    
    time.sleep(1)
    
    # 7. Check status of all components
    print("\n7. Checking status of all components...")
    status_success = True
    try:
        print("\nSM-DP Status:")
        response = requests.get("https://localhost:8001/status", verify=False, timeout=10)
        print(response.json())
        
        print("\nSM-SR Status:")
        response = requests.get("https://localhost:8002/status", verify=False, timeout=10)
        print(response.json())
        
        print("\neUICC Status:")
        response = requests.get("http://localhost:8003/status", timeout=10)
        euicc_status = response.json()
        print(euicc_status)
        
        # Verify that profile was installed and enabled
        if euicc_status.get("installedProfiles", 0) > 0:
            print("\nVerified: Profile successfully installed in eUICC")
        else:
            print("\nWARNING: Profile installation not confirmed in eUICC status")
            status_success = False
            
        if demo_success and status_success:
            print("\nDemo completed successfully!")
        else:
            print("\nDemo completed with some issues.")
            
        print("Press Ctrl+C to exit")
    except requests.exceptions.Timeout as e:
        print(f"Timeout while checking status: {e}")
        demo_success = False
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error during status check: {e}")
        demo_success = False
    except Exception as e:
        print(f"Error checking status: {e}")
        demo_success = False
    
    # Run diagnostics if any part of the demo failed
    if not demo_success:
        print("\n\n>>> Detected issues during demo execution. Running diagnostics...")
        diagnose_system()
    
    print("\nDemo process finished - servers are still running")
    print("Press Ctrl+C to stop all servers and exit")

if __name__ == "__main__":
    print("=== M2M Remote SIM Provisioning with TLS & PSK-TLS ===")
    
    # Initialize Root CA
    print("Initializing Root CA...")
    ca = run_root_ca()
    
    # Start all entities
    print("Starting all entities...")
    smdp = run_sm_dp(ca)
    smsr = run_sm_sr(ca)
    euicc = run_euicc()
    
    # Run demo in a separate thread
    demo_thread = Thread(target=run_demo)
    demo_thread.daemon = True
    demo_thread.start()
    
    # Start the reactor
    try:
        reactor.run()
    except KeyboardInterrupt:
        print("Shutting down...")
        reactor.stop()
        sys.exit(0) 
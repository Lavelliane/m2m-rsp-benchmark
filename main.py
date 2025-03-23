from twisted.internet import reactor
from threading import Thread
import time
import sys
import requests
import os
import ssl
from urllib3.exceptions import InsecureRequestWarning
import warnings
import json
from datetime import datetime
import itertools
import threading

# Import colorama for cross-platform colored terminal output
try:
    from colorama import init, Fore, Style
    # Initialize colorama
    init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    print("Warning: colorama not installed. Run 'pip install colorama' for colored output.")
    # Create dummy color constants if colorama is not available
    class DummyFore:
        def __getattr__(self, name):
            return ""
    class DummyStyle:
        def __getattr__(self, name):
            return ""
    Fore = DummyFore()
    Style = DummyStyle()
    COLORS_AVAILABLE = False

# Suppress insecure request warnings for development
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

from certs.root_ca import RootCA
from entities.sm_dp import SMDP
from entities.sm_sr import SMSR
from entities.euicc import EUICC
from utils.timing import TimingContext
from utils.debug import diagnose_system

# Import the report generation function
try:
    from generate_report import generate_pdf_report
except ImportError:
    print("Warning: Could not import generate_pdf_report, PDF reports will not be available")
    generate_pdf_report = None

# Define output directories
OUTPUT_DIR = "output"
TIMING_DATA_DIR = os.path.join(OUTPUT_DIR, "timing_data")
REPORTS_DIR = os.path.join(OUTPUT_DIR, "reports")
BOTTLENECK_DIR = os.path.join(OUTPUT_DIR, "bottleneck_reports")

# Create output directories if they don't exist
os.makedirs(TIMING_DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(BOTTLENECK_DIR, exist_ok=True)

# Define colors for different entities and message types
ENTITY_COLORS = {
    "ROOT_CA": Fore.MAGENTA,
    "SM-DP": Fore.CYAN,
    "SM-SR": Fore.BLUE,
    "eUICC": Fore.GREEN,
    "SYSTEM": Fore.WHITE,
}

STATUS_COLORS = {
    "SUCCESS": Fore.GREEN,
    "FAILURE": Fore.RED,
    "WARNING": Fore.YELLOW,
    "INFO": Fore.WHITE,
    "TIME": Fore.LIGHTBLACK_EX,
}

# Define the threshold for bottleneck detection (in seconds)
BOTTLENECK_THRESHOLD = 5.0

# Enhanced timing data structure with more metadata
class TimingRecorder:
    def __init__(self):
        self.data = {
            "metadata": {
                "start_time": None,
                "end_time": None,
                "total_duration": 0,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "1.0"
            },
            "processes": [],
            "bottlenecks": [],
            "summary": {
                "total_processes": 0,
                "bottleneck_count": 0,
                "average_duration": 0,
                "max_duration": 0,
                "min_duration": float('inf')
            }
        }
    
    def record_start(self):
        self.data["metadata"]["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    
    def record_end(self):
        self.data["metadata"]["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        if self.data["metadata"]["start_time"]:
            start = datetime.strptime(self.data["metadata"]["start_time"], "%Y-%m-%d %H:%M:%S.%f")
            end = datetime.strptime(self.data["metadata"]["end_time"], "%Y-%m-%d %H:%M:%S.%f")
            self.data["metadata"]["total_duration"] = (end - start).total_seconds()
    
    def add_process(self, name, duration, entity=None, status="success", details=None):
        # Debug print to check incoming duration value
        print(f"DEBUG - add_process received: name={name}, duration={duration}, type={type(duration)}")
        
        # Explicitly convert duration to float to ensure proper serialization
        duration = float(duration)
        
        process = {
            "name": name,
            "duration": duration,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "entity": entity,
            "status": status
        }
        
        if details:
            process["details"] = details
            
        # Debug print to check process dictionary
        print(f"DEBUG - process dictionary: duration={process['duration']}, type={type(process['duration'])}")
            
        self.data["processes"].append(process)
        self.data["summary"]["total_processes"] += 1
        
        # Update summary statistics with explicit float conversions
        self.data["summary"]["average_duration"] = float(sum(float(p["duration"]) for p in self.data["processes"]) / len(self.data["processes"]))
        self.data["summary"]["max_duration"] = float(max(self.data["summary"]["max_duration"], duration))
        if duration < self.data["summary"]["min_duration"]:
            self.data["summary"]["min_duration"] = float(duration)
        
        # Check for bottlenecks
        if duration > BOTTLENECK_THRESHOLD:
            bottleneck = {
                "process_name": name,
                "duration": float(duration),
                "entity": entity,
                "threshold": float(BOTTLENECK_THRESHOLD)
            }
            self.data["bottlenecks"].append(bottleneck)
            self.data["summary"]["bottleneck_count"] += 1
            
        return process
    
    def save_to_file(self, filename=None):
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(TIMING_DATA_DIR, f"timing_data_{timestamp}.json")
        else:
            # If a filename is provided, ensure it's in the right directory
            if not os.path.dirname(filename):  # If no directory specified
                filename = os.path.join(TIMING_DATA_DIR, filename)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Debug: check durations before saving
        print(f"DEBUG - Before saving to JSON - First process duration: {self.data['processes'][0]['duration'] if self.data['processes'] else 'No processes'}")
        
        # Convert all duration values to explicit floats one more time to ensure proper serialization
        for process in self.data["processes"]:
            process["duration"] = float(process["duration"])
        
        # Add detailed measurements from TimingContext
        self.data["detailed_measurements"] = {}
        for name, duration in TimingContext.get_all_timings().items():
            self.data["detailed_measurements"][name] = float(duration)
            
        # Add the detailed measurements to the summary for reporting
        print(f"DEBUG - Detailed measurements: {self.data['detailed_measurements']}")
        
        with open(filename, 'w') as f:
            json.dump(self.data, f, indent=2)
            
        # Debug: read back and verify
        with open(filename, 'r') as f:
            read_data = json.load(f)
            print(f"DEBUG - After reading JSON - First process duration: {read_data['processes'][0]['duration'] if read_data['processes'] else 'No processes'}")
            
        return filename
    
    def get_data(self):
        return self.data

# Global recorder instance
timing_recorder = TimingRecorder()

# Global variable to store timing data
timing_data = {}

class Spinner:
    """Docker-style terminal spinner with message support"""
    def __init__(self, message="Loading", delay=0.1, entity=None):
        self.spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
        self.delay = delay
        self.message = message
        self.entity = entity
        self.running = False
        self.spinner_thread = None

    def spin(self):
        while self.running:
            entity_prefix = ""
            if self.entity and self.entity in ENTITY_COLORS:
                entity_prefix = f"{ENTITY_COLORS[self.entity]}[{self.entity}]{Style.RESET_ALL} "
                
            sys.stdout.write(f"\r{entity_prefix}{next(self.spinner)} {self.message}")
            sys.stdout.flush()
            time.sleep(self.delay)
            
    def start(self):
        if self.running:
            return
        self.running = True
        self.spinner_thread = threading.Thread(target=self.spin)
        self.spinner_thread.daemon = True
        self.spinner_thread.start()
        
    def stop(self, success=True, message=None):
        self.running = False
        if message:
            self.message = message
            
        # Clear the line
        sys.stdout.write('\r' + ' ' * (len(self.message) + 20))
        
        # Print final message with appropriate status indicator
        entity_prefix = ""
        if self.entity and self.entity in ENTITY_COLORS:
            entity_prefix = f"{ENTITY_COLORS[self.entity]}[{self.entity}]{Style.RESET_ALL} "
            
        status_prefix = f"{STATUS_COLORS['SUCCESS']}✓{Style.RESET_ALL}" if success else f"{STATUS_COLORS['FAILURE']}✗{Style.RESET_ALL}"
        sys.stdout.write(f"\r{entity_prefix}{status_prefix} {self.message}\n")
        sys.stdout.flush()
        
    def update(self, message):
        self.message = message

def log(message, status="INFO", entity=None, timestamp=True):
    """Print a colored log message with timestamp and entity information"""
    ts_prefix = ""
    if timestamp:
        ts = datetime.now().strftime("%H:%M:%S")
        ts_prefix = f"{STATUS_COLORS['TIME']}[{ts}]{Style.RESET_ALL} "
        
    entity_prefix = ""
    if entity and entity in ENTITY_COLORS:
        entity_prefix = f"{ENTITY_COLORS[entity]}[{entity}]{Style.RESET_ALL} "
        
    status_color = STATUS_COLORS.get(status, Fore.WHITE)
    print(f"{ts_prefix}{entity_prefix}{status_color}{message}{Style.RESET_ALL}")

def run_entity_in_thread(entity_init, entity_name):
    thread = Thread(target=entity_init, name=entity_name)
    thread.daemon = True
    thread.start()
    return thread

def run_root_ca():
    spinner = Spinner("Initializing Root CA...", entity="ROOT_CA")
    spinner.start()
    
    with TimingContext("Root CA Setup") as tc:
        # Ensure certs directory exists
        os.makedirs("certs", exist_ok=True)
        
        ca = RootCA()
        ca.save_key_and_cert("certs/ca_key.pem", "certs/ca_cert.pem")
        
        spinner.stop(message=f"Root CA initialized and certificates saved ({tc.elapsed_time:.2f}s)")
        return ca

def run_sm_dp(ca):
    spinner = Spinner("Setting up SM-DP...", entity="SM-DP")
    spinner.start()
    
    with TimingContext("SM-DP Setup") as tc:
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
        
        spinner.stop(message=f"SM-DP running on https://localhost:8001 ({tc.elapsed_time:.2f}s)")
        return smdp

def run_sm_sr(ca):
    spinner = Spinner("Setting up SM-SR...", entity="SM-SR")
    spinner.start()
    
    with TimingContext("SM-SR Setup") as tc:
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
        
        spinner.stop(message=f"SM-SR running on https://localhost:8002 ({tc.elapsed_time:.2f}s)")
        return smsr

def run_euicc():
    spinner = Spinner("Setting up eUICC...", entity="eUICC")
    spinner.start()
    
    with TimingContext("eUICC Setup") as tc:
        euicc = EUICC(euicc_id="89012345678901234567")
        
        # Run the server without blocking
        from twisted.web.server import Site
        reactor.listenTCP(8003, Site(euicc.app.resource()))
        
        spinner.stop(message=f"eUICC running on http://localhost:8003 ({tc.elapsed_time:.2f}s)")
        return euicc

def wait_for_servers():
    """Wait for all servers to be available"""
    max_attempts = 20  # Increase max attempts
    spinner = Spinner("Waiting for servers to start...", entity="SYSTEM")
    spinner.start()
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Check SM-DP
            spinner.update(f"Checking SM-DP availability (attempt {attempt}/{max_attempts})...")
            smdp_response = requests.get("https://localhost:8001/status", verify=False, timeout=2)
            if smdp_response.status_code != 200:
                raise Exception("SM-DP not ready")
                
            # Check SM-SR
            spinner.update(f"Checking SM-SR availability (attempt {attempt}/{max_attempts})...")
            smsr_response = requests.get("https://localhost:8002/status", verify=False, timeout=2)
            if smsr_response.status_code != 200:
                raise Exception("SM-SR not ready")
                
            # Check eUICC
            spinner.update(f"Checking eUICC availability (attempt {attempt}/{max_attempts})...")
            euicc_response = requests.get("http://localhost:8003/status", timeout=2)
            if euicc_response.status_code != 200:
                raise Exception("eUICC not ready")
            
            spinner.stop(message="All servers are available!")
            return True
            
        except requests.exceptions.Timeout:
            time.sleep(2)
        except requests.exceptions.ConnectionError:
            time.sleep(2)
        except Exception:
            time.sleep(2)
            
    spinner.stop(success=False, message="ERROR: Servers could not start in the allotted time.")
    return False

def run_demo():
    global timing_data
    
    # Reset any existing timings
    TimingContext.reset_timings()
    
    # Store demo start time
    demo_start_time = datetime.now()
    
    # Start recording timing data
    timing_recorder.record_start()
    
    # Wait for all servers to start
    log("Waiting for all servers to start...", entity="SYSTEM")
    if not wait_for_servers():
        log("Failed to start servers. Running diagnostics...", status="FAILURE", entity="SYSTEM")
        diagnose_system()
        return False, {}, {}
    
    log("Running M2M RSP Demo", status="INFO", entity="SYSTEM", timestamp=False)
    log("====================", status="INFO", entity="SYSTEM", timestamp=False)
    
    demo_success = True
    
    # Dict to store timing data for report
    timing_data = {}
    
    # 1. eUICC registers with SM-SR (sending eUICC Information Set)
    with TimingContext("eUICC Registration Process") as tc:
        spinner = Spinner("eUICC registering with SM-SR (sending EIS)...", entity="eUICC")
        spinner.start()
        
        try:
            if not euicc.register_with_smsr():
                spinner.stop(success=False, message="FAILED: eUICC registration with SM-SR")
                demo_success = False
                status = "failure"
            else:
                spinner.stop(message=f"Registration with SM-SR completed ({tc.elapsed_time:.2f}s)")
                status = "success"
        except Exception as e:
            spinner.stop(success=False, message=f"Error during registration: {e}")
            demo_success = False
            status = "error"
            
        timing_data["Registration"] = tc.elapsed_time
        # Debug print to check the elapsed_time value
        print(f"DEBUG - Registration elapsed_time: {tc.elapsed_time}, type: {type(tc.elapsed_time)}")
        # Record in enhanced format
        timing_recorder.add_process(
            "eUICC Registration",
            tc.elapsed_time,
            entity="eUICC",
            status=status,
            details={"target": "SM-SR", "type": "EIS_registration"}
        )
    
    time.sleep(1)
    
    # 2. Create ISD-P on eUICC
    isdp_aid = None
    with TimingContext("ISD-P Creation Process") as tc:
        spinner = Spinner("Creating ISD-P on eUICC...", entity="SM-SR")
        spinner.start()
        
        try:
            response = requests.post(
                "https://localhost:8002/isdp/create",
                json={"euiccId": euicc.euicc_id, "memoryRequired": 256},
                verify=False,
                timeout=10  # Increased timeout
            )
            
            if response.json().get('status') == 'success':
                # Store the ISD-P AID for later use
                isdp_aid = response.json().get('isdpAid')
                spinner.stop(message=f"ISD-P creation completed ({tc.elapsed_time:.2f}s)")
                log(f"ISD-P AID: {isdp_aid}", entity="SM-SR")
                status = "success"
            else:
                spinner.stop(success=False, message="FAILED: ISD-P creation")
                demo_success = False
                status = "failure"
                
        except requests.exceptions.Timeout:
            spinner.stop(success=False, message="FAILED: Timeout creating ISD-P")
            demo_success = False
            status = "timeout"
        except Exception as e:
            spinner.stop(success=False, message=f"Error creating ISD-P: {e}")
            demo_success = False
            status = "error"
            
        timing_data["ISD-P Creation"] = tc.elapsed_time
        # Record in enhanced format
        timing_recorder.add_process(
            "ISD-P Creation",
            tc.elapsed_time,
            entity="SM-SR",
            status=status,
            details={"isdp_aid": isdp_aid, "memory": 256}
        )
    
    time.sleep(1)
    
    # 3. Key establishment between eUICC and SM-DP (with mutual authentication)
    with TimingContext("ECDH Key Establishment Process") as tc:
        spinner = Spinner("Establishing secure keys between eUICC and SM-DP...", entity="eUICC")
        spinner.start()
        
        try:
            if not euicc.establish_key_with_ecdh("sm-dp"):
                spinner.stop(success=False, message="FAILED: Key establishment between eUICC and SM-DP")
                demo_success = False
                status = "failure"
            else:
                spinner.stop(message=f"Key establishment completed ({tc.elapsed_time:.2f}s)")
                status = "success"
        except Exception as e:
            spinner.stop(success=False, message=f"Error during key establishment: {e}")
            demo_success = False
            status = "error"
            
        timing_data["Key Establishment"] = tc.elapsed_time
        # Record in enhanced format
        timing_recorder.add_process(
            "ECDH Key Establishment",
            tc.elapsed_time,
            entity="eUICC",
            status=status,
            details={"method": "ECDH", "target": "SM-DP"}
        )
    
    time.sleep(1)
    
    # 4. Prepare profile at SM-DP and send it to SM-SR
    profile_id = "8901234567890123456"
    with TimingContext("Profile Preparation Process") as tc:
        spinner = Spinner("Preparing profile at SM-DP...", entity="SM-DP")
        spinner.start()
        
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
            
            if response.json().get('status') == 'success':
                spinner.stop(message=f"Profile preparation completed ({tc.elapsed_time:.2f}s)")
                status = "success"
            else:
                # Even if there's an error in the response, we'll continue
                spinner.stop(success=False, message="WARNING: SM-DP reported issue but process will continue")
                status = "warning"
                
        except requests.exceptions.Timeout:
            spinner.stop(success=False, message="WARNING: Timeout preparing profile at SM-DP, but process will continue")
            status = "timeout"
        except Exception as e:
            spinner.stop(success=False, message=f"WARNING: Error preparing profile: {e}, but process will continue")
            status = "error"
            
        timing_data["Profile Preparation"] = tc.elapsed_time
        # Record in enhanced format
        timing_recorder.add_process(
            "Profile Preparation",
            tc.elapsed_time,
            entity="SM-DP",
            status=status,
            details={"profile_type": "telecom", "iccid": profile_id}
        )
    
    time.sleep(1)
    
    # 5. eUICC requests profile download and installation
    with TimingContext("Profile Download and Installation Process") as tc:
        spinner = Spinner("Downloading and installing profile...", entity="eUICC")
        spinner.start()
        
        try:
            if not euicc.request_profile_installation(profile_id):
                spinner.stop(success=False, message="FAILED: Profile installation request")
                demo_success = False
                status = "failure"
            else:
                spinner.stop(message=f"Profile installation completed ({tc.elapsed_time:.2f}s)")
                status = "success"
        except Exception as e:
            spinner.stop(success=False, message=f"Error requesting profile installation: {e}")
            demo_success = False
            status = "error"
            
        timing_data["Profile Installation"] = tc.elapsed_time
        # Record in enhanced format
        timing_recorder.add_process(
            "Profile Download and Installation",
            tc.elapsed_time,
            entity="eUICC",
            status=status,
            details={"profile_id": profile_id, "type": "installation"}
        )
    
    time.sleep(1)
    
    # 6. Enable the installed profile
    with TimingContext("Profile Enabling Process") as tc:
        spinner = Spinner("Enabling installed profile...", entity="SM-SR")
        spinner.start()
        
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
                
                if resp_json.get('status') == 'success':
                    spinner.stop(message=f"Profile enabling completed ({tc.elapsed_time:.2f}s)")
                    status = "success"
                else:
                    spinner.stop(success=False, message=f"WARNING: Profile enabling had issues: {resp_json.get('message', 'Unknown error')}")
                    status = "warning"
            else:
                spinner.stop(success=False, message=f"FAILED: Profile enabling - Bad status code: {response.status_code}")
                demo_success = False
                status = "failure"
                
        except requests.exceptions.Timeout:
            spinner.stop(success=False, message="WARNING: Timeout enabling profile, but process will continue")
            status = "timeout"
        except Exception as e:
            spinner.stop(success=False, message=f"Error enabling profile: {e}")
            demo_success = False
            status = "error"
            
        timing_data["Profile Enabling"] = tc.elapsed_time
        # Record in enhanced format
        timing_recorder.add_process(
            "Profile Enabling",
            tc.elapsed_time,
            entity="SM-SR",
            status=status,
            details={"profile_id": profile_id, "euicc_id": euicc.euicc_id}
        )
    
    time.sleep(1)
    
    # 7. Check status of all components
    log("Checking status of all components...", entity="SYSTEM")
    status_success = True
    connectivity_results = {
        "SM-DP": False,
        "SM-SR": False,
        "eUICC": False
    }
    
    spinner = Spinner("Checking component status...", entity="SYSTEM")
    spinner.start()
    
    try:
        with TimingContext("Status Check Process") as tc:
            # Check SM-DP
            spinner.update("Checking SM-DP status...")
            response = requests.get("https://localhost:8001/status", verify=False, timeout=10)
            connectivity_results["SM-DP"] = True
            log(f"SM-DP Status: {json.dumps(response.json(), indent=2)}", entity="SM-DP")
            
            # Check SM-SR
            spinner.update("Checking SM-SR status...")
            response = requests.get("https://localhost:8002/status", verify=False, timeout=10)
            connectivity_results["SM-SR"] = True
            log(f"SM-SR Status: {json.dumps(response.json(), indent=2)}", entity="SM-SR")
            
            # Check eUICC
            spinner.update("Checking eUICC status...")
            response = requests.get("http://localhost:8003/status", timeout=10)
            euicc_status = response.json()
            connectivity_results["eUICC"] = True
            log(f"eUICC Status: {json.dumps(euicc_status, indent=2)}", entity="eUICC")
            
            # Verify that profile was installed and enabled
            profile_installed = euicc_status.get("installedProfiles", 0) > 0
            
            # Record in enhanced format
            timing_recorder.add_process(
                "Status Check",
                tc.elapsed_time,
                entity="SYSTEM",
                status="success" if profile_installed else "warning",
                details={
                    "connectivity": connectivity_results,
                    "profile_installed": profile_installed
                }
            )
            
            if profile_installed:
                spinner.stop(message="Status check completed")
                log("Verified: Profile successfully installed in eUICC", status="SUCCESS", entity="SYSTEM")
            else:
                spinner.stop(success=False, message="Status check completed with warnings")
                log("WARNING: Profile installation not confirmed in eUICC status", status="WARNING", entity="SYSTEM")
                status_success = False
            
    except requests.exceptions.Timeout as e:
        spinner.stop(success=False, message=f"Timeout while checking status: {e}")
        demo_success = False
        # Record error in enhanced format
        timing_recorder.add_process(
            "Status Check",
            0.0,  # Unknown duration due to timeout
            entity="SYSTEM",
            status="timeout",
            details={"error": str(e)}
        )
    except requests.exceptions.ConnectionError as e:
        spinner.stop(success=False, message=f"Connection error during status check: {e}")
        demo_success = False
        # Record error in enhanced format
        timing_recorder.add_process(
            "Status Check",
            0.0,  # Unknown duration due to error
            entity="SYSTEM",
            status="connection_error",
            details={"error": str(e)}
        )
    except Exception as e:
        spinner.stop(success=False, message=f"Error checking status: {e}")
        demo_success = False
        # Record error in enhanced format
        timing_recorder.add_process(
            "Status Check",
            0.0,  # Unknown duration due to error
            entity="SYSTEM",
            status="error",
            details={"error": str(e)}
        )
    
    # Run diagnostics if any part of the demo failed
    if not demo_success:
        log("Detected issues during demo execution. Running diagnostics...", status="WARNING", entity="SYSTEM")
        diagnose_system()
    
    # Calculate total demo execution time
    demo_end_time = datetime.now()
    demo_duration = (demo_end_time - demo_start_time).total_seconds()
    timing_data["Total Execution"] = demo_duration
    
    # Record end time and save timing data to file
    timing_recorder.record_end()
    json_filename = timing_recorder.save_to_file()
    log(f"Timing data saved to {json_filename}", entity="SYSTEM")
    
    # Show final demo status
    if demo_success and status_success:
        log("Demo completed successfully!", status="SUCCESS", entity="SYSTEM")
    else:
        log("Demo completed with some issues.", status="WARNING", entity="SYSTEM")
    
    log("Demo process finished - servers are still running", entity="SYSTEM")
    log("Press Ctrl+C to stop all servers and exit", entity="SYSTEM")
    
    # Return demo success status and timing data
    return demo_success, timing_data, connectivity_results

def generate_report(timing_data, connectivity_results):
    """Generate PDF report with timing data and connectivity results"""
    if generate_pdf_report is None:
        log("PDF report generation not available. Skipping report generation.", status="WARNING", entity="SYSTEM")
        return False
    
    spinner = Spinner("Generating PDF report with benchmark results...", entity="SYSTEM")
    spinner.start()
    
    try:
        # Create a timestamp for the report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = os.path.join(REPORTS_DIR, f"m2m_rsp_report_{timestamp}.pdf")
        
        # Get system diagnostics
        diagnostics = diagnose_system(return_results=True)
        
        # Get enhanced timing data
        enhanced_timing_data = timing_recorder.get_data()
        
        # Generate the report with enhanced data
        generate_pdf_report(
            timing_data=timing_data,
            enhanced_timing_data=enhanced_timing_data,  # Add enhanced data
            connectivity_results=connectivity_results,
            diagnostics=diagnostics,
            bottleneck_threshold=BOTTLENECK_THRESHOLD,  # Add bottleneck threshold
            output_file=report_filename
        )
        
        spinner.stop(message=f"PDF report generated: {report_filename}")
        
        # Generate HTML report for bottlenecks
        generate_bottleneck_report(enhanced_timing_data)
        
        return True
    except Exception as e:
        spinner.stop(success=False, message=f"Error generating PDF report: {e}")
        return False

def generate_bottleneck_report(timing_data):
    """Generate an HTML report focusing on bottlenecks"""
    try:
        bottlenecks = timing_data["bottlenecks"]
        if not bottlenecks:
            log("No bottlenecks detected, skipping bottleneck report", entity="SYSTEM")
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = os.path.join(BOTTLENECK_DIR, f"bottleneck_report_{timestamp}.html")
        
        # Generate a simple HTML report
        with open(report_filename, 'w') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <title>Performance Bottleneck Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .summary {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .bottleneck {{ background-color: #fff0f0; padding: 10px; border-left: 5px solid #ff6b6b; margin-bottom: 10px; }}
        .bottleneck h3 {{ margin-top: 0; color: #d63031; }}
        .threshold {{ color: #e67e22; font-weight: bold; }}
        .duration {{ color: #d63031; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; }}
        .chart-container {{ height: 300px; margin-top: 30px; }}
    </style>
</head>
<body>
    <h1>Performance Bottleneck Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p>Total Processes: {timing_data["summary"]["total_processes"]}</p>
        <p>Bottlenecks Detected: {timing_data["summary"]["bottleneck_count"]}</p>
        <p>Average Duration: {timing_data["summary"]["average_duration"]:.2f}s</p>
        <p>Threshold for Bottleneck: <span class="threshold">{BOTTLENECK_THRESHOLD}s</span></p>
        <p>Test Start Time: {timing_data["metadata"]["start_time"]}</p>
        <p>Test End Time: {timing_data["metadata"]["end_time"]}</p>
        <p>Total Test Duration: {timing_data["metadata"]["total_duration"]:.2f}s</p>
    </div>
    
    <h2>Detected Bottlenecks</h2>
""")
            
            # Add each bottleneck
            for bottleneck in bottlenecks:
                f.write(f"""
    <div class="bottleneck">
        <h3>{bottleneck["process_name"]}</h3>
        <p>Duration: <span class="duration">{bottleneck["duration"]:.2f}s</span> (Threshold: {bottleneck["threshold"]}s)</p>
        <p>Entity: {bottleneck["entity"]}</p>
    </div>
""")
                
            # Add all processes table
            f.write("""
    <h2>All Processes</h2>
    <table>
        <tr>
            <th>Process</th>
            <th>Duration (s)</th>
            <th>Entity</th>
            <th>Status</th>
        </tr>
""")
            
            # Sort processes by duration (descending)
            sorted_processes = sorted(timing_data["processes"], key=lambda x: x["duration"], reverse=True)
            
            for process in sorted_processes:
                # Highlight row for bottlenecks
                row_style = ' style="background-color: #fff0f0;"' if process["duration"] > BOTTLENECK_THRESHOLD else ''
                duration_style = ' class="duration"' if process["duration"] > BOTTLENECK_THRESHOLD else ''
                
                f.write(f"""
        <tr{row_style}>
            <td>{process["name"]}</td>
            <td{duration_style}>{process["duration"]:.2f}</td>
            <td>{process["entity"]}</td>
            <td>{process["status"]}</td>
        </tr>
""")
                
            f.write("""
    </table>
</body>
</html>
""")
            
        log(f"Bottleneck HTML report generated: {report_filename}", status="SUCCESS", entity="SYSTEM")
        return report_filename
    except Exception as e:
        log(f"Error generating bottleneck report: {e}", status="FAILURE", entity="SYSTEM")
        return None

if __name__ == "__main__":
    # Print header with styling
    print(f"\n{Style.BRIGHT}{Fore.CYAN}=== M2M Remote SIM Provisioning with TLS & PSK-TLS ==={Style.RESET_ALL}\n")
    
    # Initialize Root CA
    ca = run_root_ca()
    
    # Start all entities
    log("Starting all entities...", entity="SYSTEM")
    smdp = run_sm_dp(ca)
    smsr = run_sm_sr(ca)
    euicc = run_euicc()
    
    # Modified to capture return values
    def run_demo_and_report():
        success, timing_data, connectivity_results = run_demo()
        # Generate report after demo completes
        if generate_pdf_report is not None:
            generate_report(timing_data, connectivity_results)
    
    # Create and start the demo thread
    demo_thread = Thread(target=run_demo_and_report)
    demo_thread.daemon = True
    demo_thread.start()
    
    # Start the reactor
    try:
        reactor.run()
    except KeyboardInterrupt:
        log("Shutting down...", status="WARNING", entity="SYSTEM")
        reactor.stop()
        sys.exit(0) 
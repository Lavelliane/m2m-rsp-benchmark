#!/usr/bin/env python3
"""
Test script for report generation
"""

import os
import json
from datetime import datetime
import sys

# Create the output directory structure
output_dirs = [
    "output/timing_data",
    "output/reports",
    "output/bottleneck_reports"
]

for directory in output_dirs:
    os.makedirs(directory, exist_ok=True)

# Create sample timing data
timing_data = {
    "Registration": 2.5,
    "ISD-P Creation": 1.5,
    "Key Establishment": 3.0,
    "Profile Preparation": 8.5,  # Bottleneck (over 5 seconds)
    "Profile Installation": 2.0,
    "Profile Enabling": 1.5,
    "Total Execution": 19.0
}

# Create enhanced sample timing data
enhanced_timing_data = {
    "metadata": {
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "total_duration": 19.0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0"
    },
    "processes": [
        {
            "name": "eUICC Registration",
            "duration": 2.5,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "entity": "eUICC",
            "status": "success"
        },
        {
            "name": "ISD-P Creation",
            "duration": 1.5,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "entity": "SM-SR",
            "status": "success"
        },
        {
            "name": "ECDH Key Establishment",
            "duration": 3.0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "entity": "eUICC",
            "status": "success"
        },
        {
            "name": "Profile Preparation",
            "duration": 8.5,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "entity": "SM-DP",
            "status": "success",
            "details": {"profile_type": "telecom", "iccid": "8901234567890123456"}
        },
        {
            "name": "Profile Download and Installation",
            "duration": 2.0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "entity": "eUICC",
            "status": "success"
        },
        {
            "name": "Profile Enabling",
            "duration": 1.5,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            "entity": "SM-SR",
            "status": "success"
        }
    ],
    "bottlenecks": [
        {
            "process_name": "Profile Preparation",
            "duration": 8.5,
            "entity": "SM-DP",
            "threshold": 5.0
        }
    ],
    "summary": {
        "total_processes": 6,
        "bottleneck_count": 1,
        "average_duration": 3.16,
        "max_duration": 8.5,
        "min_duration": 1.5
    }
}

# Save the enhanced timing data to file
with open("output/timing_data/test_enhanced_timing_data.json", "w") as f:
    json.dump(enhanced_timing_data, f, indent=2)

print("Sample timing data created in output/timing_data/test_enhanced_timing_data.json")

# Simulate connectivity results
connectivity_results = {
    "SM-DP": True,
    "SM-SR": True,
    "eUICC": True
}

# Test report generation
try:
    from generate_report import generate_pdf_report
    
    # Generate the report
    output_file = "output/reports/test_report.pdf"
    
    print(f"Generating test report to {output_file}...")
    generate_pdf_report(
        timing_data=timing_data,
        enhanced_timing_data=enhanced_timing_data,
        connectivity_results=connectivity_results,
        bottleneck_threshold=5.0,
        output_file=output_file
    )
    
    print(f"Test report generated successfully: {output_file}")
    
except ImportError:
    print("Error: Could not import generate_pdf_report function")
    sys.exit(1)
except Exception as e:
    print(f"Error generating report: {e}")
    sys.exit(1) 
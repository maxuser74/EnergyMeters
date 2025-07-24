#!/usr/bin/env python3
"""
Simple script to start the energy meter web server
"""

import subprocess
import sys
import os

def start_server():
    print("Starting Energy Meter Web Server with Graphics...")
    print("Server will be available at: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        subprocess.run([sys.executable, "energy_meter_webserver_excel.py"], check=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"Error starting server: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    start_server()

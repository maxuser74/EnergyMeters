#!/usr/bin/env python3
"""
Quick test to verify that readings are being retrieved from ModBus devices
"""

import requests
import json
import time

def test_web_api():
    """Test the web API endpoints to see what data is being returned"""
    base_url = "http://localhost:5050"
    
    print("Testing Energy Meter Web API...")
    print("=" * 50)
    
    try:
        # Test main page
        print("1. Testing main page...")
        response = requests.get(f"{base_url}/", timeout=5)
        print(f"   Main page status: {response.status_code}")
        
        # Test API data endpoint
        print("\n2. Testing API data endpoint...")
        response = requests.get(f"{base_url}/api/data", timeout=10)
        print(f"   API data status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Response keys: {list(data.keys())}")
            
            if 'readings' in data:
                readings = data['readings']
                print(f"   Number of utilities in readings: {len(readings)}")
                
                for utility_id, utility_data in readings.items():
                    print(f"\n   Utility: {utility_id}")
                    print(f"   Status: {utility_data.get('status', 'Unknown')}")
                    
                    registers = utility_data.get('registers', {})
                    print(f"   Number of registers: {len(registers)}")
                    
                    for reg_addr, reg_data in registers.items():
                        value = reg_data.get('value', 'No value')
                        unit = reg_data.get('unit', '')
                        description = reg_data.get('description', '')
                        print(f"     Register {reg_addr}: {description} = {value} {unit}")
                
            else:
                print("   No 'readings' key found in response")
                print(f"   Full response: {data}")
        
        # Test refresh all
        print("\n3. Testing refresh all endpoint...")
        response = requests.get(f"{base_url}/api/refresh_all", timeout=15)
        print(f"   Refresh all status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success', False)}")
            print(f"   Message: {data.get('message', 'No message')}")
            
            if 'readings' in data:
                readings = data['readings']
                print(f"   Number of utilities: {len(readings)}")
                
                for utility_id, utility_data in readings.items():
                    registers = utility_data.get('registers', {})
                    if registers:
                        print(f"   {utility_id}: {len(registers)} registers with data")
                    else:
                        print(f"   {utility_id}: No register data")
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to the web server")
        print("   Make sure the Flask app is running on http://localhost:5050")
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_web_api()

#!/usr/bin/env python3
"""
Test the actual server to see if Transducer ratio appears in the API response
"""
import sys
import os
import requests
import time
import subprocess
import threading

def test_api_response():
    """Test if the Transducer ratio appears in the API response"""
    print("🌐 TESTING API RESPONSE FOR TRANSDUCER RATIO")
    print("=" * 50)
    
    try:
        # Make API call to get readings
        response = requests.get('http://localhost:5000/api/readings', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API response received")
            print(f"📊 Utilities count: {data.get('utilities_count', 0)}")
            print(f"📊 Registers count: {data.get('registers_count', 0)}")
            print(f"🔌 Connection status: {data.get('connection_status', 'Unknown')}")
            
            readings = data.get('readings', {})
            print(f"\n🔍 Analyzing readings for {len(readings)} utilities...")
            
            found_transducer = False
            
            for utility_id, utility_data in readings.items():
                print(f"\n   📌 Utility: {utility_data.get('name', 'Unknown')}")
                registers = utility_data.get('registers', {})
                print(f"      Registers: {len(registers)}")
                
                # Look for setup category registers
                setup_registers = []
                transducer_registers = []
                
                for reg_key, reg_data in registers.items():
                    category = reg_data.get('category', 'unknown')
                    description = reg_data.get('description', '')
                    
                    if category == 'setup':
                        setup_registers.append({
                            'key': reg_key,
                            'description': description,
                            'value': reg_data.get('value'),
                            'status': reg_data.get('status')
                        })
                    
                    if 'transducer' in description.lower():
                        transducer_registers.append({
                            'key': reg_key,
                            'description': description,
                            'value': reg_data.get('value'),
                            'status': reg_data.get('status'),
                            'category': category
                        })
                
                print(f"      Setup registers: {len(setup_registers)}")
                for reg in setup_registers:
                    print(f"         🎯 {reg['description']}: {reg['value']} ({reg['status']})")
                    
                print(f"      Transducer registers: {len(transducer_registers)}")
                for reg in transducer_registers:
                    print(f"         🔧 {reg['description']}: {reg['value']} ({reg['status']}) [Category: {reg['category']}]")
                    found_transducer = True
            
            if found_transducer:
                print(f"\n✅ TRANSDUCER RATIO FOUND IN API RESPONSE!")
            else:
                print(f"\n❌ TRANSDUCER RATIO NOT FOUND IN API RESPONSE!")
                print(f"🔧 This indicates an issue with register reading or data processing")
            
            return found_transducer
            
        else:
            print(f"❌ API request failed with status: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to server at http://localhost:5000")
        print(f"🔧 Make sure the energy meter server is running")
        return False
    except Exception as e:
        print(f"❌ Error testing API: {e}")
        return False

def test_dummy_mode():
    """Test in dummy mode to see if all registers appear"""
    print(f"\n🧪 TESTING DUMMY MODE")
    print("=" * 30)
    
    try:
        # Check if env file exists and set to DUMMY mode temporarily
        env_backup = None
        if os.path.exists('env'):
            with open('env', 'r') as f:
                env_backup = f.read()
        
        with open('env', 'w') as f:
            f.write('MODE=DUMMY\n')
        
        print("✅ Set MODE=DUMMY for testing")
        
        # Wait a moment and test API again
        time.sleep(2)
        result = test_api_response()
        
        # Restore original env
        if env_backup is not None:
            with open('env', 'w') as f:
                f.write(env_backup)
        else:
            if os.path.exists('env'):
                os.remove('env')
        
        print("✅ Restored original MODE setting")
        return result
        
    except Exception as e:
        print(f"❌ Error in dummy mode test: {e}")
        return False

if __name__ == "__main__":
    print("🚀 TESTING TRANSDUCER RATIO IN RUNNING SERVER")
    print("🔧 Make sure energy_meter.py server is running on localhost:5000")
    print("=" * 60)
    
    # Test normal mode
    success_normal = test_api_response()
    
    # Test dummy mode if normal mode fails
    if not success_normal:
        success_dummy = test_dummy_mode()
    else:
        success_dummy = True
    
    print(f"\n" + "=" * 60)
    if success_normal:
        print("✅ TRANSDUCER RATIO IS WORKING IN NORMAL MODE")
        print("🎉 The issue might be in the web interface display")
    elif success_dummy:
        print("⚠️  TRANSDUCER RATIO WORKS IN DUMMY MODE BUT NOT NORMAL MODE")
        print("🔧 Check Modbus connection and register reading")
    else:
        print("❌ TRANSDUCER RATIO NOT FOUND IN ANY MODE")
        print("🔧 There's a fundamental issue with the register loading")

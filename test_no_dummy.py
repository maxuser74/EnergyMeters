#!/usr/bin/env python3
"""
Test script to verify that no dummy data is generated when field devices are unavailable
"""

import sys
import os

# Ensure we can import the energy meter module
sys.path.insert(0, os.path.dirname(__file__))

# Import the energy meter reader
from energy_meter import ExcelBasedEnergyMeterReader

def test_no_dummy_data():
    """Test that no dummy data is generated when real devices fail"""
    print("Testing: No dummy data generation when field devices are unavailable")
    print("=" * 70)
    
    # Create a reader instance
    reader = ExcelBasedEnergyMeterReader()
    
    # Simulate reading utilities when none are available (should return empty)
    print("\n1. Testing with no utilities configured:")
    reader.utilities_config = []  # Empty utilities
    result = reader.read_all_utilities()
    
    if result == {}:
        print("✅ PASS: Empty result when no utilities configured")
    else:
        print("❌ FAIL: Expected empty result, got:", result)
    
    # Test with utilities that will fail to connect (non-existent IPs)
    print("\n2. Testing with unreachable utilities:")
    test_utilities = [{
        'id': 'test_cabinet1_node1',
        'cabinet': 1,
        'node': 1,
        'utility_name': 'Test Machine',
        'ip_address': '192.168.999.999',  # Non-existent IP
        'port': 502
    }]
    
    # Temporarily override the global utilities_config
    import energy_meter
    original_utilities = energy_meter.utilities_config
    energy_meter.utilities_config = test_utilities
    
    result = reader.read_all_utilities()
    
    # Restore original configuration
    energy_meter.utilities_config = original_utilities
    
    if result == {}:
        print("✅ PASS: Empty result when utilities cannot be reached")
    else:
        print("❌ FAIL: Expected empty result, got:", result)
    
    print("\n3. Testing DUMMY mode (should generate test data):")
    original_mode = energy_meter.MODE
    energy_meter.MODE = 'DUMMY'
    
    result = reader.read_all_utilities()
    
    # Restore original mode
    energy_meter.MODE = original_mode
    
    if result and len(result) > 0:
        first_utility = list(result.values())[0]
        if '[TEST]' in first_utility.get('name', ''):
            print("✅ PASS: DUMMY mode generates clearly marked test data")
        else:
            print("❌ FAIL: DUMMY mode data not clearly marked as test data")
    else:
        print("❌ FAIL: DUMMY mode should generate test data")
    
    print("\n" + "=" * 70)
    print("Test completed. Check the output above for results.")

if __name__ == '__main__':
    test_no_dummy_data()

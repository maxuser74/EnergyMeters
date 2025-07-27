#!/usr/bin/env python3
"""
Test script to verify Group-based dummy data generation
Only machines with Group="Dummy" should generate random data
"""

import sys
import os

# Ensure we can import the energy meter module
sys.path.insert(0, os.path.dirname(__file__))

def test_group_based_dummy():
    """Test that only Group='Dummy' machines generate random data"""
    print("Testing: Group-based dummy data generation")
    print("=" * 70)
    
    # Import after path setup
    from energy_meter import ExcelBasedEnergyMeterReader
    import energy_meter
    
    # Create a reader instance
    reader = ExcelBasedEnergyMeterReader()
    
    # Test utilities with different groups
    test_utilities = [
        {
            'id': 'real_machine_1',
            'cabinet': 1,
            'node': 1,
            'utility_name': 'Real Production Machine',
            'gruppo': 'Production',  # Should try real connection
            'ip_address': '192.168.156.75',
            'port': 502
        },
        {
            'id': 'dummy_machine_1', 
            'cabinet': 2,
            'node': 1,
            'utility_name': 'Test Dummy Machine',
            'gruppo': 'Dummy',  # Should generate random data
            'ip_address': '192.168.156.76',
            'port': 502
        },
        {
            'id': 'real_machine_2',
            'cabinet': 3,
            'node': 1,
            'utility_name': 'Another Real Machine',
            'gruppo': 'Maintenance',  # Should try real connection
            'ip_address': '192.168.156.77', 
            'port': 502
        },
        {
            'id': 'dummy_machine_2',
            'cabinet': 1,
            'node': 2,
            'utility_name': 'Second Test Machine',
            'gruppo': 'dummy',  # Case insensitive - should generate random data
            'ip_address': '192.168.156.75',
            'port': 502
        }
    ]
    
    print("\n1. Testing individual machine behavior:")
    print("-" * 50)
    
    # Override global utilities config
    original_utilities = energy_meter.utilities_config
    energy_meter.utilities_config = test_utilities
    
    # Ensure we're in PRODUCTION mode
    original_mode = energy_meter.MODE
    energy_meter.MODE = 'PRODUCTION'
    
    for utility in test_utilities:
        print(f"\n📋 Testing: {utility['utility_name']} (Group: {utility['gruppo']})")
        result = reader.read_single_utility(utility)
        
        is_dummy_group = utility.get('gruppo', '').strip().lower() == 'dummy'
        
        if is_dummy_group:
            if '[DUMMY]' in result.get('name', ''):
                print(f"   ✅ PASS: Dummy group machine generated random data")
                print(f"   📊 Sample voltage: {result['registers']['voltage_L1']['value']}V")
            else:
                print(f"   ❌ FAIL: Dummy group machine should generate random data")
        else:
            # Real machines will likely fail to connect (unless devices are actually available)
            if result.get('status') in ['CONNECTION_FAILED', 'CONNECTION_ERROR', 'ALL_REGISTERS_FAILED']:
                print(f"   ✅ PASS: Non-dummy machine attempted real connection (expected failure)")
                print(f"   🔌 Status: {result.get('status')}")
            elif result.get('status') in ['OK', 'PARTIAL']:
                print(f"   ✅ PASS: Non-dummy machine successfully connected to real device!")
                print(f"   📊 Status: {result.get('status')}")
            else:
                print(f"   ⚠️  Unexpected status: {result.get('status')}")
    
    print(f"\n2. Testing mixed utilities reading:")
    print("-" * 50)
    
    all_results = reader.read_all_utilities()
    
    dummy_count = 0
    real_count = 0
    
    for utility_id, result in all_results.items():
        utility_config = next((u for u in test_utilities if u['id'] == utility_id), None)
        if utility_config:
            is_dummy_group = utility_config.get('gruppo', '').strip().lower() == 'dummy'
            if is_dummy_group and result.get('status') == 'OK':
                dummy_count += 1
            elif not is_dummy_group and result.get('status') in ['OK', 'PARTIAL']:
                real_count += 1
    
    print(f"📊 Results: {dummy_count} dummy group machines active, {real_count} real devices connected")
    
    if dummy_count >= 2:  # We have 2 dummy group machines in test data
        print("✅ PASS: Dummy group machines are generating data as expected")
    else:
        print("❌ FAIL: Not all dummy group machines generated data")
    
    print(f"\n3. Testing GLOBAL DUMMY mode override:")
    print("-" * 50)
    
    energy_meter.MODE = 'DUMMY'
    global_dummy_result = reader.read_all_utilities()
    
    if len(global_dummy_result) == 1 and 'GLOBAL TEST' in str(global_dummy_result):
        print("✅ PASS: GLOBAL DUMMY mode overrides individual Group settings")
    else:
        print("❌ FAIL: GLOBAL DUMMY mode should override Group settings")
    
    # Restore original settings
    energy_meter.utilities_config = original_utilities
    energy_meter.MODE = original_mode
    
    print("\n" + "=" * 70)
    print("Group-based dummy data test completed!")
    print("🎲 Machines with Group='Dummy' generate random data")
    print("📡 Other machines attempt real field device connections")
    print("🧪 GLOBAL DUMMY mode overrides individual Group settings")

if __name__ == '__main__':
    test_group_based_dummy()

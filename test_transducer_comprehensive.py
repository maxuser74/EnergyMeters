#!/usr/bin/env python3
"""
Test reading a single utility in DUMMY mode to see if Transducer ratio appears
"""
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_single_utility_reading():
    """Test reading a single utility to see all registers including setup"""
    print("🔧 TESTING SINGLE UTILITY READING")
    print("=" * 40)
    
    try:
        from energy_meter import ExcelBasedEnergyMeterReader
        
        # Create reader
        reader = ExcelBasedEnergyMeterReader()
        
        # Generate dummy data to see all expected registers
        print("🧪 Generating dummy data...")
        dummy_data = reader.generate_dummy_data(
            utility_id='test_transducer',
            utility_name='TEST TRANSDUCER',
            cabinet=1,
            node=1,
            use_random=False
        )
        
        print(f"✅ Generated dummy data for utility: {dummy_data['name']}")
        print(f"📊 Registers in dummy data: {len(dummy_data['registers'])}")
        
        # Show all registers by category
        categories = {}
        for reg_key, reg_data in dummy_data['registers'].items():
            category = reg_data.get('category', 'unknown')
            if category not in categories:
                categories[category] = []
            categories[category].append({
                'key': reg_key,
                'description': reg_data['description'],
                'value': reg_data['value'],
                'unit': reg_data.get('unit', ''),
                'status': reg_data['status']
            })
        
        print(f"\n🏷️  Categories found in dummy data:")
        for category, registers in categories.items():
            icon = '🎯' if category == 'setup' else '📋'
            print(f"   {icon} {category}: {len(registers)} registers")
            for reg in registers:
                print(f"      • {reg['description']}: {reg['value']} {reg['unit']}")
        
        # Check if we have setup category
        has_setup = 'setup' in categories
        print(f"\n🔍 Setup category present in dummy data: {has_setup}")
        
        if not has_setup:
            print("❌ ISSUE: Setup category not in dummy data generation")
            print("🔧 The issue is that dummy data doesn't include real Excel registers")
        
        return has_setup
        
    except Exception as e:
        print(f"❌ Error testing utility reading: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_excel_to_register_mapping():
    """Test the complete flow from Excel to register data structure"""
    print(f"\n🔄 TESTING EXCEL TO REGISTER MAPPING")
    print("=" * 40)
    
    try:
        from energy_meter import ExcelBasedEnergyMeterReader
        
        reader = ExcelBasedEnergyMeterReader()
        
        # Load registers from Excel
        registers = reader.load_registers_from_excel()
        print(f"✅ Loaded {len(registers)} registers from Excel")
        
        # Check specifically for Transducer ratio
        transducer_registers = []
        setup_registers = []
        
        for start_addr, reg_info in registers.items():
            description = reg_info.get('description', '')
            category = reg_info.get('category', '')
            
            if 'transducer' in description.lower():
                transducer_registers.append({
                    'address': start_addr,
                    'description': description,
                    'category': category,
                    'factor': reg_info.get('factor'),
                    'data_type': reg_info.get('data_type'),
                    'source_unit': reg_info.get('source_unit'),
                    'target_unit': reg_info.get('target_unit')
                })
            
            if category == 'setup':
                setup_registers.append({
                    'address': start_addr,
                    'description': description,
                    'category': category,
                    'factor': reg_info.get('factor')
                })
        
        print(f"\n🔧 Transducer registers found: {len(transducer_registers)}")
        for reg in transducer_registers:
            print(f"   📌 {reg['description']} (Address: {reg['address']})")
            print(f"      Category: {reg['category']}")
            print(f"      Factor: {reg['factor']}")
            print(f"      Data type: {reg['data_type']}")
            print(f"      Units: {reg['source_unit']} → {reg['target_unit']}")
        
        print(f"\n🎯 Setup registers found: {len(setup_registers)}")
        for reg in setup_registers:
            print(f"   🔧 {reg['description']} (Address: {reg['address']}, Factor: {reg['factor']})")
        
        # The key question: Is Transducer ratio loaded as setup category?
        transducer_in_setup = any(
            'transducer' in reg['description'].lower() and reg['category'] == 'setup'
            for reg in setup_registers
        )
        
        print(f"\n🔍 Transducer ratio in setup category: {transducer_in_setup}")
        
        if transducer_in_setup:
            print("✅ TRANSDUCER RATIO IS PROPERLY LOADED AS SETUP")
            print("🔧 The issue must be in register reading or web display")
        else:
            print("❌ TRANSDUCER RATIO IS NOT IN SETUP CATEGORY")
            print("🔧 Check the Excel Type column and category mapping")
        
        return len(transducer_registers) > 0 and transducer_in_setup
        
    except Exception as e:
        print(f"❌ Error testing Excel mapping: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 COMPREHENSIVE TRANSDUCER RATIO TESTING")
    print("=" * 50)
    
    success1 = test_single_utility_reading()
    success2 = test_excel_to_register_mapping()
    
    print(f"\n" + "=" * 50)
    if success1 and success2:
        print("✅ TRANSDUCER RATIO IS LOADED CORRECTLY")
        print("🔧 Issue is likely in register reading or web interface display")
        print("💡 Recommendations:")
        print("   1. Check if server is running in DUMMY mode")
        print("   2. Check if Modbus connection is working for real devices")
        print("   3. Check browser console for JavaScript errors")
    else:
        print("❌ FOUND ISSUES WITH TRANSDUCER RATIO LOADING")
        print("🔧 Fix the loading issues first before checking web interface")

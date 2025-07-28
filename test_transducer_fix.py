#!/usr/bin/env python3
"""
Test the fixed dummy data generation to verify Transducer ratio appears
"""
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_fixed_dummy_data():
    """Test that the fixed dummy data generation includes Transducer ratio"""
    print("🔧 TESTING FIXED DUMMY DATA GENERATION")
    print("=" * 50)
    
    try:
        from energy_meter import ExcelBasedEnergyMeterReader
        
        # Create reader (this loads the Excel configuration)
        reader = ExcelBasedEnergyMeterReader()
        
        # Generate dummy data
        print("🧪 Generating dummy data with Excel register configuration...")
        dummy_data = reader.generate_dummy_data(
            utility_id='test_transducer_fixed',
            utility_name='TEST TRANSDUCER FIXED',
            cabinet=1,
            node=1,
            use_random=False
        )
        
        print(f"✅ Generated dummy data for: {dummy_data['name']}")
        print(f"📊 Total registers in dummy data: {len(dummy_data['registers'])}")
        
        # Analyze registers by category
        categories = {}
        transducer_found = False
        
        for reg_key, reg_data in dummy_data['registers'].items():
            category = reg_data.get('category', 'unknown')
            description = reg_data.get('description', '')
            
            if category not in categories:
                categories[category] = []
            
            categories[category].append({
                'key': reg_key,
                'description': description,
                'value': reg_data['value'],
                'unit': reg_data.get('unit', ''),
                'status': reg_data['status']
            })
            
            # Check for Transducer ratio specifically
            if 'transducer' in description.lower():
                transducer_found = True
                print(f"🎯 FOUND TRANSDUCER: {description} = {reg_data['value']} {reg_data.get('unit', '')} (Category: {category})")
        
        print(f"\n🏷️  Categories in dummy data:")
        for category, registers in categories.items():
            icon = '🎯' if category == 'setup' else '📋'
            print(f"   {icon} {category}: {len(registers)} registers")
            for reg in registers:
                marker = "   🔧 " if 'transducer' in reg['description'].lower() else "      • "
                print(f"{marker}{reg['description']}: {reg['value']} {reg['unit']}")
        
        print(f"\n🔍 Results:")
        print(f"   Setup category present: {'setup' in categories}")
        print(f"   Transducer ratio found: {transducer_found}")
        
        if transducer_found and 'setup' in categories:
            print(f"✅ SUCCESS: Transducer ratio now appears in dummy data!")
            return True
        else:
            print(f"❌ ISSUE: Transducer ratio still missing from dummy data")
            return False
        
    except Exception as e:
        print(f"❌ Error testing fixed dummy data: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 TESTING TRANSDUCER RATIO FIX")
    print("🎯 Verifying that Transducer ratio now appears in dummy mode")
    print("=" * 60)
    
    success = test_fixed_dummy_data()
    
    print(f"\n" + "=" * 60)
    if success:
        print("✅ TRANSDUCER RATIO FIX SUCCESSFUL!")
        print("🎉 The Transducer ratio should now be visible in the app")
        print("💡 Next steps:")
        print("   1. Run the energy meter server")
        print("   2. Check the web interface for Setup badge")
        print("   3. Verify Transducer ratio appears with 🔧 icon")
    else:
        print("❌ TRANSDUCER RATIO FIX FAILED!")
        print("🔧 There are still issues to resolve")

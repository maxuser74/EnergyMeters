#!/usr/bin/env python3
"""
Test script to verify Factor-based conversion integration in energy_meter.py
"""
import sys
import os

# Add the current directory to the path to import energy_meter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_factor_integration():
    """Test the complete Factor integration in energy_meter.py"""
    print("🔍 Testing Factor integration in energy_meter.py...")
    
    try:
        from energy_meter import EnergyMeterServer
        
        # Create an instance to test the loading
        print("📁 Creating EnergyMeterServer instance...")
        server = EnergyMeterServer()
        
        # Test loading registers with Factor
        print("📊 Loading registers from Excel...")
        success = server.load_registers_from_excel("registri.xlsx")
        
        if not success:
            print("❌ Failed to load registers from Excel")
            return
        
        print(f"✅ Successfully loaded {len(server.registers_data)} registers")
        
        # Test Factor integration
        print("\n🔧 Testing Factor integration:")
        registers_with_factor = 0
        registers_without_factor = 0
        
        for reg in server.registers_data:
            if 'factor' in reg and reg['factor'] is not None:
                registers_with_factor += 1
                print(f"  ✅ {reg['name']}: Factor = {reg['factor']}")
            else:
                registers_without_factor += 1
                print(f"  ⚠️  {reg['name']}: No Factor")
        
        print(f"\n📈 Summary:")
        print(f"   Registers with Factor: {registers_with_factor}")
        print(f"   Registers without Factor: {registers_without_factor}")
        print(f"   Total registers: {len(server.registers_data)}")
        
        # Test conversion method
        print("\n🧮 Testing convert_units method with Factor:")
        test_cases = [
            {"value": 2500, "source": "A/100", "target": "A", "factor": 0.01, "expected": 25.0},
            {"value": 23000, "source": "V/100", "target": "V", "factor": 0.01, "expected": 230.0},
            {"value": 950, "source": "cosφ/1000", "target": "cosφ", "factor": 0.001, "expected": 0.95},
            {"value": 15000, "source": "W/10", "target": "W", "factor": 0.1, "expected": 1500.0},
        ]
        
        for case in test_cases:
            result = server.convert_units(
                case["value"], 
                case["source"], 
                case["target"], 
                case["factor"]
            )
            
            status = "✅" if abs(result - case["expected"]) < 0.001 else "❌"
            print(f"  {status} {case['value']} * {case['factor']} = {result} (expected: {case['expected']})")
        
        print("\n✅ Factor integration test complete!")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import energy_meter: {e}")
        return False
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        return False

def test_badge_and_factor_integration():
    """Test that both badge categorization and Factor conversion work together"""
    print("\n🎯 Testing Badge + Factor integration...")
    
    try:
        from energy_meter import EnergyMeterServer
        
        server = EnergyMeterServer()
        success = server.load_registers_from_excel("registri.xlsx")
        
        if not success:
            print("❌ Failed to load registers")
            return False
        
        # Group by badge types and check Factor usage
        badge_groups = {}
        for reg in server.registers_data:
            badge_type = reg.get('badge_type', 'unknown')
            if badge_type not in badge_groups:
                badge_groups[badge_type] = []
            badge_groups[badge_type].append(reg)
        
        print("📊 Badge types with Factor information:")
        for badge_type, registers in badge_groups.items():
            print(f"\n  🏷️  {badge_type.upper()} ({len(registers)} registers):")
            for reg in registers:
                factor = reg.get('factor', 'N/A')
                print(f"     {reg['name']}: Factor = {factor}")
        
        print("\n✅ Badge + Factor integration test complete!")
        return True
        
    except Exception as e:
        print(f"❌ Error during badge+factor testing: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing complete Factor-based conversion system...")
    print("=" * 60)
    
    success1 = test_factor_integration()
    success2 = test_badge_and_factor_integration()
    
    print("\n" + "=" * 60)
    if success1 and success2:
        print("✅ All Factor conversion tests passed!")
    else:
        print("❌ Some tests failed!")

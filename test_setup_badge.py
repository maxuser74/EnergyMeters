#!/usr/bin/env python3
"""
Test Setup badge integration
"""
import sys
import os

# Add the current directory to the path to import energy_meter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_setup_badge():
    """Test that Setup badge is properly loaded and categorized"""
    print("🔧 Testing Setup badge integration...")
    
    try:
        from energy_meter import ExcelBasedEnergyMeterReader
        
        # Create reader instance
        reader = ExcelBasedEnergyMeterReader()
        
        # Get the registers configuration
        registers = reader.load_registers_from_excel()
        
        print(f"📊 Loaded {len(registers)} registers total")
        
        # Group registers by category
        badge_groups = {}
        for start_addr, reg_info in registers.items():
            category = reg_info.get('category', 'unknown')
            if category not in badge_groups:
                badge_groups[category] = []
            badge_groups[category].append({
                'address': start_addr,
                'description': reg_info['description'],
                'factor': reg_info.get('factor'),
                'source_unit': reg_info.get('source_unit'),
                'target_unit': reg_info.get('target_unit')
            })
        
        print("\n🏷️  Badge Categories Found:")
        for category, registers_list in badge_groups.items():
            print(f"\n  📌 {category.upper()} ({len(registers_list)} registers):")
            for reg in registers_list:
                factor_info = f" (Factor: {reg['factor']})" if reg['factor'] is not None else ""
                unit_info = f" [{reg['source_unit']} → {reg['target_unit']}]" if reg['source_unit'] else ""
                print(f"     • {reg['description']}{unit_info}{factor_info}")
        
        # Check specifically for Setup badge
        setup_registers = badge_groups.get('setup', [])
        print(f"\n🎯 Setup Badge Analysis:")
        if setup_registers:
            print(f"   ✅ Setup badge found with {len(setup_registers)} registers")
            for reg in setup_registers:
                print(f"   📋 {reg['description']}")
                print(f"      Address: {reg['address']}")
                print(f"      Factor: {reg['factor']}")
                print(f"      Units: {reg['source_unit']} → {reg['target_unit']}")
        else:
            print("   ❌ No Setup badge registers found")
        
        print(f"\n📈 Summary:")
        print(f"   Total badge types: {len(badge_groups)}")
        print(f"   Total registers: {sum(len(regs) for regs in badge_groups.values())}")
        
        badge_counts = {cat: len(regs) for cat, regs in badge_groups.items()}
        for category, count in sorted(badge_counts.items()):
            print(f"   - {category}: {count}")
        
        return len(setup_registers) > 0
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing Setup Badge Integration")
    print("=" * 50)
    
    success = test_setup_badge()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Setup badge integration successful!")
    else:
        print("❌ Setup badge integration failed!")

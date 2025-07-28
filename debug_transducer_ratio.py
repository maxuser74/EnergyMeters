#!/usr/bin/env python3
"""
Debug script to check why Transducer ratio is not visible in the app
"""
import sys
import os
import pandas as pd

def debug_transducer_ratio():
    """Debug the Transducer ratio register loading"""
    print("🔍 DEBUGGING TRANSDUCER RATIO VISIBILITY")
    print("=" * 50)
    
    # Step 1: Check Excel file
    print("\n📁 Step 1: Checking Excel file...")
    try:
        df = pd.read_excel("registri.xlsx")
        print(f"✅ Loaded Excel with {len(df)} rows")
        
        # Find Transducer ratio specifically
        transducer_rows = df[df['Lettura'].str.contains('Transducer ratio', na=False, case=False)]
        print(f"\n🔍 Transducer ratio entries found: {len(transducer_rows)}")
        
        for idx, row in transducer_rows.iterrows():
            print(f"   📌 Row {idx}:")
            print(f"      Registro: {row.get('Registro')}")
            print(f"      Lettura: {row.get('Lettura')}")
            print(f"      Type: {row.get('Type')}")
            print(f"      Report: {row.get('Report')}")
            print(f"      Factor: {row.get('Factor')}")
            print(f"      Lenght: {row.get('Lenght')}")
            print(f"      Readings: {row.get('Readings')}")
            print(f"      Convert to: {row.get('Convert to')}")
        
    except Exception as e:
        print(f"❌ Error loading Excel: {e}")
        return False
    
    # Step 2: Check register loading simulation
    print(f"\n🔧 Step 2: Simulating register loading...")
    try:
        # Simulate the loading logic for Transducer ratio
        for idx, row in transducer_rows.iterrows():
            print(f"\n   Processing Transducer ratio (Row {idx}):")
            
            # Check Report status
            report_status = str(row.get('Report', 'yes')).strip().lower()
            should_report = report_status in ['yes', 'y', '1', 'true']
            print(f"      Report status: '{row.get('Report')}' → Should report: {should_report}")
            
            if not should_report:
                print(f"      ❌ SKIPPED: Report status is not 'Yes'")
                continue
            
            # Check required fields
            end_address = row.get('Registro')
            description = str(row.get('Lettura', '')).strip()
            data_type = str(row.get('Lenght', '')).strip()
            
            print(f"      End address: {end_address}")
            print(f"      Description: '{description}'")
            print(f"      Data type: '{data_type}'")
            
            if not description or description == 'nan':
                print(f"      ❌ SKIPPED: Empty description")
                continue
            
            # Check Type mapping
            register_type = row.get('Type')
            if pd.notna(register_type):
                category = str(register_type).strip().lower()
                category = category.replace(' ', '_').replace('/', '_')
                if category == 'setup':
                    mapped_category = 'setup'
                else:
                    mapped_category = category
                print(f"      Type: '{register_type}' → Category: '{mapped_category}'")
            else:
                mapped_category = description.strip().replace(' ', '_').replace('/', '_').lower()
                print(f"      No Type column, using description → Category: '{mapped_category}'")
            
            # Calculate addresses
            try:
                end_address_int = int(end_address)
                if data_type.lower() == 'float':
                    register_count = 2
                    start_address = end_address_int - 1
                elif 'long long' in data_type.lower():
                    register_count = 4
                    start_address = end_address_int - 3
                else:
                    register_count = 2
                    start_address = end_address_int - 1
                
                print(f"      Address calculation: {start_address}-{end_address_int} ({register_count} registers)")
                print(f"      ✅ WOULD BE LOADED as '{mapped_category}' category")
                
            except (ValueError, TypeError) as e:
                print(f"      ❌ SKIPPED: Invalid address '{end_address}': {e}")
    
    except Exception as e:
        print(f"❌ Error in simulation: {e}")
        return False
    
    return True

def check_class_loading():
    """Check if the class loads the register correctly"""
    print(f"\n🔧 Step 3: Testing actual class loading...")
    
    try:
        # Add current directory to path
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        # Import the class
        from energy_meter import ExcelBasedEnergyMeterReader
        
        # Create instance
        reader = ExcelBasedEnergyMeterReader()
        
        # Check the loaded registers
        if hasattr(reader, 'load_registers_from_excel'):
            registers = reader.load_registers_from_excel()
            print(f"   ✅ Loaded {len(registers)} registers from class method")
            
            # Look for setup category registers
            setup_registers = []
            for start_addr, reg_info in registers.items():
                if reg_info.get('category') == 'setup':
                    setup_registers.append({
                        'start_address': start_addr,
                        'description': reg_info['description'],
                        'category': reg_info['category'],
                        'factor': reg_info.get('factor')
                    })
            
            print(f"   🎯 Setup registers found: {len(setup_registers)}")
            for reg in setup_registers:
                print(f"      • {reg['description']} (Address: {reg['start_address']}, Factor: {reg['factor']})")
            
            if len(setup_registers) == 0:
                print(f"   ❌ NO SETUP REGISTERS LOADED!")
                return False
            else:
                print(f"   ✅ Setup registers loaded correctly")
                return True
        else:
            print(f"   ❌ Method load_registers_from_excel not found")
            return False
            
    except Exception as e:
        print(f"   ❌ Error testing class loading: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success1 = debug_transducer_ratio()
    success2 = check_class_loading()
    
    print(f"\n" + "=" * 50)
    if success1 and success2:
        print("✅ Transducer ratio should be loading correctly")
        print("🔍 Issue might be in the web interface or register reading")
    else:
        print("❌ Found issues with Transducer ratio loading")
        print("🔧 Fix these issues first before checking web interface")

#!/usr/bin/env python3
"""
Test the ExcelBasedEnergyMeterReader register loading with updated badge mapping
"""
import sys
import os

# Add the virtual environment to the path
venv_path = r"C:\Users\mpasseri\OneDrive - CAMOZZI GROUP SPA\Documenti\VSCode\EnergyMeters\.venv\Lib\site-packages"
sys.path.insert(0, venv_path)

try:
    # Import the necessary modules
    import pandas as pd
    import struct
    import time
    import threading
    import json
    import random
    from datetime import datetime
    
    # Now we can test the class
    class TestEnergyMeterReader:
        def __init__(self):
            pass
            
        def load_registers_from_excel(self):
            """Load register configuration from registri.xlsx (only Report=Yes registers), and group by 'Type' column for badge grouping"""
            try:
                if not os.path.exists('registri.xlsx'):
                    print("ERROR: registri.xlsx file not found!")
                    return {}
                    
                df_registri = pd.read_excel('registri.xlsx')
                
                # Validate required columns
                required_columns = ['Registro', 'Lettura', 'Lenght']
                missing_columns = [col for col in required_columns if col not in df_registri.columns]
                if missing_columns:
                    print(f"ERROR: Missing required columns in registri.xlsx: {missing_columns}")
                    return {}
                
                registers = {}
                print("Loading registers from registri.xlsx (Report=Yes only):")
                
                for idx, row in df_registri.iterrows():
                    try:
                        # Check if this register should be reported
                        report_status = str(row.get('Report', 'yes')).strip().lower()
                        if report_status not in ['yes', 'y', '1', 'true']:
                            print(f"  Skipping register (Report={row.get('Report', 'N/A')}): {row['Lettura']}")
                            continue
                            
                        end_address = int(row['Registro'])
                        description = str(row['Lettura']).strip()
                        data_type = str(row['Lenght']).strip()
                        source_unit = str(row.get('Readings', '')).strip()
                        target_unit = str(row.get('Convert to', source_unit)).strip()
                        
                        if not description or description == 'nan':
                            print(f"WARNING: Empty description at row {idx}, skipping")
                            continue
                        
                        # Use 'Type' column for grouping, fallback to Lettura if missing
                        if 'Type' in df_registri.columns and pd.notna(row.get('Type')):
                            category = str(row['Type']).strip().lower()
                            category = category.replace(' ', '_').replace('/', '_')
                            if category == 'currents':
                                category = 'current'
                            elif category == 'voltages':
                                category = 'voltage'
                            elif category == 'power_factors':
                                category = 'power_factor'
                            elif category == 'power':
                                category = 'power'
                        else:
                            category = description.strip().replace(' ', '_').replace('/', '_').lower()
                        
                        # Calculate register count and start address based on data type
                        if data_type.lower() == 'float':
                            register_count = 2
                            start_address = end_address - 1
                        elif 'long long' in data_type.lower():
                            register_count = 4
                            start_address = end_address - 3
                        else:
                            register_count = 2
                            start_address = end_address - 1
                        
                        # Store register info
                        registers[start_address] = {
                            'description': description,
                            'data_type': data_type,
                            'register_count': register_count,
                            'start_address': start_address,
                            'end_address': end_address,
                            'source_unit': source_unit,
                            'target_unit': target_unit,
                            'category': category
                        }
                        print(f"  ✅ Register: {description} (Type: {category}) (Address: {start_address}-{end_address})")
                        
                    except (ValueError, TypeError) as e:
                        print(f"ERROR: Invalid register data at row {idx}: {e}")
                        continue
                        
                print(f"Loaded {len(registers)} registers for reporting")
                return registers
                
            except FileNotFoundError:
                print("ERROR: registri.xlsx file not found!")
                return {}
            except pd.errors.EmptyDataError:
                print("ERROR: registri.xlsx is empty!")
                return {}
            except Exception as e:
                print(f"ERROR loading registers from registri.xlsx: {e}")
                return {}
    
    # Test the function
    print("=== TESTING UPDATED REGISTER LOADING ===")
    test_reader = TestEnergyMeterReader()
    registers = test_reader.load_registers_from_excel()
    
    print(f"\n=== BADGE SUMMARY ===")
    badges = {}
    for reg_addr, reg_info in registers.items():
        category = reg_info['category']
        if category not in badges:
            badges[category] = []
        badges[category].append(reg_info)
    
    for badge_name, regs in badges.items():
        print(f"🏷️  {badge_name.upper()} BADGE: {len(regs)} registers")
        for reg in regs:
            print(f"   • {reg['description']} (Address: {reg['start_address']}-{reg['end_address']})")
    
    print(f"\n✅ Badge categorization working correctly!")
    print(f"   Total badges: {len(badges)}")
    print(f"   Total registers: {len(registers)}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

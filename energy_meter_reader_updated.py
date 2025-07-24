#!/usr/bin/env python3
"""
Energy Meter Reader Script - Utility-Based Monitoring
Reads specific registers from monitored utilities defined in Excel files:
- Utenze.xlsx: Contains the specific utilities to monitor (Cabinet, Node, Utility name)
- registri.xlsx: Contains the registers to read for each utility (with Length information)
"""

from pymodbus.constants import Endian
from pymodbus.client import ModbusTcpClient
import time
from datetime import datetime
import os
import csv
import struct

# Try to import pandas for Excel export, but make it optional
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("WARNING: pandas not available - will export to CSV instead of Excel")

def load_utilities_from_excel():
    """Load utilities configuration from Utenze.xlsx"""
    try:
        df_utenze = pd.read_excel('Utenze.xlsx')
        utilities = []
        
        # Cabinet IP mapping
        cabinet_ips = {
            1: '192.168.156.75',
            2: '192.168.156.76', 
            3: '192.168.156.77'
        }
        
        for _, row in df_utenze.iterrows():
            cabinet = int(row['Cabinet'])
            node = int(row['Nodo'])
            utility_name = str(row['Utenza'])
            ip_address = cabinet_ips.get(cabinet, None)
            
            if ip_address:
                utilities.append({
                    'cabinet': cabinet,
                    'node': node,
                    'utility_name': utility_name,
                    'ip_address': ip_address,
                    'port': 502
                })
            else:
                print(f"WARNING: Unknown cabinet {cabinet} for utility {utility_name}")
        
        print(f"Loaded {len(utilities)} utilities from Utenze.xlsx")
        return utilities
        
    except FileNotFoundError:
        print("ERROR: Utenze.xlsx file not found!")
        return []
    except Exception as e:
        print(f"ERROR loading utilities from Utenze.xlsx: {e}")
        return []

def load_registers_from_excel():
    """Load register configuration from registri.xlsx with proper address calculation"""
    try:
        df_registri = pd.read_excel('registri.xlsx')
        registers = {}
        
        print("Analyzing registers from registri.xlsx:")
        for _, row in df_registri.iterrows():
            end_address = int(row['Registro'])
            description = str(row['Lettura'])
            data_type = str(row['Lenght'])
            
            # Calculate register count and start address based on data type
            if data_type.lower() == 'float':
                # Float = 32-bit = 2 registers (16-bit each)
                register_count = 2
                start_address = end_address - 1
            elif 'long long' in data_type.lower():
                # Signed long long = 64-bit = 4 registers (16-bit each)  
                register_count = 4
                start_address = end_address - 3
            else:
                # Default to 2 registers for unknown types
                register_count = 2
                start_address = end_address - 1
                print(f"  WARNING: Unknown data type '{data_type}', assuming float")
            
            # Store register info with calculated start address
            registers[start_address] = {
                'description': description,
                'data_type': data_type,
                'register_count': register_count,
                'start_address': start_address,
                'end_address': end_address
            }
            
            print(f"  Register: {description}")
            print(f"    Address range: {start_address} to {end_address} ({register_count} registers)")
            print(f"    Data type: {data_type}")
        
        print(f"Loaded {len(registers)} registers from registri.xlsx")
        return registers
        
    except FileNotFoundError:
        print("ERROR: registri.xlsx file not found!")
        # Fallback with old format
        return {374: {'description': "Current L1 (A)", 'data_type': 'float', 'register_count': 2, 'start_address': 374, 'end_address': 375}}
    except Exception as e:
        print(f"ERROR loading registers from registri.xlsx: {e}")
        # Fallback with old format
        return {374: {'description': "Current L1 (A)", 'data_type': 'float', 'register_count': 2, 'start_address': 374, 'end_address': 375}}

def read_register_value(client, register_info, node_id):
    """Read a register value based on its data type and length"""
    start_address = register_info['start_address']
    register_count = register_info['register_count']
    data_type = register_info['data_type']
    description = register_info['description']
    
    try:
        # Read the required number of registers
        request = client.read_holding_registers(address=start_address, count=register_count, slave=node_id)
        
        if request.isError():
            return None
        
        # Process based on data type
        if data_type.lower() == 'float':
            # 32-bit float: 2 registers
            if len(request.registers) < 2:
                return None
            high_word = request.registers[0]
            low_word = request.registers[1]
            
            # Convert to 32-bit float: word order is little endian (low word first)
            packed_data = struct.pack('>HH', low_word, high_word)
            value = struct.unpack('>f', packed_data)[0]
            return round(value, 2)
            
        elif 'long long' in data_type.lower():
            # 64-bit signed long long: 4 registers
            if len(request.registers) < 4:
                return None
            
            # Combine 4 registers into 64-bit value
            # Assuming little endian order: [low_word, high_word, higher_word, highest_word]
            word1 = request.registers[0]
            word2 = request.registers[1] 
            word3 = request.registers[2]
            word4 = request.registers[3]
            
            # Pack as 64-bit signed integer
            packed_data = struct.pack('>HHHH', word4, word3, word2, word1)
            value = struct.unpack('>q', packed_data)[0]
            
            # Check if this is energy data that needs scaling (W/10)
            if '(W/10)' in description or '/10' in description:
                value = value / 10.0
                return round(value, 1)
            else:
                return value
        else:
            # Unknown type, try as float
            if len(request.registers) >= 2:
                high_word = request.registers[0]
                low_word = request.registers[1]
                packed_data = struct.pack('>HH', low_word, high_word)
                value = struct.unpack('>f', packed_data)[0]
                return round(value, 2)
            else:
                return None
                
    except Exception as e:
        print(f"    ERROR reading register {start_address}: {e}")
        return None

def read_energy_meter_registers():
    """
    Read energy meter registers from utilities defined in Utenze.xlsx
    using registers defined in registri.xlsx with proper length handling
    Export data to Excel
    """
    # Load configuration from Excel files
    utilities = load_utilities_from_excel()
    registers = load_registers_from_excel()
    
    if not utilities:
        print("No utilities loaded. Exiting.")
        return False
    
    if not registers:
        print("No registers loaded. Exiting.")
        return False
    
    # Store all data for Excel export
    all_data = []
    
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 120)
    
    # Print table header - dynamic based on registers
    header_parts = ["Utility", "Cabinet", "Node"]
    for start_address, register_info in registers.items():
        description = register_info['description']
        header_parts.append(description[:15])  # Truncate long descriptions
    header_parts.append("Status")
    
    # Print header
    header_line = " | ".join([f"{part:>15}" for part in header_parts])
    print(header_line)
    print("-" * len(header_line))
    
    # Process each utility
    for utility in utilities:
        utility_name = utility['utility_name']
        cabinet_num = utility['cabinet']
        node_num = utility['node']
        ip_address = utility['ip_address']
        port = utility['port']
        
        # Create Modbus TCP client for this utility
        client = ModbusTcpClient(ip_address, port=port, timeout=3)
        
        try:
            # Connect to the device
            connection_result = client.connect()
            if not connection_result:
                # Connection failed - display error
                row_parts = [utility_name[:15], f"Cabinet {cabinet_num}", f"Node {node_num}"]
                for _ in registers:
                    row_parts.append("ERROR")
                row_parts.append("CONN_FAIL")
                
                row_line = " | ".join([f"{part:>15}" for part in row_parts])
                print(row_line)
                
                # Add error row to data
                data_row = {
                    'Utility': utility_name,
                    'Cabinet': f"Cabinet {cabinet_num}",
                    'IP_Address': ip_address,
                    'Node': node_num,
                    'Status': 'CONNECTION_FAILED',
                    'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                for start_address, register_info in registers.items():
                    description = register_info['description']
                    data_row[description] = 'ERROR'
                all_data.append(data_row)
                continue
            
            # Read all registers for this utility
            node_results = {}
            node_status = "OK"
            
            # Read each register using the new function
            for start_address, register_info in registers.items():
                try:
                    value = read_register_value(client, register_info, node_num)
                    if value is not None:
                        node_results[start_address] = value
                    else:
                        node_results[start_address] = None
                        node_status = "ERROR" if node_status == "OK" else node_status
                    
                except Exception as e:
                    node_results[start_address] = None
                    node_status = "PARTIAL" if node_status == "OK" else "FAIL"
                    print(f"    Exception reading {register_info['description']}: {e}")
            
            # Display results
            row_parts = [utility_name[:15], f"Cabinet {cabinet_num}", f"Node {node_num}"]
            for start_address, register_info in registers.items():
                value = node_results.get(start_address)
                if value is not None:
                    # Format based on data type
                    if 'long long' in register_info['data_type'].lower():
                        row_parts.append(f"{value}")
                    else:
                        row_parts.append(f"{value:.2f}")
                else:
                    row_parts.append("N/A")
            row_parts.append(node_status)
            
            row_line = " | ".join([f"{part:>15}" for part in row_parts])
            print(row_line)
            
            # Add to data collection for Excel
            data_row = {
                'Utility': utility_name,
                'Cabinet': f"Cabinet {cabinet_num}",
                'IP_Address': ip_address,
                'Node': node_num,
                'Status': node_status,
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            for start_address, register_info in registers.items():
                description = register_info['description']
                value = node_results.get(start_address)
                if value is not None:
                    if 'long long' in register_info['data_type'].lower():
                        data_row[description] = value  # Keep as integer
                    else:
                        data_row[description] = round(value, 2)
                else:
                    data_row[description] = None
            all_data.append(data_row)
            
        except Exception as e:
            # Connection or other error
            row_parts = [utility_name[:15], f"Cabinet {cabinet_num}", f"Node {node_num}"]
            for _ in registers:
                row_parts.append("ERROR")
            row_parts.append("EXCEPTION")
            
            row_line = " | ".join([f"{part:>15}" for part in row_parts])
            print(row_line)
            
            # Add error row to data
            data_row = {
                'Utility': utility_name,
                'Cabinet': f"Cabinet {cabinet_num}",
                'IP_Address': ip_address,
                'Node': node_num,
                'Status': f'EXCEPTION: {str(e)[:50]}',
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            for start_address, register_info in registers.items():
                description = register_info['description']
                data_row[description] = 'ERROR'
            all_data.append(data_row)
            
        finally:
            # Always close the connection
            try:
                client.close()
            except:
                pass
    
    print("=" * 120)
    
    # Export to Excel or CSV
    try:
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if PANDAS_AVAILABLE:
            # Export to Excel using pandas
            df = pd.DataFrame(all_data)
            filename = f'energy_meter_readings_utilities_{timestamp}.xlsx'
            df.to_excel(filename, index=False, sheet_name='Utility Energy Readings')
            print(f"SUCCESS: Data exported to Excel: {filename}")
        else:
            # Export to CSV as fallback
            filename = f'energy_meter_readings_utilities_{timestamp}.csv'
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                if all_data:
                    fieldnames = all_data[0].keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_data)
            print(f"SUCCESS: Data exported to CSV: {filename}")
        
        print(f"Total utilities monitored: {len(all_data)}")
        
        # Display summary statistics
        if len(all_data) > 0:
            # Count successful readings
            successful_readings = [row for row in all_data if row['Status'] in ['OK', 'PARTIAL']]
            failed_readings = [row for row in all_data if row['Status'] not in ['OK', 'PARTIAL']]
            
            print(f"MONITORING SUMMARY:")
            print(f"   Total utilities: {len(all_data)}")
            print(f"   Successful readings: {len(successful_readings)}")
            print(f"   Failed readings: {len(failed_readings)}")
            
            if successful_readings:
                print(f"UTILITY DETAILS:")
                for row in successful_readings:
                    utility_name = row['Utility'][:20]  # Truncate long names
                    status = row['Status']
                    print(f"   - {utility_name}: {status}")
                    
                # Calculate statistics for numeric registers (if any)
                if PANDAS_AVAILABLE:
                    try:
                        df_success = pd.DataFrame(successful_readings)
                        print(f"MEASUREMENT STATISTICS:")
                        for start_address, register_info in registers.items():
                            description = register_info['description']
                            if description in df_success.columns:
                                df_success[description] = pd.to_numeric(df_success[description], errors='coerce')
                                valid_values = df_success[description].dropna()
                                if len(valid_values) > 0:
                                    print(f"   {description}:")
                                    print(f"     Max: {valid_values.max():.2f}")
                                    print(f"     Avg: {valid_values.mean():.2f}")
                                    print(f"     Min: {valid_values.min():.2f}")
                    except:
                        print("   Could not calculate detailed statistics")
            
            if failed_readings:
                print(f"FAILED UTILITIES:")
                for row in failed_readings:
                    utility_name = row['Utility'][:20]
                    status = row['Status'][:30]
                    print(f"   - {utility_name}: {status}")
        
        # Show file location
        full_path = os.path.abspath(filename)
        print(f"File saved at: {full_path}")
        
    except Exception as e:
        print(f"ERROR: Error exporting data: {e}")
        if not PANDAS_AVAILABLE:
            print("   For Excel export, install: pip install pandas openpyxl")
    
    return True

def continuous_monitoring(interval_seconds=5, max_readings=10):
    """
    Continuously monitor energy meter registers
    
    Args:
        interval_seconds (int): Time between readings in seconds
        max_readings (int): Maximum number of readings (0 for infinite)
    """
    print(f"Starting continuous monitoring...")
    print(f"Reading interval: {interval_seconds} seconds")
    print(f"Max readings: {'Infinite' if max_readings == 0 else max_readings}")
    print("Press Ctrl+C to stop\n")
    
    reading_count = 0
    try:
        while True:
            reading_count += 1
            print(f"\n=== READING #{reading_count} ===")
            
            success = read_energy_meter_registers()
            
            if not success:
                print("Reading failed, retrying in next cycle...")
            
            # Check if we've reached max readings
            if max_readings > 0 and reading_count >= max_readings:
                print(f"\nReached maximum readings ({max_readings}). Stopping.")
                break
                
            # Wait for next reading
            if max_readings == 0 or reading_count < max_readings:
                print(f"\nWaiting {interval_seconds} seconds for next reading...")
                time.sleep(interval_seconds)
                
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"\nERROR in monitoring: {e}")

if __name__ == "__main__":
    print("Energy Meter Reader - Enhanced with Length-based Address Calculation")
    print("===================================================================")
    print()
    
    # Single reading
    print("Performing single reading...")
    read_energy_meter_registers()
    
    # Ask user if they want continuous monitoring
    try:
        response = input("\nDo you want to start continuous monitoring? (y/n): ").lower().strip()
        if response in ['y', 'yes']:
            try:
                interval = int(input("Enter reading interval in seconds (default 5): ") or "5")
                max_reads = int(input("Enter max readings (0 for infinite, default 10): ") or "10")
                continuous_monitoring(interval, max_reads)
            except ValueError:
                print("Invalid input, using defaults...")
                continuous_monitoring()
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    
    print("\nProgram finished.")

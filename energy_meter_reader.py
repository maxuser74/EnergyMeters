#!/usr/bin/env python3
"""
Energy Meter Reader Script
Reads multiple registers from a Modbus TCP energy meter device
"""

from pymodbus.constants import Endian
from pymodbus.client import ModbusTcpClient
import time
from datetime import datetime
import os
import csv

# Try to import pandas for Excel export, but make it optional
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("⚠️  pandas not available - will export to CSV instead of Excel")

def read_energy_meter_registers():
    """
    Read all energy meter registers and display results for multiple cabinets
    Export data to Excel
    """
    # Cabinet configurations
    cabinets = [
        {'name': 'Cabinet 1', 'ip': '192.168.156.75', 'nodes': range(1, 27)},
        {'name': 'Cabinet 2', 'ip': '192.168.156.76', 'nodes': range(1, 22)},
        {'name': 'Cabinet 3', 'ip': '192.168.156.77', 'nodes': range(1, 16)}
    ]
    port = 502
    
    # Register definitions with descriptions
    registers = {
        374: "Current L1 (A)", 
        376: "Current L2 (A)",
        378: "Current L3 (A)",
    }
    
    # Store all data for Excel export
    all_data = []
    
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    
    # Print table header
    print(f"{'Cabinet':>10} | {'Node':>4} | {'Current L1 (A)':>12} | {'Current L2 (A)':>12} | {'Current L3 (A)':>12} | {'Status':>10}")
    print("-" * 100)
    
    for cabinet in cabinets:
        cabinet_name = cabinet['name']
        cabina = cabinet['ip']
        nodes = cabinet['nodes']
        
        # Create Modbus TCP client for this cabinet
        client = ModbusTcpClient(cabina, port=port, timeout=3)
        
        try:
            # Connect to the device
            connection_result = client.connect()
            if not connection_result:
                print(f"{'':>10} | {'':>4} | ERROR: Cannot connect to {cabinet_name} at {cabina}:{port}")
                # Add error row to data
                all_data.append({
                    'Cabinet': cabinet_name,
                    'IP_Address': cabina,
                    'Node': 'N/A',
                    'Current_L1_A': 'ERROR',
                    'Current_L2_A': 'ERROR', 
                    'Current_L3_A': 'ERROR',
                    'Status': 'CONNECTION_FAILED',
                    'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                continue
            
            # Iterate through nodes for this cabinet
            for nodo in nodes:
                node_results = {}
                node_status = "OK"
                
                # Read each register for this node
                for registro, description in registers.items():
                    try:
                        # Read 2 registers (32-bit float)
                        request = client.read_holding_registers(address=registro, count=2, slave=nodo)
                        
                        if request.isError():
                            node_results[registro] = None
                            node_status = "ERROR"
                            continue
                            
                        # Decode the 32-bit float value
                        import struct
                        
                        high_word = request.registers[0]
                        low_word = request.registers[1]
                        
                        # Convert to 32-bit float: word order is little endian (low word first)
                        packed_data = struct.pack('>HH', low_word, high_word)
                        valore = struct.unpack('>f', packed_data)[0]
                        
                        # Round to 2 decimal places
                        valore = round(valore, 2)
                        
                        # Store result
                        node_results[registro] = valore
                        
                    except Exception as e:
                        node_results[registro] = None
                        node_status = "FAIL"
                
                # Prepare display values
                l1_current = f"{node_results.get(374, 0):.2f}" if node_results.get(374) is not None else "N/A"
                l2_current = f"{node_results.get(376, 0):.2f}" if node_results.get(376) is not None else "N/A"
                l3_current = f"{node_results.get(378, 0):.2f}" if node_results.get(378) is not None else "N/A"
                
                # Display row
                print(f"{cabinet_name:>10} | {nodo:>4} | {l1_current:>12} | {l2_current:>12} | {l3_current:>12} | {node_status:>10}")
                
                # Add to data collection for Excel
                all_data.append({
                    'Cabinet': cabinet_name,
                    'IP_Address': cabina,
                    'Node': nodo,
                    'Current_L1_A': round(node_results.get(374, 0), 2) if node_results.get(374) is not None else None,
                    'Current_L2_A': round(node_results.get(376, 0), 2) if node_results.get(376) is not None else None, 
                    'Current_L3_A': round(node_results.get(378, 0), 2) if node_results.get(378) is not None else None,
                    'Status': node_status,
                    'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            
        except Exception as e:
            print(f"{'':>10} | {'':>4} | ERROR connecting to {cabinet_name}: {e}")
            # Add error row to data
            all_data.append({
                'Cabinet': cabinet_name,
                'IP_Address': cabina,
                'Node': 'N/A',
                'Current_L1_A': 'ERROR',
                'Current_L2_A': 'ERROR', 
                'Current_L3_A': 'ERROR',
                'Status': f'EXCEPTION: {str(e)[:50]}',
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
        finally:
            # Always close the connection
            try:
                client.close()
            except:
                pass
    
    print("=" * 100)
    
    # Export to Excel or CSV
    try:
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if PANDAS_AVAILABLE:
            # Export to Excel using pandas
            df = pd.DataFrame(all_data)
            filename = f'energy_meter_readings_{timestamp}.xlsx'
            df.to_excel(filename, index=False, sheet_name='Energy Meter Readings')
            print(f"\n✅ Data exported to Excel: {filename}")
        else:
            # Export to CSV as fallback
            filename = f'energy_meter_readings_{timestamp}.csv'
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                if all_data:
                    fieldnames = all_data[0].keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_data)
            print(f"\n✅ Data exported to CSV: {filename}")
        
        print(f"📊 Total rows exported: {len(all_data)}")
        
        # Display summary statistics
        if len(all_data) > 0 and PANDAS_AVAILABLE:
            df_numeric = df[df['Current_L1_A'] != 'ERROR'].copy()
            if len(df_numeric) > 0:
                try:
                    df_numeric['Current_L1_A'] = pd.to_numeric(df_numeric['Current_L1_A'], errors='coerce')
                    df_numeric['Current_L2_A'] = pd.to_numeric(df_numeric['Current_L2_A'], errors='coerce')
                    df_numeric['Current_L3_A'] = pd.to_numeric(df_numeric['Current_L3_A'], errors='coerce')
                    
                    print(f"\n📈 SUMMARY STATISTICS:")
                    print(f"   Total nodes read: {len(df_numeric)}")
                    print(f"   Max L1 current: {df_numeric['Current_L1_A'].max():.2f} A")
                    print(f"   Max L2 current: {df_numeric['Current_L2_A'].max():.2f} A")
                    print(f"   Max L3 current: {df_numeric['Current_L3_A'].max():.2f} A")
                    print(f"   Avg L1 current: {df_numeric['Current_L1_A'].mean():.2f} A")
                    print(f"   Avg L2 current: {df_numeric['Current_L2_A'].mean():.2f} A")
                    print(f"   Avg L3 current: {df_numeric['Current_L3_A'].mean():.2f} A")
                except:
                    print("   Could not calculate statistics")
        elif len(all_data) > 0:
            # Simple statistics without pandas
            valid_data = [row for row in all_data if row['Status'] == 'OK']
            if valid_data:
                l1_values = [row['Current_L1_A'] for row in valid_data if row['Current_L1_A'] is not None]
                l2_values = [row['Current_L2_A'] for row in valid_data if row['Current_L2_A'] is not None]
                l3_values = [row['Current_L3_A'] for row in valid_data if row['Current_L3_A'] is not None]
                
                print(f"\n📈 SUMMARY STATISTICS:")
                print(f"   Total nodes read: {len(valid_data)}")
                if l1_values:
                    print(f"   Max L1 current: {max(l1_values):.2f} A")
                    print(f"   Avg L1 current: {sum(l1_values)/len(l1_values):.2f} A")
                if l2_values:
                    print(f"   Max L2 current: {max(l2_values):.2f} A")
                    print(f"   Avg L2 current: {sum(l2_values)/len(l2_values):.2f} A")
                if l3_values:
                    print(f"   Max L3 current: {max(l3_values):.2f} A")
                    print(f"   Avg L3 current: {sum(l3_values)/len(l3_values):.2f} A")
        
        # Show file location
        full_path = os.path.abspath(filename)
        print(f"📁 File saved at: {full_path}")
        
    except Exception as e:
        print(f"❌ Error exporting data: {e}")
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
    print("Energy Meter Reader")
    print("==================")
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

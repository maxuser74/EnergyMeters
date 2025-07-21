#!/usr/bin/env python3
"""
Energy Meter Reader Script
Reads multiple registers from a Modbus TCP energy meter device
"""

from pymodbus.constants import Endian
from pymodbus.client import ModbusTcpClient
import time
from datetime import datetime

def read_energy_meter_registers():
    """
    Read all energy meter registers and display results
    """
    # Connection parameters
    cabina = '192.168.156.75'
    nodo = 8  # Modbus slave/device ID
    port = 502
    
    # Register definitions with descriptions
    registers = {
        372: "Tensione RMS media su 3 fasi V (Average RMS voltage on 3 phases V)",
        374: "Corrente di linea L1 A (Line current L1 A)", 
        376: "Corrente di linea L2 A (Line current L2 A)",
        378: "Corrente di linea L3 A (Line current L3 A)",
        390: "Potenza ATTIVA istantanea media RMS Watt (Average instantaneous ACTIVE power RMS Watt)"
    }
    
    # Create Modbus TCP client
    client = ModbusTcpClient(cabina, port=port)
    
    try:
        # Connect to the device
        connection_result = client.connect()
        if not connection_result:
            print(f"ERROR: Cannot connect to energy meter at {cabina}:{port}")
            return False
            
        print(f"Connected to energy meter at {cabina}:{port}")
        print(f"Device ID: {nodo}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 80)
        
        # Read each register
        results = {}
        for registro, description in registers.items():
            try:
                # Read 2 registers (32-bit float)
                request = client.read_holding_registers(address=registro, count=2, slave=nodo)
                
                if request.isError():
                    print(f"ERROR reading register {registro}: {request}")
                    continue
                    
                # Decode the 32-bit float value using the new method
                # Convert the two 16-bit registers to a 32-bit float
                # The registers come as [high_word, low_word] for the 32-bit value
                import struct
                
                # Pack the two 16-bit registers into bytes (big endian byte order, little endian word order)
                high_word = request.registers[0]
                low_word = request.registers[1]
                
                # Convert to 32-bit float: word order is little endian (low word first)
                # but byte order within each word is big endian
                packed_data = struct.pack('>HH', low_word, high_word)  # Little word order, big endian bytes
                valore = struct.unpack('>f', packed_data)[0]  # Big endian 32-bit float
                
                # Store result
                results[registro] = valore
                
                # Display result
                print(f"Register {registro:3d}: {valore:10.3f} - {description}")
                
            except Exception as e:
                print(f"ERROR reading register {registro}: {e}")
                
        print("-" * 80)
        print(f"Total registers read: {len(results)}")
        
        # Summary with units
        if results:
            print("\nSUMMARY:")
            if 372 in results:
                print(f"  Voltage (3-phase avg): {results[372]:.2f} V")
            if 374 in results:
                print(f"  Current L1:           {results[374]:.2f} A")
            if 376 in results:
                print(f"  Current L2:           {results[376]:.2f} A") 
            if 378 in results:
                print(f"  Current L3:           {results[378]:.2f} A")
            if 390 in results:
                print(f"  Active Power:         {results[390]:.2f} W")
                
            # Calculate total current if all phases available
            if all(reg in results for reg in [374, 376, 378]):
                total_current = results[374] + results[376] + results[378]
                print(f"  Total Current:        {total_current:.2f} A")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False
        
    finally:
        # Always close the connection
        client.close()
        print("\nConnection closed.")

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

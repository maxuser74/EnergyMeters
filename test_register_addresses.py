#!/usr/bin/env python3
"""
Test specific register addresses that the main app uses
"""
import pandas as pd
from pymodbus.client import ModbusTcpClient

def test_specific_registers():
    print("=== TESTING SPECIFIC REGISTER ADDRESSES ===")
    
    # Load register configuration
    df = pd.read_excel('registri.xlsx')
    registers = df[df['Report'] == 'Yes']
    
    print("Registers to test:")
    for _, row in registers.iterrows():
        reg_addr = row['Registro']
        description = row['Lettura']
        print(f"  - Register {reg_addr}: {description}")
    
    # Test on device 10 (which responded successfully)
    print(f"\n=== TESTING ON DEVICE 10 (192.168.156.77) ===")
    
    try:
        client = ModbusTcpClient('192.168.156.77', port=502, timeout=3)
        if client.connect():
            print("✅ Connected successfully")
            
            for _, row in registers.iterrows():
                reg_addr = row['Registro'] 
                description = row['Lettura']
                
                try:
                    # Test reading 2 registers (for float values)
                    result = client.read_holding_registers(address=reg_addr, count=2, device_id=10)
                    if result.isError():
                        print(f"  ❌ Register {reg_addr} ({description}): {result}")
                    else:
                        values = result.registers
                        print(f"  ✅ Register {reg_addr} ({description}): {values}")
                except Exception as e:
                    print(f"  ❌ Register {reg_addr} ({description}): Exception {e}")
            
            client.close()
        else:
            print("❌ Failed to connect")
            
    except Exception as e:
        print(f"Connection error: {e}")

    # Test on device 11 (which also responded successfully)
    print(f"\n=== TESTING ON DEVICE 11 (192.168.156.75) ===")
    
    try:
        client = ModbusTcpClient('192.168.156.75', port=502, timeout=3)
        if client.connect():
            print("✅ Connected successfully")
            
            for _, row in registers.iterrows():
                reg_addr = row['Registro']
                description = row['Lettura']
                
                try:
                    result = client.read_holding_registers(address=reg_addr, count=2, device_id=11)
                    if result.isError():
                        print(f"  ❌ Register {reg_addr} ({description}): {result}")
                    else:
                        values = result.registers
                        print(f"  ✅ Register {reg_addr} ({description}): {values}")
                except Exception as e:
                    print(f"  ❌ Register {reg_addr} ({description}): Exception {e}")
            
            client.close()
        else:
            print("❌ Failed to connect")
            
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    test_specific_registers()

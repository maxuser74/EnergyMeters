#!/usr/bin/env python3
"""
ModBus connectivity test script
"""
import pandas as pd
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

def test_modbus_connectivity():
    print("=== MODBUS CONNECTIVITY TEST ===")
    
    # Load utilities configuration
    try:
        df = pd.read_excel('Utenze.xlsx')
        print(f"Loaded {len(df)} utilities from Utenze.xlsx")
        print("\nUtilities configuration:")
        for _, row in df.iterrows():
            cabinet = row.get('Cabinet', 'N/A')
            node = row.get('Nodo', 'N/A') 
            gruppo = row.get('Gruppo', 'N/A')
            utenza = row.get('Utenza', 'N/A')
            print(f"  - {utenza} (Cabinet: {cabinet}, Node: {node}, Group: {gruppo})")
            
        # Test connectivity to each utility
        print("\n=== CONNECTIVITY TESTS ===")
        for _, row in df.iterrows():
            utenza = row.get('Utenza', 'Unknown')
            node = row.get('Nodo', 1)
            
            # Try common ModBus IP addresses
            test_ips = [
                '192.168.1.100',
                '192.168.0.100', 
                '127.0.0.1',
                '192.168.156.77',
                '192.168.156.75'
            ]
            
            print(f"\nTesting {utenza} (Node {node}):")
            connected = False
            
            for ip in test_ips:
                try:
                    client = ModbusTcpClient(ip, port=502, timeout=2)
                    if client.connect():
                        print(f"  ✅ Connected to {ip}:502")
                        
                        # Try reading a simple register
                        try:
                            result = client.read_holding_registers(address=0, count=1, device_id=node)
                            if not result.isError():
                                print(f"  ✅ Successfully read register 0 from device {node}")
                                connected = True
                            else:
                                print(f"  ⚠️  Connected but register read failed: {result}")
                        except Exception as e:
                            print(f"  ⚠️  Connected but register read error: {e}")
                        
                        client.close()
                        break
                    else:
                        print(f"  ❌ Failed to connect to {ip}:502")
                except Exception as e:
                    print(f"  ❌ Connection error to {ip}:502: {e}")
            
            if not connected:
                print(f"  ❌ No successful connections found for {utenza}")
                
    except Exception as e:
        print(f"Error loading configuration: {e}")

if __name__ == "__main__":
    test_modbus_connectivity()

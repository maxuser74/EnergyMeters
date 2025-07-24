#!/usr/bin/env python3
import pandas as pd

# Read all data from both relevant files
print("=== UTENZE.XLSX ===")
df_utenze = pd.read_excel('Utenze.xlsx')
print("All utilities to monitor:")
print(df_utenze.to_string(index=False))
print(f"Total utilities: {len(df_utenze)}")
print()

print("=== REGISTRI.XLSX ===")
df_registri = pd.read_excel('registri.xlsx')
print("Registers to read:")
print(df_registri.to_string(index=False))
print(f"Total registers: {len(df_registri)}")
print()

print("=== REGISTRY.XLSX (for reference) ===")
df_registry = pd.read_excel('registry.xlsx')
print("All available registers:")
print(df_registry.to_string(index=False))
print(f"Total available registers: {len(df_registry)}")
print()

# Create IP mapping for cabinets
print("=== CABINET IP MAPPING ===")
cabinet_ips = {
    1: '192.168.156.75',
    2: '192.168.156.76', 
    3: '192.168.156.77'
}

for cabinet in df_utenze['Cabinet'].unique():
    ip = cabinet_ips.get(cabinet, 'UNKNOWN')
    utilities = df_utenze[df_utenze['Cabinet'] == cabinet]
    print(f"Cabinet {cabinet} (IP: {ip}):")
    for _, row in utilities.iterrows():
        print(f"  - Node {row['Nodo']}: {row['Utenza']}")
print()

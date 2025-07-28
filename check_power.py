#!/usr/bin/env python3
"""
Check all Power registers in registri.xlsx
"""
import sys
import os

# Add the virtual environment to the path
venv_path = r"C:\Users\mpasseri\OneDrive - CAMOZZI GROUP SPA\Documenti\VSCode\EnergyMeters\.venv\Lib\site-packages"
sys.path.insert(0, venv_path)

try:
    import pandas as pd
    
    # Read the Excel file
    df_registri = pd.read_excel('registri.xlsx')
    
    print("=== ALL POWER REGISTERS ===")
    
    # Find all Power type registers
    power_registers = df_registri[df_registri['Type'] == 'Power']
    
    if len(power_registers) > 0:
        print(f"Found {len(power_registers)} Power registers:")
        for idx, row in power_registers.iterrows():
            registro = row.get('Registro', 'N/A')
            lettura = row.get('Lettura', 'N/A')
            report = row.get('Report', 'N/A')
            print(f"   • Register {registro}: {lettura} (Report: {report})")
    else:
        print("No Power registers found in the Excel file.")
        
    # Check if any power-related registers exist (case insensitive)
    power_like = df_registri[df_registri['Type'].astype(str).str.contains('power', case=False, na=False)]
    if len(power_like) > 0:
        print(f"\nFound {len(power_like)} power-related registers:")
        for idx, row in power_like.iterrows():
            registro = row.get('Registro', 'N/A')
            lettura = row.get('Lettura', 'N/A')
            type_val = row.get('Type', 'N/A')
            report = row.get('Report', 'N/A')
            print(f"   • Register {registro}: {lettura} (Type: {type_val}, Report: {report})")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

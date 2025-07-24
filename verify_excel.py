#!/usr/bin/env python3
import pandas as pd

# Check the generated Excel file
filename = 'energy_meter_readings_utilities_20250722_180420.xlsx'

try:
    df = pd.read_excel(filename)
    print("=== EXCEL FILE VERIFICATION ===")
    print(f"File: {filename}")
    print(f"Shape: {df.shape}")
    print("\nColumn names:")
    for i, col in enumerate(df.columns):
        print(f"  {i+1}. {col}")
    
    print("\nSample data (first row):")
    first_row = df.iloc[0]
    for col in df.columns:
        if 'Current' in col or 'Energy' in col or 'Positive' in col:
            print(f"  {col}: {first_row[col]}")
            
    # Check if target units are in column names
    print("\n=== UNIT VERIFICATION ===")
    units_found = []
    for col in df.columns:
        if '(' in col and ')' in col:
            unit = col[col.rfind('(')+1:col.rfind(')')]
            units_found.append((col, unit))
    
    if units_found:
        print("✅ Target units found in column names:")
        for col_name, unit in units_found:
            print(f"   {col_name} → Unit: {unit}")
    else:
        print("❌ No units found in column names")
        
except Exception as e:
    print(f"Error reading file: {e}")

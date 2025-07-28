#!/usr/bin/env python3
"""
Script to analyze registri.xlsx file structure
"""
import pandas as pd
import sys

try:
    # Read the Excel file
    df = pd.read_excel('registri.xlsx')
    
    print("=== REGISTRI.XLSX ANALYSIS ===")
    print(f"Total rows: {len(df)}")
    print(f"Total columns: {len(df.columns)}")
    print("\nColumns:", df.columns.tolist())
    
    print("\n=== FIRST 10 ROWS ===")
    print(df.head(10).to_string())
    
    if 'Type' in df.columns:
        print("\n=== UNIQUE VALUES IN 'Type' COLUMN ===")
        unique_types = df['Type'].dropna().unique()
        for i, type_val in enumerate(unique_types, 1):
            count = len(df[df['Type'] == type_val])
            print(f"{i}. '{type_val}' (appears {count} times)")
    else:
        print("\n⚠️  No 'Type' column found!")
    
    if 'Report' in df.columns:
        print("\n=== REPORT COLUMN VALUES ===")
        report_values = df['Report'].value_counts()
        print(report_values)
    
    # Show only records where Report = Yes
    if 'Report' in df.columns:
        report_yes = df[df['Report'].astype(str).str.lower().isin(['yes', 'y', '1', 'true'])]
        print(f"\n=== RECORDS WITH Report=Yes ({len(report_yes)} records) ===")
        if len(report_yes) > 0:
            print(report_yes[['Registro', 'Lettura', 'Type', 'Report']].to_string())
        
except Exception as e:
    print(f"Error reading registri.xlsx: {e}")
    sys.exit(1)

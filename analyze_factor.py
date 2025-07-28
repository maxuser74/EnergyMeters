#!/usr/bin/env python3
"""
Analyze the Factor column in registri.xlsx
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
    
    print("=== REGISTRI.XLSX FACTOR COLUMN ANALYSIS ===")
    print(f"Total rows: {len(df_registri)}")
    print("\nColumns:", df_registri.columns.tolist())
    
    if 'Factor' in df_registri.columns:
        print("\n=== FACTOR COLUMN DETAILS ===")
        print("Factor column values:")
        factor_values = df_registri['Factor'].dropna().unique()
        for factor in sorted(factor_values):
            count = len(df_registri[df_registri['Factor'] == factor])
            print(f"  {factor} (appears {count} times)")
        
        print(f"\nFactor statistics:")
        print(f"  Non-null values: {df_registri['Factor'].notna().sum()}")
        print(f"  Null values: {df_registri['Factor'].isna().sum()}")
        
        # Show records with Report=Yes and their Factor values
        report_yes = df_registri[df_registri['Report'].astype(str).str.lower().isin(['yes', 'y', '1', 'true'])]
        print(f"\n=== REPORT=YES RECORDS WITH FACTOR ({len(report_yes)} records) ===")
        for idx, row in report_yes.iterrows():
            registro = row.get('Registro', 'N/A')
            lettura = row.get('Lettura', 'N/A')
            readings = row.get('Readings', 'N/A')
            convert_to = row.get('Convert to', 'N/A')
            factor = row.get('Factor', 'N/A')
            print(f"Register {registro}: {lettura}")
            print(f"   Readings: {readings}")
            print(f"   Convert to: {convert_to}")
            print(f"   Factor: {factor}")
            print()
    else:
        print("\n⚠️  No 'Factor' column found!")
        
    # Show all relevant columns for conversion
    relevant_cols = ['Registro', 'Lettura', 'Readings', 'Convert to', 'Factor', 'Report']
    available_cols = [col for col in relevant_cols if col in df_registri.columns]
    
    print(f"=== CONVERSION-RELEVANT COLUMNS ===")
    print(f"Available columns: {available_cols}")
    
    if len(available_cols) >= 3:
        print(f"\nSample of relevant data:")
        sample_data = df_registri[available_cols].head(10)
        print(sample_data.to_string())
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

import os
import sys

# Add the virtual environment to the path
venv_path = r"C:\Users\mpasseri\OneDrive - CAMOZZI GROUP SPA\Documenti\VSCode\EnergyMeters\.venv\Lib\site-packages"
sys.path.insert(0, venv_path)

try:
    import pandas as pd
    
    # Read the Excel file
    df = pd.read_excel('registri.xlsx')
    
    print("=== REGISTRI.XLSX ANALYSIS ===")
    print(f"Total rows: {len(df)}")
    print(f"Total columns: {len(df.columns)}")
    print("\nColumns:", df.columns.tolist())
    
    print("\n=== FIRST 10 ROWS ===")
    for i, row in df.head(10).iterrows():
        print(f"Row {i}: {dict(row)}")
    
    if 'Type' in df.columns:
        print("\n=== UNIQUE VALUES IN 'Type' COLUMN ===")
        unique_types = df['Type'].dropna().unique()
        for i, type_val in enumerate(unique_types, 1):
            count = len(df[df['Type'] == type_val])
            print(f"{i}. '{type_val}' (appears {count} times)")
    else:
        print("\n⚠️  No 'Type' column found!")
        
    # Show structure for badge correction
    if 'Report' in df.columns:
        report_yes = df[df['Report'].astype(str).str.lower().isin(['yes', 'y', '1', 'true'])]
        print(f"\n=== RECORDS WITH Report=Yes FOR BADGES ({len(report_yes)} records) ===")
        if len(report_yes) > 0:
            for i, row in report_yes.iterrows():
                registro = row.get('Registro', 'N/A')
                lettura = row.get('Lettura', 'N/A')
                type_val = row.get('Type', 'N/A')
                print(f"Register {registro}: {lettura} -> Type: {type_val}")
                
except ImportError as e:
    print(f"Import error: {e}")
except Exception as e:
    print(f"Error: {e}")

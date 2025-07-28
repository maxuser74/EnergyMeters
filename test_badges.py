#!/usr/bin/env python3
"""
Test script to verify badge categorization from registri.xlsx
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
    
    print("=== BADGE CATEGORIZATION TEST ===")
    print("Based on registri.xlsx 'Type' column mapping:")
    print()
    
    # Only process Report=Yes records
    report_yes = df_registri[df_registri['Report'].astype(str).str.lower().isin(['yes', 'y', '1', 'true'])]
    
    badge_mapping = {}
    
    for idx, row in report_yes.iterrows():
        registro = row.get('Registro', 'N/A')
        lettura = row.get('Lettura', 'N/A')
        excel_type = row.get('Type', 'N/A')
        
        # Apply the same logic as in the code
        if pd.notna(row.get('Type')):
            category = str(row['Type']).strip().lower()
            category = category.replace(' ', '_').replace('/', '_')
            if category == 'currents':
                category = 'current'
            elif category == 'voltages':
                category = 'voltage'
            elif category == 'power_factors':
                category = 'power_factor'
            elif category == 'power':
                category = 'power'
        else:
            category = lettura.strip().replace(' ', '_').replace('/', '_').lower()
        
        if category not in badge_mapping:
            badge_mapping[category] = []
        
        badge_mapping[category].append({
            'registro': registro,
            'lettura': lettura,
            'excel_type': excel_type
        })
    
    print("EXPECTED BADGES:")
    for badge_category, registers in badge_mapping.items():
        print(f"\n🏷️  {badge_category.upper()} BADGE ({len(registers)} registers):")
        for reg in registers:
            print(f"   • Register {reg['registro']}: {reg['lettura']} (Excel Type: {reg['excel_type']})")
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total badges: {len(badge_mapping)}")
    print(f"   Total registers: {sum(len(regs) for regs in badge_mapping.values())}")
    
    # Check if all expected badge types are covered
    expected_badges = ['current', 'voltage', 'power_factor', 'power']
    missing_badges = [b for b in expected_badges if b not in badge_mapping]
    extra_badges = [b for b in badge_mapping if b not in expected_badges]
    
    if missing_badges:
        print(f"   ⚠️  Missing expected badges: {missing_badges}")
    if extra_badges:
        print(f"   ℹ️  Additional badges found: {extra_badges}")
    if not missing_badges and not extra_badges:
        print(f"   ✅ All badge categories correctly mapped!")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

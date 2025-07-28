#!/usr/bin/env python3
"""
Simple test to verify Factor column loading without full server initialization
"""
import pandas as pd
import os

def test_factor_excel_loading():
    """Simple test of Excel Factor loading"""
    print("🔍 Testing Excel Factor column loading...")
    
    try:
        # Load Excel file
        df = pd.read_excel("registri.xlsx")
        print(f"✅ Loaded Excel with {len(df)} rows")
        
        # Filter for Report = Yes
        report_df = df[df['Report'] == 'Yes'].copy()
        print(f"📊 Found {len(report_df)} registers with Report = Yes")
        
        if 'Factor' not in df.columns:
            print("❌ Factor column not found")
            return False
        
        print("\n📋 Registers with Factors:")
        for idx, row in report_df.iterrows():
            name = row['Name']
            factor = row['Factor']
            readings = row.get('Readings', 'N/A')
            convert_to = row.get('Convert to', 'N/A')
            register_type = row.get('Type', 'Unknown')
            
            print(f"  📌 {name}")
            print(f"     Type: {register_type}")
            print(f"     Factor: {factor}")
            print(f"     {readings} → {convert_to}")
            
            # Test conversion if factor is valid
            if pd.notna(factor) and factor != 0:
                test_value = 1000
                converted = test_value * factor
                print(f"     Test: {test_value} * {factor} = {converted}")
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Simple Factor Excel Test")
    print("=" * 40)
    
    if test_factor_excel_loading():
        print("✅ Factor Excel loading test passed!")
    else:
        print("❌ Factor Excel loading test failed!")

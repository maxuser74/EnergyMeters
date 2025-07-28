#!/usr/bin/env python3
"""
Test script to verify Factor-based conversion from registri.xlsx
"""
import pandas as pd
import os

def test_factor_loading():
    """Test loading and analyzing Factor column from registri.xlsx"""
    
    # Check if registri.xlsx exists
    file_path = "registri.xlsx"
    if not os.path.exists(file_path):
        print(f"❌ File {file_path} not found")
        return
    
    print("📁 Loading registri.xlsx for Factor analysis...")
    
    try:
        # Load the Excel file
        df = pd.read_excel(file_path)
        
        print(f"📊 Loaded {len(df)} rows from Excel file")
        print(f"📋 Columns: {list(df.columns)}")
        
        # Check if Factor column exists
        if 'Factor' not in df.columns:
            print("❌ Factor column not found in Excel file")
            return
        
        # Filter for Report = Yes
        report_df = df[df['Report'] == 'Yes'].copy()
        print(f"\n📈 Found {len(report_df)} registers with Report = Yes")
        
        # Analyze Factor column
        print("\n🔍 Factor Analysis:")
        print(f"   Total registers with Report=Yes: {len(report_df)}")
        print(f"   Factor column stats:")
        print(f"     - Non-null factors: {report_df['Factor'].notna().sum()}")
        print(f"     - Null factors: {report_df['Factor'].isna().sum()}")
        print(f"     - Unique factors: {report_df['Factor'].nunique()}")
        print(f"     - Factor range: {report_df['Factor'].min()} to {report_df['Factor'].max()}")
        
        # Show detailed factor information
        print("\n📋 Detailed Factor Information:")
        for idx, row in report_df.iterrows():
            register_name = row['Name']
            readings = row.get('Readings', 'N/A')
            convert_to = row.get('Convert to', 'N/A')
            factor = row.get('Factor', 'N/A')
            register_type = row.get('Type', 'Unknown')
            
            print(f"   {register_name}:")
            print(f"     Type: {register_type}")
            print(f"     Readings: {readings}")
            print(f"     Convert to: {convert_to}")
            print(f"     Factor: {factor}")
            
            # Test conversion calculation
            if pd.notna(factor) and factor != 0:
                # Simulate a test reading value
                test_reading = 1000  # Example raw value
                converted_value = test_reading * factor
                print(f"     Test conversion: {test_reading} * {factor} = {converted_value}")
            print()
        
        print("✅ Factor analysis complete!")
        
    except Exception as e:
        print(f"❌ Error loading Excel file: {e}")

def test_conversion_logic():
    """Test the conversion logic with sample values"""
    print("\n🧮 Testing conversion logic...")
    
    # Test cases with different factors
    test_cases = [
        {"name": "Current L1", "raw_value": 2500, "factor": 0.01, "expected": 25.0},
        {"name": "Voltage L1-N", "raw_value": 23000, "factor": 0.01, "expected": 230.0},
        {"name": "Power Factor L1", "raw_value": 95, "factor": 0.01, "expected": 0.95},
        {"name": "Active Power", "raw_value": 15000, "factor": 0.1, "expected": 1500.0},
    ]
    
    print("Test cases:")
    for case in test_cases:
        raw = case["raw_value"]
        factor = case["factor"]
        expected = case["expected"]
        calculated = raw * factor
        
        status = "✅" if abs(calculated - expected) < 0.001 else "❌"
        print(f"  {status} {case['name']}: {raw} * {factor} = {calculated} (expected: {expected})")
    
    print("\n🔢 Conversion logic test complete!")

if __name__ == "__main__":
    print("🚀 Testing Factor-based conversion system...")
    print("=" * 50)
    
    test_factor_loading()
    test_conversion_logic()
    
    print("\n" + "=" * 50)
    print("✅ Factor conversion testing complete!")

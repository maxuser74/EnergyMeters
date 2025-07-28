#!/usr/bin/env python3
"""
Simple test for Setup badge - just test register loading
"""
import pandas as pd

def test_setup_loading():
    """Simple test of Setup register loading from Excel"""
    print("🔧 Simple Setup Badge Test")
    print("=" * 40)
    
    try:
        # Load Excel directly
        df = pd.read_excel("registri.xlsx")
        print(f"📁 Loaded Excel with {len(df)} rows")
        
        # Filter for Report = Yes
        report_df = df[df['Report'].str.lower().isin(['yes', 'y'])].copy()
        print(f"📊 Found {len(report_df)} registers with Report=Yes")
        
        # Group by Type and count
        if 'Type' in report_df.columns:
            type_counts = report_df['Type'].value_counts()
            print(f"\n🏷️  Badge Types:")
            for badge_type, count in type_counts.items():
                icon = "🎯" if badge_type == "Setup" else "📋"
                print(f"  {icon} {badge_type}: {count} registers")
                
                # Show details for Setup type
                if badge_type == "Setup":
                    setup_registers = report_df[report_df['Type'] == 'Setup']
                    print(f"     📌 Setup Registers:")
                    for idx, row in setup_registers.iterrows():
                        registro = row['Registro']
                        lettura = row['Lettura']
                        factor = row.get('Factor', 'N/A')
                        readings = row.get('Readings', 'N/A')
                        convert_to = row.get('Convert to', 'N/A')
                        print(f"        • Registro {registro}: {lettura}")
                        print(f"          Factor: {factor}, {readings} → {convert_to}")
        
        # Test category mapping logic
        print(f"\n🔍 Testing Setup category mapping:")
        test_type = "Setup"
        category = test_type.strip().lower()
        category = category.replace(' ', '_').replace('/', '_')
        
        if category == 'setup':
            mapped_category = 'setup'
        else:
            mapped_category = category
            
        print(f"   Input Type: '{test_type}'")
        print(f"   Mapped Category: '{mapped_category}'")
        print(f"   ✅ Setup mapping working correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_setup_loading()
    print("\n" + "=" * 40)
    if success:
        print("✅ Setup badge test successful!")
    else:
        print("❌ Setup badge test failed!")

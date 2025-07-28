#!/usr/bin/env python3
"""
Analyze registri.xlsx for Setup badge candidates
"""
import pandas as pd
import os

def analyze_setup_registers():
    """Analyze registri.xlsx for potential Setup badge registers"""
    
    if not os.path.exists("registri.xlsx"):
        print("❌ registri.xlsx file not found")
        return
    
    try:
        # Load Excel file
        df = pd.read_excel("registri.xlsx")
        print(f"📁 Loaded Excel with {len(df)} rows")
        print(f"📋 Columns: {list(df.columns)}")
        
        print("\n🔍 All registers analysis:")
        print("=" * 80)
        
        # Show all registers with their Type and Report status
        for idx, row in df.iterrows():
            registro = row.get('Registro', 'N/A')
            lettura = row.get('Lettura', 'N/A')
            register_type = row.get('Type', 'N/A')
            report = row.get('Report', 'No')
            factor = row.get('Factor', 'N/A')
            readings = row.get('Readings', 'N/A')
            convert_to = row.get('Convert to', 'N/A')
            
            # Highlight potential setup registers
            is_setup_candidate = False
            if pd.notna(register_type):
                type_lower = str(register_type).lower()
                if any(keyword in type_lower for keyword in ['setup', 'config', 'parameter', 'setting']):
                    is_setup_candidate = True
            
            if pd.notna(lettura):
                lettura_lower = str(lettura).lower()
                if any(keyword in lettura_lower for keyword in ['setup', 'config', 'parameter', 'setting', 'mode']):
                    is_setup_candidate = True
            
            status_icon = "🎯" if is_setup_candidate else ("✅" if str(report).lower() in ['yes', 'y'] else "⚪")
            
            print(f"{status_icon} Registro {registro}: {lettura}")
            print(f"    Type: {register_type}")
            print(f"    Report: {report}")
            print(f"    Factor: {factor}")
            print(f"    {readings} → {convert_to}")
            print()
        
        # Summary of current Report=Yes registers
        report_yes = df[df['Report'].str.lower().isin(['yes', 'y'])].copy() if 'Report' in df.columns else pd.DataFrame()
        print(f"\n📊 Current Report=Yes registers: {len(report_yes)}")
        
        if len(report_yes) > 0:
            print("\nCurrent badge types:")
            if 'Type' in report_yes.columns:
                type_counts = report_yes['Type'].value_counts()
                for badge_type, count in type_counts.items():
                    print(f"  - {badge_type}: {count} registers")
        
        # Look for potential Setup registers
        setup_candidates = []
        for idx, row in df.iterrows():
            registro = row.get('Registro')
            lettura = str(row.get('Lettura', '')).lower()
            register_type = str(row.get('Type', '')).lower()
            
            # Check if this could be a setup register
            setup_keywords = ['setup', 'config', 'parameter', 'setting', 'mode', 'control']
            if any(keyword in lettura for keyword in setup_keywords) or any(keyword in register_type for keyword in setup_keywords):
                setup_candidates.append({
                    'registro': registro,
                    'lettura': row.get('Lettura'),
                    'type': row.get('Type'),
                    'report': row.get('Report'),
                    'factor': row.get('Factor'),
                    'readings': row.get('Readings'),
                    'convert_to': row.get('Convert to')
                })
        
        print(f"\n🎯 Potential Setup badge candidates: {len(setup_candidates)}")
        for candidate in setup_candidates:
            print(f"  📌 Registro {candidate['registro']}: {candidate['lettura']}")
            print(f"     Current Report: {candidate['report']}")
            print(f"     Type: {candidate['type']}")
        
        return setup_candidates
        
    except Exception as e:
        print(f"❌ Error analyzing Excel: {e}")
        return []

if __name__ == "__main__":
    print("🔍 Analyzing registri.xlsx for Setup badge candidates...")
    print("=" * 60)
    
    candidates = analyze_setup_registers()
    
    print("\n" + "=" * 60)
    print("✅ Analysis complete!")

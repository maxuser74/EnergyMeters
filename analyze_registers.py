#!/usr/bin/env python3
import pandas as pd

# Read and analyze the register information
print("=== REGISTER ADDRESS CALCULATION AND UNIT CONVERSION ANALYSIS ===")
df = pd.read_excel('registri.xlsx')

print(f"\nColumns found: {df.columns.tolist()}")
print(f"Total registers: {len(df)}")

print("\nRegister Analysis:")
for i, row in df.iterrows():
    end_address = int(row['Registro'])
    description = str(row['Lettura'])
    data_type = str(row['Lenght'])
    source_unit = str(row['Readings']) if 'Readings' in row else 'N/A'
    target_unit = str(row['Convert to']) if 'Convert to' in row else 'N/A'
    
    # Calculate register length based on data type
    if data_type.lower() == 'float':
        # Float = 32-bit = 2 registers (16-bit each)
        register_count = 2
        start_address = end_address - 1
    elif 'long long' in data_type.lower():
        # Signed long long = 64-bit = 4 registers (16-bit each)
        register_count = 4
        start_address = end_address - 3
    else:
        # Default to 2 registers for unknown types
        register_count = 2 
        start_address = end_address - 1
        print(f"  WARNING: Unknown data type '{data_type}', assuming float")
    
    print(f"\nRegister {i+1}:")
    print(f"  Description: {description}")
    print(f"  End Address: {end_address}")
    print(f"  Data Type: {data_type}")
    print(f"  Register Count: {register_count}")
    print(f"  Start Address: {start_address}")
    print(f"  Address Range: {start_address} to {end_address}")
    print(f"  Source Unit: {source_unit}")
    print(f"  Target Unit: {target_unit}")
    
    # Show conversion needed
    if source_unit != target_unit:
        print(f"  🔄 CONVERSION NEEDED: {source_unit} → {target_unit}")
    else:
        print(f"  ✅ NO CONVERSION: Same units ({source_unit})")

print("\n=== SUMMARY ===")
print("Key findings:")
print("1. 'Registro' column contains END addresses")
print("2. 'Lenght' specifies data type which determines register count")
print("3. Need to calculate start address = end_address - (register_count - 1)")
print("4. Float = 2 registers, Long Long = 4 registers")
print("5. 'Readings' column specifies source measurement units")
print("6. 'Convert to' column specifies target display units")
print("7. Unit conversion must be applied during data processing")

# Show conversion summary
print("\n=== UNIT CONVERSION REQUIREMENTS ===")
conversions_needed = []
no_conversions = []

for i, row in df.iterrows():
    source_unit = str(row['Readings']) if 'Readings' in row else 'N/A'
    target_unit = str(row['Convert to']) if 'Convert to' in row else 'N/A'
    description = str(row['Lettura'])
    
    if source_unit != target_unit:
        conversions_needed.append(f"{description}: {source_unit} → {target_unit}")
    else:
        no_conversions.append(f"{description}: {source_unit}")

if conversions_needed:
    print("Conversions needed:")
    for conversion in conversions_needed:
        print(f"  🔄 {conversion}")

if no_conversions:
    print("No conversions needed:")
    for item in no_conversions:
        print(f"  ✅ {item}")

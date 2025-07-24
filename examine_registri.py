#!/usr/bin/env python3
import pandas as pd

# Read registri.xlsx and examine all columns
print("=== EXAMINING registri.xlsx ===")
df = pd.read_excel('registri.xlsx')

print(f"Columns: {df.columns.tolist()}")
print(f"Shape: {df.shape}")
print("\nAll data:")
print(df.to_string(index=False))

print("\nRow by row analysis:")
for i, row in df.iterrows():
    print(f"Row {i}:")
    for col in df.columns:
        print(f"  {col}: {row[col]}")
    print()

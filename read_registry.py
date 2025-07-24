import pandas as pd

# Read the registry file
df = pd.read_excel('registry.xlsx')
print("Registry content:")
print(df.to_string())
print("\nColumns:", df.columns.tolist())
print("\nFirst few rows with details:")
for idx, row in df.head(20).iterrows():
    print(f"Register {row.iloc[0]}: {row.iloc[1]}")

#!/usr/bin/env python3
import pandas as pd

# Read Utenze.xlsx
print("Reading Utenze.xlsx...")
try:
    df_utenze = pd.read_excel('Utenze.xlsx')
    print("Utenze.xlsx - Columns:", df_utenze.columns.tolist())
    print("Utenze.xlsx - Shape:", df_utenze.shape)
    print("Utenze.xlsx - First few rows:")
    print(df_utenze.head())
    print()
except Exception as e:
    print("Error reading Utenze.xlsx:", e)
    print()

# Read registri.xlsx
print("Reading registri.xlsx...")
try:
    df_registri = pd.read_excel('registri.xlsx')
    print("registri.xlsx - Columns:", df_registri.columns.tolist())
    print("registri.xlsx - Shape:", df_registri.shape)
    print("registri.xlsx - First few rows:")
    print(df_registri.head())
    print()
except Exception as e:
    print("Error reading registri.xlsx:", e)
    print()

# Also try reading registry.xlsx if it exists
print("Reading registry.xlsx...")
try:
    df_registry = pd.read_excel('registry.xlsx')
    print("registry.xlsx - Columns:", df_registry.columns.tolist())
    print("registry.xlsx - Shape:", df_registry.shape)
    print("registry.xlsx - First few rows:")
    print(df_registry.head())
except Exception as e:
    print("Error reading registry.xlsx:", e)

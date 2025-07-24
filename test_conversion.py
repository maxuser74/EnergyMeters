#!/usr/bin/env python3
# Quick test of unit conversion function

def convert_units(value, source_unit, target_unit):
    """Convert value from source unit to target unit"""
    if value is None:
        return None
    
    # Normalize unit names (remove spaces, convert to lowercase for comparison)
    source = source_unit.lower().replace(' ', '').replace('_', '')
    target = target_unit.lower().replace(' ', '').replace('_', '')
    
    # If source and target are the same, no conversion needed
    if source == target:
        return value
    
    # Define conversion rules
    conversions = {
        # Energy conversions
        ('tenthofwatts', 'kwh'): lambda x: x / 10000.0,  # Tenth of watts to kWh (divide by 10 for watts, then by 3600*1000 for Wh to kWh, simplified to /10000)
        ('w/10', 'kwh'): lambda x: x / 10000.0,  # Same as above
        ('watts', 'kwh'): lambda x: x / 3600000.0,  # Watts to kWh 
        ('wh', 'kwh'): lambda x: x / 1000.0,  # Wh to kWh
        
        # Power conversions
        ('tenthofwatts', 'w'): lambda x: x / 10.0,  # Tenth of watts to watts
        ('w/10', 'w'): lambda x: x / 10.0,  # Same as above
        
        # Current conversions (typically no conversion needed for A to A)
        ('a', 'a'): lambda x: x,
        
        # Voltage conversions (typically no conversion needed for V to V)  
        ('v', 'v'): lambda x: x,
    }
    
    # Try to find a conversion
    conversion_key = (source, target)
    if conversion_key in conversions:
        converted_value = conversions[conversion_key](value)
        return round(converted_value, 3)  # Round to 3 decimal places for precision
    
    # If no conversion found, log warning and return original value
    print(f"    WARNING: No conversion available from '{source_unit}' to '{target_unit}', using original value")
    return value

# Test conversions
print("=== UNIT CONVERSION TEST ===")

test_cases = [
    (100.0, "A", "A"),  # No conversion
    (1000.0, "Tenth of watts", "Kwh"),  # Should convert
    (50000.0, "Tenth of watts", "Kwh"),  # Larger value
]

for value, source, target in test_cases:
    result = convert_units(value, source, target)
    print(f"{value} {source} → {result} {target}")
    
print("\nConversion logic explanation:")
print("Tenth of watts → Kwh:")
print("  1. Tenth of watts / 10 = watts")  
print("  2. watts / 3600000 = kWh (since 1 kWh = 3.6M watt-seconds)")
print("  3. Combined: value / 10000.0")
print("  Example: 50000 tenth-of-watts → 5.0 kWh")

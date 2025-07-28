#!/usr/bin/env python3
"""
Test the updated active power calculation
"""
import sys
import os
import math

# Add the virtual environment to the path
venv_path = r"C:\Users\mpasseri\OneDrive - CAMOZZI GROUP SPA\Documenti\VSCode\EnergyMeters\.venv\Lib\site-packages"
sys.path.insert(0, venv_path)

def test_power_calculation():
    # Sample data similar to what we'd get from registers
    volts = [400.2, 399.8, 401.1]  # Phase voltages
    amps = [200.5, 198.7, 201.2]   # Phase currents  
    pfs = [0.91, 0.89, 0.92]       # Power factors
    
    print("=== ACTIVE POWER CALCULATION TEST ===")
    print(f"Input Data:")
    print(f"  Voltages: {volts} V")
    print(f"  Currents: {amps} A") 
    print(f"  Power Factors: {pfs}")
    print()
    
    # Method 1: Sum of individual phase powers (P = V * I * cosφ for each phase)
    p_per_phase = (volts[0]*amps[0]*pfs[0] + volts[1]*amps[1]*pfs[1] + volts[2]*amps[2]*pfs[2]) / 1000
    print(f"Method 1 - Sum of Phase Powers:")
    print(f"  P1 = {volts[0]} × {amps[0]} × {pfs[0]} = {round(volts[0]*amps[0]*pfs[0], 1)} W")
    print(f"  P2 = {volts[1]} × {amps[1]} × {pfs[1]} = {round(volts[1]*amps[1]*pfs[1], 1)} W")
    print(f"  P3 = {volts[2]} × {amps[2]} × {pfs[2]} = {round(volts[2]*amps[2]*pfs[2], 1)} W")
    print(f"  Total = {round(p_per_phase, 2)} kW")
    print()
    
    # Method 2: Three-phase power formula P = √3 * V_line * I_avg * cosφ_avg
    v_line = max(volts)  # Use highest voltage as line voltage
    i_avg = sum(amps) / len(amps)
    cosph_avg = sum(pfs) / len(pfs)
    p_three_phase = (math.sqrt(3) * v_line * i_avg * cosph_avg) / 1000
    
    print(f"Method 2 - Three-Phase Formula (P = √3 × V × I × cosφ):")
    print(f"  V_line = {v_line} V (max voltage)")
    print(f"  I_avg = {round(i_avg, 1)} A")
    print(f"  cosφ_avg = {round(cosph_avg, 3)}")
    print(f"  P = √3 × {v_line} × {round(i_avg, 1)} × {round(cosph_avg, 3)} = {round(p_three_phase, 2)} kW")
    print()
    
    # Choose final value
    p_final = min(p_per_phase, p_three_phase)
    print(f"Final calculated power: {round(p_final, 2)} kW (using conservative approach)")
    
    # Show difference
    diff_percent = abs(p_per_phase - p_three_phase) / p_per_phase * 100
    print(f"Difference between methods: {round(diff_percent, 1)}%")
    
    return p_final

if __name__ == "__main__":
    test_power_calculation()

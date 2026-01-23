# Configuration

<!-- Configuration settings for the Energy Meter application -->

measurement_interval_ms: 100
modbus_timeout_s: 3

# Rounding Configuration (Decimals)
decimals_V: 1
decimals_A: 1
decimals_PF: 2
decimals_kW: 1

# Integer Length Configuration (Padding)
integers_V: 3
integers_A: 4
integers_PF: 1

# Power Factor Color Ranges
# Values below pf_red_max are RED
# Values between pf_red_max and pf_yellow_max are YELLOW
# Values above pf_yellow_max are GREEN
pf_red_max: 0.4
pf_yellow_max: 0.5

# Voltage Ranges (Red if outside these ranges)
# Line-to-Line (L1-L2, L2-L3, L3-L1) - Typically 380-420V
v_ll_min: 380
v_ll_max: 430

# Line-to-Neutral (L1-N, L2-N, L3-N) - Typically 210-250V
v_ln_min: 210
v_ln_max: 250

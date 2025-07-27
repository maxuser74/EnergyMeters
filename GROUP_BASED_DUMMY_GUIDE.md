# Group-Based Dummy Data Configuration

## Overview

The energy meter system now supports **Group-based dummy data generation**. Only machines explicitly marked with `Group = "Dummy"` in the Utenze.xlsx file will generate random test data. All other machines must rely on real field device connections.

## Configuration

### Excel File Setup (Utenze.xlsx)

The `Gruppo` column in Utenze.xlsx determines machine behavior:

| Cabinet | Nodo | Utenza | Gruppo | Behavior |
|---------|------|--------|--------|----------|
| 1 | 1 | Production Line A | Production | ⚡ **Real Device**: Connects to Modbus TCP at 192.168.156.75 |
| 2 | 1 | Test Machine B | **Dummy** | 🎲 **Random Data**: Generates realistic test values |
| 3 | 2 | Maintenance Unit | Maintenance | ⚡ **Real Device**: Connects to Modbus TCP at 192.168.156.77 |
| 1 | 3 | Demo Equipment | **dummy** | 🎲 **Random Data**: Case-insensitive matching |

### Behavior Rules

1. **Group = "Dummy"** (case-insensitive):
   - ✅ Generates random realistic data (voltage, current, power factor)
   - ✅ Always shows status "OK"
   - ✅ Updates with new random values on each refresh
   - ✅ Labeled with `[DUMMY]` prefix in the interface

2. **Any other Group value**:
   - ⚡ Attempts real Modbus TCP connection to field device
   - ⚡ Uses IP address based on Cabinet number
   - ⚡ Shows actual connection status (OK/PARTIAL/FAILED)
   - ⚡ No fallback to dummy data if connection fails

3. **MODE = 'DUMMY'** (Global Override):
   - 🧪 All machines generate test data regardless of Group
   - 🧪 Used for complete system testing
   - 🧪 Shows `[GLOBAL TEST]` labeling

## IP Address Mapping

Cabinet numbers map to IP addresses:
- Cabinet 1 → 192.168.156.75
- Cabinet 2 → 192.168.156.76  
- Cabinet 3 → 192.168.156.77

## Status Messages

### Console Output Examples

```
📋 Testing: Production Line A (Group: Production)
    ⚡ Attempting real connection to 192.168.156.75:502
    ❌ CONNECTION_FAILED: Device not responding

🎲 Dummy Group machine: Test Machine B - generating random data
    ✅ Generated random data: 401.2V, 198.5A, 0.91 PF

✅ Mixed success: 2 real devices, 1 dummy group machines
```

### Web Interface Status

- **"Connected (2 real, 1 dummy)"** - Mixed real and test data
- **"Only dummy group machines responding (1 dummy)"** - No real devices
- **"No devices responding"** - Complete failure
- **"🧪 GLOBAL TEST MODE"** - All data is simulated

## API Response Changes

The `/api/readings` endpoint now includes:

```json
{
  "has_real_data": true,
  "has_dummy_group_data": true,
  "guidance": {
    "message": "Only dummy group machines are providing data",
    "suggestions": [
      "Real field devices are not responding",
      "Check network connectivity to real Modbus devices",
      "Dummy group machines are working as expected (random data)"
    ]
  }
}
```

## Troubleshooting

### No Real Devices Responding

When only dummy group machines work:
1. ✅ Dummy machines show random data (this is expected)
2. ❌ Real machines show connection failures
3. 📋 Check network connectivity to real device IPs
4. 🔧 Verify devices are powered and Modbus TCP is enabled

### Adding Test Machines

To add a test machine that generates random data:
1. Open Utenze.xlsx
2. Add new row with desired Cabinet/Node
3. Set `Gruppo = "Dummy"`
4. Use 'Refresh Machines' in web interface
5. Machine will now generate random test data

### Converting Real to Test Machine

1. Change `Gruppo` from "Production" to "Dummy" in Excel
2. Click 'Refresh Machines' in web interface  
3. Machine immediately switches to random data generation
4. No real device connection attempted

## Benefits

- 🎯 **Precise Control**: Only designated machines generate test data
- 🔍 **Clear Identification**: Dummy data clearly labeled in interface
- 📊 **Mixed Environments**: Real and test machines can coexist
- 🚫 **No False Data**: Failed real devices don't create misleading dummy data
- 🔧 **Easy Configuration**: Simple Excel column controls behavior

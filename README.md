# Energy Meter Web Server

A Flask-based web application for monitoring energy meters via Modbus TCP protocol. The application reads configuration from Excel files and provides a responsive web dashboard.

## Features

- **Excel-based Configuration**: Configure utilities and registers via Excel files
- **Real-time Monitoring**: Individual refresh buttons and live monitoring with charts
- **Robust Error Handling**: Graceful handling of connection failures and data errors
- **Grouped Machine Selection**: Machines grouped by "Gruppo" field from configuration
- **Responsive Web Interface**: Works on desktop and mobile devices
- **Fallback Mode**: Dummy data generation when real devices are unavailable

## Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure the following Excel files are present:
   - `Utenze.xlsx`: Machine/utility configuration
   - `registri.xlsx`: Register configuration

## Configuration Files

### Utenze.xlsx
Required columns:
- `Cabinet`: Cabinet number (1-3, or 0 for dummy)
- `Nodo`: Node/device ID
- `Utenza`: Machine/utility name
- `Gruppo`: (Optional) Group name for organizing machines

### registri.xlsx
Required columns:
- `Registro`: Register end address
- `Lettura`: Register description
- `Lenght`: Data type (float, long long, etc.)
- `Report`: Include in reports (yes/no)
- `Readings`: Source unit
- `Convert to`: Target unit
- `Type`: (Optional) Category for grouping (voltage, current, power, etc.)

## Usage

### Start the Server
```bash
python energy_meter_webserver_excel.py
```

Or use the launcher:
```bash
python start_server.py
```

### Access the Dashboard
Open your web browser and navigate to:
```
http://localhost:5050
```

### Operating Modes
- **PRODUCTION**: Connects to real Modbus devices
- **DUMMY**: Uses simulated data for testing

Set mode by creating an `env` file:
```
MODE=DUMMY
```

## Network Configuration

The application uses the following IP mapping:
- Cabinet 1: `192.168.156.75`
- Cabinet 2: `192.168.156.76`
- Cabinet 3: `192.168.156.77`

## File Structure

```
EnergyMeters/
├── energy_meter_webserver_excel.py  # Main application
├── Utenze.xlsx                      # Machine configuration
├── registri.xlsx                    # Register configuration
├── requirements.txt                 # Python dependencies
├── start_server.py                  # Optional launcher
├── templates/
│   └── energy_dashboard.html        # Web interface
└── README.md                        # This file
```

## Features Overview

### Web Dashboard
- Real-time energy meter readings
- Individual machine refresh buttons  
- Live monitoring with real-time charts
- Grouped machine selector
- Responsive design for mobile/desktop

### Data Processing
- Automatic unit conversion
- Calculated power values
- Error detection and reporting
- Connection status monitoring

### Robustness
- Excel file validation
- Network timeout handling
- Graceful error recovery
- Detailed logging

## Troubleshooting

### Common Issues
1. **Missing Excel files**: Ensure `Utenze.xlsx` and `registri.xlsx` are present
2. **Connection failures**: Check network connectivity and device IP addresses
3. **Import errors**: Install all dependencies with `pip install -r requirements.txt`

### Logs
Check console output for detailed error messages and connection status.

## License
This project is for internal use only.

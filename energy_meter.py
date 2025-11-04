#!/usr/bin/env python3
"""
Energy Meter Web Server - Enhanced with Excel Configuration
Displays energy meter readings in a web interface using configuration from Excel files:
- Utenze.xlsx: Contains the specific utilities to monitor (Cabinet, Node, Utility name)
- registri.xlsx: Contains the registers to read with Report column filtering
Features individual machine refresh buttons and real-time updates
"""

from flask import Flask, render_template, jsonify, request
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException
import struct
import time
from datetime import datetime
import threading
import json
import pandas as pd
import os

app = Flask(__name__)

# Global variables to store the latest readings
latest_readings = {}
last_update_time = None
connection_status = "Disconnected"
utilities_config = []
registers_config = {}

class ExcelBasedEnergyMeterReader:
    def __init__(self):
        self.load_configuration()
        
    def load_configuration(self):
        """Load configuration from Excel files"""
        global utilities_config, registers_config
        
        # Load utilities from Excel
        utilities_config = self.load_utilities_from_excel()
        
        # Load registers from Excel (only those marked for reporting)
        registers_config = self.load_registers_from_excel()
        
        print(f"Loaded {len(utilities_config)} utilities and {len(registers_config)} registers")
        
    def load_utilities_from_excel(self):
        """Load utilities configuration from Utenze.xlsx"""
        try:
            df_utenze = pd.read_excel('Utenze.xlsx')
            utilities = []
            
            # Cabinet IP mapping
            cabinet_ips = {
                1: '192.168.156.75',
                2: '192.168.156.76', 
                3: '192.168.156.77'
            }
            
            for _, row in df_utenze.iterrows():
                cabinet = int(row['Cabinet'])
                node = int(row['Nodo'])
                utility_name = str(row['Utenza'])
                ip_address = cabinet_ips.get(cabinet, None)
                
                if ip_address:
                    utilities.append({
                        'id': f"cabinet{cabinet}_node{node}",
                        'cabinet': cabinet,
                        'node': node,
                        'utility_name': utility_name,
                        'ip_address': ip_address,
                        'port': 502
                    })
                else:
                    print(f"WARNING: Unknown cabinet {cabinet} for utility {utility_name}")
            
            print(f"Loaded {len(utilities)} utilities from Utenze.xlsx")
            return utilities
            
        except FileNotFoundError:
            print("ERROR: Utenze.xlsx file not found!")
            return []
        except Exception as e:
            print(f"ERROR loading utilities from Utenze.xlsx: {e}")
            return []

    def load_registers_from_excel(self):
        """Load register configuration from registri.xlsx (only Report=Yes registers), and group by 'Type' column for badge grouping"""
        try:
            df_registri = pd.read_excel('registri.xlsx')
            registers = {}
            print("Loading registers from registri.xlsx (Report=Yes only):")
            for _, row in df_registri.iterrows():
                # Check if this register should be reported
                report_status = str(row['Report']).strip().lower() if 'Report' in row else 'yes'
                if report_status not in ['yes', 'y', '1', 'true']:
                    print(f"  Skipping register (Report={row['Report']}): {row['Lettura']}")
                    continue
                end_address = int(row['Registro'])
                description = str(row['Lettura'])
                data_type = str(row['Lenght'])
                source_unit = str(row['Readings']) if 'Readings' in row else ''
                target_unit = str(row['Convert to']) if 'Convert to' in row else source_unit
                # Use 'Type' column for grouping, fallback to Lettura if missing
                if 'Type' in df_registri.columns and pd.notna(row['Type']):
                    category = str(row['Type']).strip().replace(' ', '_').replace('/', '_').lower()
                else:
                    category = description.strip().replace(' ', '_').replace('/', '_').lower()
                # Calculate register count and start address based on data type
                if data_type.lower() == 'float':
                    register_count = 2
                    start_address = end_address - 1
                elif 'long long' in data_type.lower():
                    register_count = 4
                    start_address = end_address - 3
                else:
                    register_count = 2
                    start_address = end_address - 1
                # Store register info
                registers[start_address] = {
                    'description': description,
                    'data_type': data_type,
                    'register_count': register_count,
                    'start_address': start_address,
                    'end_address': end_address,
                    'source_unit': source_unit,
                    'target_unit': target_unit,
                    'category': category
                }
                print(f"  ✅ Register: {description} (Type: {category}) (Address: {start_address}-{end_address})")
            print(f"Loaded {len(registers)} registers for reporting")
            return registers
        except FileNotFoundError:
            print("ERROR: registri.xlsx file not found!")
            return {}
        except Exception as e:
            print(f"ERROR loading registers from registri.xlsx: {e}")
            return {}

    def convert_units(self, value, source_unit, target_unit):
        """Convert value from source unit to target unit"""
        if value is None:
            return None
        
        # Normalize unit names
        source = source_unit.lower().replace(' ', '').replace('_', '')
        target = target_unit.lower().replace(' ', '').replace('_', '')
        
        # If source and target are the same, no conversion needed
        if source == target:
            return value
        
        # Define conversion rules
        conversions = {
            ('tenthofwatts', 'kwh'): lambda x: x / 10000.0,
            ('w/10', 'kwh'): lambda x: x / 10000.0,
            ('watts', 'kwh'): lambda x: x / 3600000.0,
            ('wh', 'kwh'): lambda x: x / 1000.0,
            ('tenthofwatts', 'w'): lambda x: x / 10.0,
            ('w/10', 'w'): lambda x: x / 10.0,
            ('a', 'a'): lambda x: x,
            ('v', 'v'): lambda x: x,
        }
        
        # Try to find a conversion
        conversion_key = (source, target)
        if conversion_key in conversions:
            converted_value = conversions[conversion_key](value)
            return round(converted_value, 3)
        
        # If no conversion found, return original value
        return value

    def read_register_value(self, client, register_info, node_id):
        """Read a register value based on its data type and length, then apply unit conversion"""
        start_address = register_info['start_address']
        register_count = register_info['register_count']
        data_type = register_info['data_type']
        source_unit = register_info.get('source_unit', '')
        target_unit = register_info.get('target_unit', source_unit)
        
        try:
            # Read the required number of registers
            request = client.read_holding_registers(address=start_address, count=register_count, device_id=node_id)
            
            if request.isError():
                return None
            
            # Process based on data type to get raw value
            raw_value = None
            
            if data_type.lower() == 'float':
                # 32-bit float: 2 registers
                if len(request.registers) < 2:
                    return None
                high_word = request.registers[0]
                low_word = request.registers[1]
                
                # Convert to 32-bit float: word order is little endian
                packed_data = struct.pack('>HH', low_word, high_word)
                raw_value = struct.unpack('>f', packed_data)[0]
                
            elif 'long long' in data_type.lower():
                # 64-bit signed long long: 4 registers
                if len(request.registers) < 4:
                    return None
                
                word1 = request.registers[0]
                word2 = request.registers[1] 
                word3 = request.registers[2]
                word4 = request.registers[3]
                
                packed_data = struct.pack('>HHHH', word4, word3, word2, word1)
                raw_value = struct.unpack('>q', packed_data)[0]
                
            else:
                # Unknown type, try as float
                if len(request.registers) >= 2:
                    high_word = request.registers[0]
                    low_word = request.registers[1]
                    packed_data = struct.pack('>HH', low_word, high_word)
                    raw_value = struct.unpack('>f', packed_data)[0]
                else:
                    return None
            
            # Apply unit conversion
            if raw_value is not None:
                converted_value = self.convert_units(raw_value, source_unit, target_unit)
                return converted_value
            else:
                return None
                    
        except Exception as e:
            print(f"    ERROR reading register {start_address}: {e}")
            return None

    def read_single_utility(self, utility):
        """Read all registers for a single utility"""
        utility_id = utility['id']
        utility_name = utility['utility_name']
        ip_address = utility['ip_address']
        port = utility['port']
        node_id = utility['node']
        
        print(f"Reading utility: {utility_name} (IP: {ip_address}, Node: {node_id})")
        
        # Create Modbus TCP client
        client = ModbusTcpClient(ip_address, port=port, timeout=3)
        
        utility_data = {
            'id': utility_id,
            'name': utility_name,
            'cabinet': utility['cabinet'],
            'node': node_id,
            'ip_address': ip_address,
            'status': 'OK',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'registers': {}
        }
        
        try:
            # Connect to the device
            connection_result = client.connect()
            if not connection_result:
                utility_data['status'] = 'CONNECTION_FAILED'
                return utility_data
            
            # Read all registers
            for start_address, register_info in registers_config.items():
                try:
                    value = self.read_register_value(client, register_info, node_id)
                    register_key = f"reg_{start_address}"
                    
                    if value is not None:
                        utility_data['registers'][register_key] = {
                            'description': register_info['description'],
                            'value': round(value, 2) if isinstance(value, float) else value,
                            'unit': register_info.get('target_unit', ''),
                            'status': 'OK',
                            'category': register_info.get('category', 'other')
                        }
                    else:
                        utility_data['registers'][register_key] = {
                            'description': register_info['description'],
                            'value': 'N/A',
                            'unit': register_info.get('target_unit', ''),
                            'status': 'ERROR',
                            'category': register_info.get('category', 'other')
                        }
                        utility_data['status'] = 'PARTIAL'
                        
                except Exception as e:
                    register_key = f"reg_{start_address}"
                    utility_data['registers'][register_key] = {
                        'description': register_info['description'],
                        'value': 'ERROR',
                        'unit': register_info.get('target_unit', ''),
                        'status': 'ERROR',
                        'category': register_info.get('category', 'other')
                    }
                    utility_data['status'] = 'PARTIAL'
                    print(f"    Exception reading register {start_address}: {e}")
            
        except Exception as e:
            utility_data['status'] = f'EXCEPTION: {str(e)[:50]}'
            print(f"Exception reading utility {utility_name}: {e}")
            
        finally:
            try:
                client.close()
            except:
                pass
        
        return utility_data

    def read_all_utilities(self):
        """Read all utilities and update global readings"""
        global latest_readings, last_update_time, connection_status
        
        print(f"Reading all {len(utilities_config)} utilities...")
        
        all_readings = {}
        successful_count = 0
        
        for utility in utilities_config:
            utility_data = self.read_single_utility(utility)
            all_readings[utility_data['id']] = utility_data
            
            if utility_data['status'] in ['OK', 'PARTIAL']:
                successful_count += 1
        
        # Update global variables
        latest_readings = all_readings
        last_update_time = datetime.now()
        
        if successful_count > 0:
            connection_status = f"Connected ({successful_count}/{len(utilities_config)} utilities)"
        else:
            connection_status = "All connections failed"
        
        print(f"Completed reading: {successful_count}/{len(utilities_config)} utilities successful")
        
        return all_readings

# Initialize the energy meter reader
energy_reader = ExcelBasedEnergyMeterReader()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('energy_dashboard.html', 
                         utilities=utilities_config,
                         registers=registers_config)

@app.route('/api/readings')
def get_readings():
    """API endpoint to get all current readings"""
    global latest_readings, last_update_time, connection_status
    
    return jsonify({
        'readings': latest_readings,
        'last_update': last_update_time.strftime('%Y-%m-%d %H:%M:%S') if last_update_time else None,
        'connection_status': connection_status,
        'utilities_count': len(utilities_config),
        'registers_count': len(registers_config)
    })

@app.route('/api/refresh_all')
def refresh_all():
    """API endpoint to refresh all utilities and reload configuration"""
    global utilities_config, registers_config
    
    print("Manual refresh of all utilities requested - reloading configuration files")
    
    try:
        # Store current configuration for comparison
        old_utilities = [u['id'] for u in utilities_config] if utilities_config else []
        old_registers = list(registers_config.keys()) if registers_config else []
        
        # Reload configuration from Excel files
        print("Reloading Utenze.xlsx and registri.xlsx...")
        energy_reader.load_configuration()
        
        # Update global variables with new configuration
        utilities_config = energy_reader.load_utilities_from_excel()
        registers_config = energy_reader.load_registers_from_excel()
        
        # Compare configurations to detect changes
        new_utilities = [u['id'] for u in utilities_config]
        new_registers = list(registers_config.keys())
        
        added_utilities = [u for u in new_utilities if u not in old_utilities]
        removed_utilities = [u for u in old_utilities if u not in new_utilities]
        added_registers = [r for r in new_registers if r not in old_registers]
        removed_registers = [r for r in old_registers if r not in new_registers]
        
        # Create detailed change message
        changes = []
        if added_utilities:
            changes.append(f"Added {len(added_utilities)} utilities: {', '.join(added_utilities)}")
        if removed_utilities:
            changes.append(f"Removed {len(removed_utilities)} utilities: {', '.join(removed_utilities)}")
        if added_registers:
            changes.append(f"Added {len(added_registers)} registers")
        if removed_registers:
            changes.append(f"Removed {len(removed_registers)} registers")
        
        change_message = "; ".join(changes) if changes else "No changes detected"
        
        print(f"Configuration reloaded: {len(utilities_config)} utilities, {len(registers_config)} registers")
        print(f"Changes: {change_message}")
        
        # Read all utilities with new configuration
        readings = energy_reader.read_all_utilities()
        
        return jsonify({
            'success': True,
            'readings': readings,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': f'Configuration reloaded: {len(utilities_config)} utilities, {len(registers_config)} registers',
            'changes': change_message,
            'utilities_count': len(utilities_config),
            'registers_count': len(registers_config),
            'added_utilities': added_utilities,
            'removed_utilities': removed_utilities
        })
        
    except Exception as e:
        print(f"Error reloading configuration: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to reload configuration: {str(e)}',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/api/refresh_utility/<utility_id>')
def refresh_utility(utility_id):
    """API endpoint to refresh a single utility"""
    global latest_readings
    
    # Find the utility configuration
    utility = None
    for u in utilities_config:
        if u['id'] == utility_id:
            utility = u
            break
    
    if not utility:
        print(f"Utility {utility_id} not found in current configuration - may have been removed")
        return jsonify({
            'success': False, 
            'error': 'Utility not found in current configuration. Try refreshing all to reload configuration.',
            'suggestion': 'reload_config'
        }), 404
    
    print(f"Manual refresh requested for utility: {utility['utility_name']}")
    
    # Read the single utility
    utility_data = energy_reader.read_single_utility(utility)
    
    # Update the global readings for this utility
    if latest_readings is None:
        latest_readings = {}
    latest_readings[utility_id] = utility_data
    
    return jsonify({
        'success': True,
        'utility_data': utility_data,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/configuration')
def get_configuration():
    """API endpoint to get current configuration"""
    return jsonify({
        'utilities': utilities_config,
        'registers': {str(k): v for k, v in registers_config.items()},
        'utilities_count': len(utilities_config),
        'registers_count': len(registers_config)
    })

def background_reading_thread():
    """Background thread to perform initial reading only at startup"""
    global energy_reader
    
    print("Starting initial background reading...")
    
    try:
        print("Background reading cycle starting...")
        energy_reader.read_all_utilities()
        print("Background reading cycle completed")
        print("Initial reading finished. Further readings will be user-controlled only.")
        
    except Exception as e:
        print(f"Error in initial background reading: {e}")
        print("Initial reading failed, but server will continue. Use manual refresh buttons.")

# Create the HTML template directory and file
def create_html_template():
    """Create the HTML template for the dashboard"""
    
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Energy Meter Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0f172a;
            color: #e5e7eb;
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: #0f172a;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.4);
            overflow: hidden;
            border: 2px solid #1f2937;
        }

        .header {
            background: #0f172a;
            color: #f3f4f6;
            padding: 20px 30px;
            text-align: center;
            border-bottom: 2px solid #1f2937;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .status-bar {
            background: #0f172a;
            padding: 15px 30px;
            border-bottom: 2px solid #1f2937;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }

        .status-item {
            display: flex;
            align-items: center;
            color: #d1d5db;
            gap: 10px;
        }

        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #e74c3c;
        }

        .status-indicator.connected {
            background: #27ae60;
        }

        .refresh-all-btn {
            background: #3498db;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            transition: background 0.3s;
        }

        .refresh-all-btn:hover {
            background: #2980b9;
        }

        .refresh-all-btn:disabled {
            background: #95a5a6;
            cursor: not-allowed;
        }

        .utilities-grid {
            padding: 30px;
            background: #0f172a;
        }

        .utility-card {
            background: #0f172a;
            border: 2px solid #374151;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            transition: transform 0.3s, box-shadow 0.3s, border-color 0.3s;
        }

        .utility-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.5);
            border-color: #4b5563;
        }

        .utility-header {
            background: #0f172a;
            padding: 20px;
            border-bottom: 2px solid #374151;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
        }

        .utility-info {
            flex: 1 1 280px;
            min-width: 0;
        }

        .utility-info h3 {
            color: #f3f4f6;
            font-size: 1.3em;
            margin-bottom: 5px;
        }

        .utility-details {
            color: #9ca3af;
            font-size: 0.9em;
        }

        .timestamp {
            color: #6b7280;
            font-size: 0.8em;
            margin-top: 5px;
        }

        .refresh-btn {
            background: #27ae60;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
        }

        .refresh-btn:hover {
            background: #229954;
            transform: scale(1.05);
        }

        .refresh-btn:disabled {
            background: #95a5a6;
            cursor: not-allowed;
            transform: none;
        }

        .refresh-btn.loading {
            background: #f39c12;
        }

        .monitor-toggle {
            background: #95a5a6;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
            margin-left: 10px;
            font-size: 0.9em;
        }

        .monitor-toggle:hover {
            transform: scale(1.05);
        }

        .monitor-toggle.active {
            background: #e74c3c;
            animation: pulse 2s infinite;
        }

        .monitor-toggle.disabled {
            background: #bdc3c7;
            cursor: not-allowed;
            transform: none;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }

        .utility-header-actions {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }

        .monitor-status {
            font-size: 0.8em;
            color: #e74c3c;
            font-weight: bold;
            margin-top: 5px;
        }

        .power-badge {
            display: inline-flex;
            flex-direction: column;
            align-items: flex-start;
            gap: 4px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 16px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 1.1em;
            margin-top: 10px;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
            transition: all 0.3s;
            max-width: 100%;
            flex-wrap: wrap;
        }

        .power-badge:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.5);
        }

        .power-badge.high-power {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }

        .power-badge.low-power {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }

        .power-badge.no-data {
            background: #95a5a6;
        }

        .power-badge .power-label {
            font-size: 0.7em;
            opacity: 0.9;
            display: block;
        }

        .power-badge .power-value {
            font-size: 1.3em;
            display: block;
            margin-top: 2px;
        }

        .charts-container {
            margin-top: 20px;
            padding: 15px;
            background: #0f172a;
            border-radius: 8px;
            border: 2px solid #374151;
        }

        .charts-header {
            text-align: center;
            font-weight: 600;
            margin-bottom: 12px;
            color: #cbd5f5;
            font-size: 0.95em;
            letter-spacing: 0.5px;
        }

        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 18px;
            margin-top: 15px;
            transition: grid-template-columns 0.3s ease;
        }

        .chart-section {
            background: #0f172a;
            padding: 15px;
            border-radius: 8px;
            border: 2px solid #374151;
            display: flex;
            flex-direction: column;
            gap: 12px;
            cursor: zoom-in;
            transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease, opacity 0.25s ease;
            min-height: 240px;
        }

        .chart-section:hover {
            transform: translateY(-4px);
            border-color: #4b5563;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.45);
        }

        .chart-section.expanded {
            grid-column: 1 / -1;
            cursor: zoom-out;
            min-height: 360px;
            box-shadow: 0 20px 40px rgba(15, 23, 42, 0.6);
            border-color: #6366f1;
        }

        .chart-section.collapsed {
            opacity: 0;
            pointer-events: none;
            transform: scale(0.97);
            display: none;
        }

        .charts-grid.expanded {
            grid-template-columns: 1fr;
        }

        .chart-title {
            font-weight: bold;
            margin-bottom: 10px;
            padding: 8px 12px;
            border-radius: 5px;
            text-align: center;
            color: #9ca3af;
            border-left: 4px solid;
            background: transparent;
            transition: color 0.3s ease;
        }

        .chart-title.voltage {
            border-left-color: #ef4444;
        }

        .chart-title.current {
            border-left-color: #3b82f6;
        }

        .chart-title.power {
            border-left-color: #f97316;
        }

        .chart-title.powerfactor {
            border-left-color: #a855f7;
        }

        .chart-canvas {
            height: 220px;
            transition: height 0.3s ease;
        }

        .chart-section.expanded .chart-canvas {
            height: 360px;
        }

        @media (max-width: 768px) {
            .charts-grid {
                grid-template-columns: 1fr;
            }
        }

        .registers-container {
            padding: 20px;
            background: #0f172a;
        }

        .readings-section {
            margin-bottom: 25px;
        }

        .section-title {
            font-size: 1.1em;
            font-weight: bold;
            color: #9ca3af;
            margin-bottom: 15px;
            padding: 8px 12px;
            border-radius: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-left: 4px solid;
            background: transparent;
        }

        .voltage-section .section-title {
            border-left-color: #ef4444;
        }

        .current-section .section-title {
            border-left-color: #3b82f6;
        }

        .energy-section .section-title {
            border-left-color: #10b981;
        }

        .other-section .section-title {
            border-left-color: #a855f7;
        }

        .power_factors-section .section-title {
            border-left-color: #a855f7;
        }

        .voltages-section .section-title {
            border-left-color: #ef4444;
        }

        .currents-section .section-title {
            border-left-color: #3b82f6;
        }

        .registers-grid {
            display: flex;
            flex-direction: column;
            gap: 12px;
            overflow-x: auto;
            overflow-y: visible;
            padding-bottom: 4px;
            width: 100%;
        }

        .registers-row {
            display: grid;
            grid-template-columns: repeat(3, minmax(140px, 1fr));
            gap: 12px;
            width: 100%;
        }

        .registers-grid.voltage-grid .registers-row,
        .registers-grid.current-grid .registers-row,
        .registers-grid.power_factor-grid .registers-row,
        .registers-grid.power-grid .registers-row {
            grid-template-columns: repeat(3, minmax(120px, 1fr));
            gap: 10px;
        }

        .registers-row .register-badge {
            width: 100%;
        }

        @media (max-width: 768px) {
            .registers-row {
                grid-template-columns: repeat(3, minmax(120px, 1fr));
            }
        }

        @media (max-width: 520px) {
            .registers-row {
                grid-template-columns: repeat(3, minmax(100px, 1fr));
            }
        }

        .register-badge {
            background: #1f2937;
            border: 2px solid #4b5563;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
            transition: all 0.3s ease;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            width: 100%;
            min-height: 120px;
            position: relative;
        }

        .register-badge.voltage,
        .register-badge.current,
        .register-badge.power_factor {
            padding: 10px;
        }

        .register-name {
            font-weight: 600;
            color: #9ca3af;
            margin-bottom: 8px;
            font-size: 0.75em;
            line-height: 1.2;
            min-height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            word-break: break-word;
            width: 100%;
        }

        .register-badge.voltage .register-name,
        .register-badge.current .register-name,
        .register-badge.power_factor .register-name {
            font-size: 0.7em;
            min-height: 28px;
            margin-bottom: 6px;
        }

        .register-measure {
            display: flex;
            align-items: baseline;
            justify-content: center;
            gap: 4px;
            margin-bottom: 3px;
        }

        .register-value {
            font-size: 1.4em;
            font-weight: bold;
            color: #e5e7eb;
        }

        .register-unit {
            font-size: 0.8em;
            color: #9ca3af;
        }

        .register-badge.voltage .register-value, 
        .register-badge.current .register-value,
        .register-badge.power_factor .register-value {
            font-size: 1.1em;
        }


        .register-badge.voltage {
            border-color: #ef4444;
            background: #1f2937;
            box-shadow: inset 0 0 0 1px rgba(239, 68, 68, 0.2);
        }

        .register-badge.current {
            border-color: #3b82f6;
            background: #1f2937;
            box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.2);
        }

        .register-badge.energy {
            border-color: #10b981;
            background: #1f2937;
            box-shadow: inset 0 0 0 1px rgba(16, 185, 129, 0.2);
        }

        .register-badge.other {
            border-color: #a855f7;
            background: #1f2937;
            box-shadow: inset 0 0 0 1px rgba(168, 85, 247, 0.2);
        }

        /* Dynamic badge color for new categories (fallback: HSL by category name hash) */
        [class*="register-badge."], .register-badge {
            /* fallback, will be overridden below */
        }
        /* Example for a few possible new categories */
        .register-badge.frequency {
            border-color: #f59e0b;
            background: #1f2937;
        }
        .register-badge.temperature {
            border-color: #14b8a6;
            background: #1f2937;
        }
        .register-badge.power_factor {
            border-color: #a855f7;
            background: #1f2937;
        }
        /* Generic fallback for any unknown category: use HSL based on category name hash */
        .register-badge[data-category] {
            /* JS will set style if not matched above */
        }

        .register-badge.error {
            border-color: #ef4444;
            background: #1f2937;
            color: #ef4444;
        }

        .register-badge.error .register-name,
        .register-badge.error .register-value,
        .register-badge.error .register-unit {
            color: #ef4444;
        }

        .voltage-current-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 25px;
        }

        .readings-section.voltages-section,
        .readings-section.currents-section,
        .readings-section.power_factors-section {
            flex: 1 1 0;
            min-width: 0;
            margin-bottom: 0;
        }

        /* Legacy support for old category names */
        .readings-section.voltage-section,
        .readings-section.current-section {
            flex: 1 1 0;
            min-width: 0;
            margin-bottom: 0;
        }

        @media (max-width: 768px) {
            .status-bar {
                flex-direction: column;
                align-items: stretch;
                gap: 15px;
            }

            .utility-header {
                flex-direction: column;
                align-items: stretch;
                gap: 15px;
            }

            .utility-header-actions {
                justify-content: center;
                flex-wrap: wrap;
            }

            .registers-row {
                gap: 10px;
            }

            .register-badge {
                padding: 10px;
            }

            .register-name {
                font-size: 0.75em;
                min-height: 28px;
            }

            .register-value {
                font-size: 1.4em;
            }

            .section-title {
                font-size: 1em;
                padding: 6px 10px;
            }

            .header h1 {
                font-size: 2em;
            }
        }

        @media (max-width: 480px) {
            .registers-row {
                grid-template-columns: repeat(3, minmax(100px, 1fr));
            }

            .register-badge {
                padding: 8px;
            }

            .register-name {
                font-size: 0.7em;
                min-height: 24px;
            }

            .register-value {
                font-size: 1.2em;
            }
        }

        .no-data {
            text-align: center;
            padding: 50px;
            color: #9ca3af;
        }

        .error-message {
            background: #0f172a;
            color: #ef4444;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            border: 2px solid #ef4444;
        }

        .success-message {
            background: #0f172a;
            color: #10b981;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            border: 2px solid #10b981;
        }

        .utility-status {
            font-size: 0.85em;
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 4px;
            margin-top: 5px;
            display: inline-block;
            border: 2px solid;
            background: #0f172a;
        }

        .utility-status.status-ok {
            border-color: #10b981;
            color: #10b981;
        }

        .utility-status.status-partial {
            border-color: #f59e0b;
            color: #f59e0b;
        }

        .utility-status.status-error {
            border-color: #ef4444;
            color: #ef4444;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏭 Energy Meter Dashboard</h1>
            <p>Real-time monitoring of energy meters from Excel configuration</p>
        </div>

        <div class="status-bar">
            <div class="status-item">
                <div class="status-indicator" id="connectionIndicator"></div>
                <span id="connectionStatus">Connecting...</span>
            </div>
            <div class="status-item">
                <span id="lastUpdate">Last Update: Loading...</span>
            </div>
            <div class="status-item">
                <span id="utilitiesCount">Utilities: 0</span>
            </div>
            <div class="status-item">
                <span id="monitoringCount">Live Monitoring: 0</span>
            </div>
            <button class="refresh-all-btn" id="refreshAllBtn" onclick="refreshAll()">
                🔄 Refresh All
            </button>
        </div>

        <div class="utilities-grid" id="utilitiesGrid">
            <div class="no-data">
                <h3>Loading utilities...</h3>
                <p>Please wait while we load the configuration from Excel files.</p>
            </div>
        </div>
    </div>

    <script>
        let isRefreshing = false;
        let monitoringIntervals = {}; // Store active monitoring intervals
        let chartInstances = {}; // Store chart instances for each utility
        let chartData = {}; // Store chart data history for each utility

        const domRefs = {
            connectionIndicator: document.getElementById('connectionIndicator'),
            connectionStatus: document.getElementById('connectionStatus'),
            lastUpdate: document.getElementById('lastUpdate'),
            utilitiesGrid: document.getElementById('utilitiesGrid'),
            utilitiesCount: document.getElementById('utilitiesCount'),
            monitoringCount: document.getElementById('monitoringCount')
        };

        const chartSections = [
            { key: 'voltage', title: '⚡ Voltage', className: 'voltage', canvasId: 'voltage' },
            { key: 'current', title: '🔌 Current', className: 'current', canvasId: 'current' },
            { key: 'power', title: '⚡ Power', className: 'power', canvasId: 'power' },
            { key: 'powerFactor', title: '📊 Power Factor', className: 'powerfactor', canvasId: 'powerfactor' }
        ];

        function getChartsHtml(utilityId) {
            const sectionsHtml = chartSections.map(section => `
                                <div class="chart-section" data-chart-type="${section.key}">
                                    <div class="chart-title ${section.className}">${section.title}</div>
                                    <div class="chart-canvas">
                                        <canvas id="${section.canvasId}-chart-${utilityId}"></canvas>
                                    </div>
                                </div>
            `).join('');

            return `
                        <div class="charts-container" id="charts-${utilityId}">
                            <div class="charts-header">📈 Real-time Monitoring Charts</div>
                            <div class="charts-grid" data-utility="${utilityId}">
                ${sectionsHtml}
                            </div>
                        </div>
            `;
        }

        function initializeChartInteractions(utilityId) {
            const grid = document.querySelector(`#charts-${utilityId} .charts-grid`);
            if (!grid || grid.dataset.interactionsInitialized === 'true') {
                return;
            }

            grid.dataset.interactionsInitialized = 'true';
            grid.querySelectorAll('.chart-section').forEach(section => {
                section.addEventListener('click', () => {
                    toggleChartExpansion(utilityId, section.dataset.chartType);
                });
            });
        }

        function toggleChartExpansion(utilityId, chartKey) {
            const grid = document.querySelector(`#charts-${utilityId} .charts-grid`);
            if (!grid || !chartKey) {
                return;
            }

            const targetSection = grid.querySelector(`.chart-section[data-chart-type="${chartKey}"]`);
            if (!targetSection) {
                return;
            }

            const isExpanded = targetSection.classList.contains('expanded');
            const sections = Array.from(grid.querySelectorAll('.chart-section'));

            if (isExpanded) {
                grid.classList.remove('expanded');
                sections.forEach(section => {
                    section.classList.remove('expanded');
                    section.classList.remove('collapsed');
                });
            } else {
                grid.classList.add('expanded');
                sections.forEach(section => {
                    if (section === targetSection) {
                        section.classList.add('expanded');
                        section.classList.remove('collapsed');
                    } else {
                        section.classList.remove('expanded');
                        section.classList.add('collapsed');
                    }
                });
            }

            requestAnimationFrame(() => {
                const instances = chartInstances[utilityId];
                if (!instances) return;

                const keysToResize = isExpanded ? chartSections.map(section => section.key) : [chartKey];
                keysToResize.forEach(key => {
                    const chart = instances[key];
                    if (chart && typeof chart.resize === 'function') {
                        chart.resize();
                    }
                });
            });
        }

        function applyDynamicBadgeColors(context = document) {
            const badges = context.querySelectorAll('.register-badge[data-category]');
            badges.forEach(badge => {
                const cat = badge.getAttribute('data-category');
                if (!cat) return;

                if (badge.classList.contains('frequency') ||
                    badge.classList.contains('temperature') ||
                    badge.classList.contains('power_factor')) {
                    return;
                }

                let hash = 0;
                for (let i = 0; i < cat.length; i++) {
                    hash = cat.charCodeAt(i) + ((hash << 5) - hash);
                }
                const hue = Math.abs(hash) % 360;
                badge.style.borderColor = `hsl(${hue},70%,50%)`;
                badge.style.background = `linear-gradient(135deg, hsl(${hue},100%,98%), hsl(${hue},100%,92%))`;
            });
        }

        // Chart configuration
        const chartConfig = {
            voltage: {
                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                borderColor: 'rgba(231, 76, 60, 1)',
                pointBackgroundColor: 'rgba(231, 76, 60, 1)',
                tension: 0.45,
                cubicInterpolationMode: 'monotone',
                fill: false
            },
            current: {
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                borderColor: 'rgba(52, 152, 219, 1)',
                pointBackgroundColor: 'rgba(52, 152, 219, 1)',
                tension: 0.45,
                cubicInterpolationMode: 'monotone',
                fill: false
            },
            power: {
                backgroundColor: 'rgba(249, 115, 22, 0.1)',
                borderColor: 'rgba(249, 115, 22, 1)',
                pointBackgroundColor: 'rgba(249, 115, 22, 1)',
                tension: 0.45,
                cubicInterpolationMode: 'monotone',
                fill: false
            },
            powerFactor: {
                backgroundColor: 'rgba(168, 85, 247, 0.1)',
                borderColor: 'rgba(168, 85, 247, 1)',
                pointBackgroundColor: 'rgba(168, 85, 247, 1)',
                tension: 0.45,
                cubicInterpolationMode: 'monotone',
                fill: false
            }
        };

        function escapeAttribute(value) {
            if (value === null || value === undefined) return '';
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }

        function cleanLabel(label, category) {
            if (!label) return label;
            let cleaned = label.trim();
            const cat = (category || '').toLowerCase();
            const removalPatterns = {
                voltages: [/voltages?/gi],
                voltage: [/voltages?/gi],
                currents: [/currents?/gi],
                current: [/currents?/gi],
                power: [/power/gi],
                power_factors: [/power\s*factors?/gi],
                power_factor: [/power\s*factors?/gi]
            };

            const patterns = removalPatterns[cat];
            if (patterns) {
                patterns.forEach(pattern => {
                    cleaned = cleaned.replace(pattern, ' ');
                });
            }

            cleaned = cleaned.replace(/\s+/g, ' ').replace(/[-:;,]+$/g, '').trim();
            return cleaned || label.trim();
        }

        function initializeCharts(utilityId) {
            // Initialize chart data storage for this utility
            if (!chartData[utilityId]) {
                chartData[utilityId] = {
                    voltage: { labels: [], datasets: [] },
                    current: { labels: [], datasets: [] },
                    power: { labels: [], datasets: [] },
                    powerFactor: { labels: [], datasets: [] }
                };
            }

            // Initialize chart instances
            if (!chartInstances[utilityId]) {
                chartInstances[utilityId] = { voltage: null, current: null, power: null, powerFactor: null };
            }

            // Create voltage chart
            const voltageCanvas = document.getElementById(`voltage-chart-${utilityId}`);
            if (voltageCanvas) {
                // Destroy existing chart if it exists
                if (chartInstances[utilityId].voltage) {
                    try {
                        chartInstances[utilityId].voltage.destroy();
                    } catch (e) {
                        console.log(`Error destroying voltage chart for ${utilityId}:`, e);
                    }
                }
                
                try {
                    chartInstances[utilityId].voltage = new Chart(voltageCanvas, {
                        type: 'line',
                        data: chartData[utilityId].voltage,
                        options: getChartOptions('Voltage (V)')
                    });
                    console.log(`Voltage chart initialized for ${utilityId}`);
                } catch (e) {
                    console.error(`Error creating voltage chart for ${utilityId}:`, e);
                }
            }

            // Create current chart
            const currentCanvas = document.getElementById(`current-chart-${utilityId}`);
            if (currentCanvas) {
                // Destroy existing chart if it exists
                if (chartInstances[utilityId].current) {
                    try {
                        chartInstances[utilityId].current.destroy();
                    } catch (e) {
                        console.log(`Error destroying current chart for ${utilityId}:`, e);
                    }
                }
                
                try {
                    chartInstances[utilityId].current = new Chart(currentCanvas, {
                        type: 'line',
                        data: chartData[utilityId].current,
                        options: getChartOptions('Current (A)')
                    });
                    console.log(`Current chart initialized for ${utilityId}`);
                } catch (e) {
                    console.error(`Error creating current chart for ${utilityId}:`, e);
                }
            }

            // Create power chart
            const powerCanvas = document.getElementById(`power-chart-${utilityId}`);
            if (powerCanvas) {
                if (chartInstances[utilityId].power) {
                    try {
                        chartInstances[utilityId].power.destroy();
                    } catch (e) {
                        console.log(`Error destroying power chart for ${utilityId}:`, e);
                    }
                }

                try {
                    chartInstances[utilityId].power = new Chart(powerCanvas, {
                        type: 'line',
                        data: chartData[utilityId].power,
                        options: getChartOptions('Power (kW)')
                    });
                    console.log(`Power chart initialized for ${utilityId}`);
                } catch (e) {
                    console.error(`Error creating power chart for ${utilityId}:`, e);
                }
            }

            // Create power factor chart
            const powerFactorCanvas = document.getElementById(`powerfactor-chart-${utilityId}`);
            if (powerFactorCanvas) {
                // Destroy existing chart if it exists
                if (chartInstances[utilityId].powerFactor) {
                    try {
                        chartInstances[utilityId].powerFactor.destroy();
                    } catch (e) {
                        console.log(`Error destroying power factor chart for ${utilityId}:`, e);
                    }
                }

                try {
                    chartInstances[utilityId].powerFactor = new Chart(powerFactorCanvas, {
                        type: 'line',
                        data: chartData[utilityId].powerFactor,
                        options: getChartOptions('Power Factor')
                    });
                    console.log(`Power factor chart initialized for ${utilityId}`);
                } catch (e) {
                    console.error(`Error creating power factor chart for ${utilityId}:`, e);
                }
            }

            initializeChartInteractions(utilityId);
        }

        function getChartOptions(title) {
            return {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'nearest',
                    intersect: false
                },
                layout: {
                    padding: { top: 8, right: 8, bottom: 8, left: 8 }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            color: '#cbd5f5',
                            boxWidth: 10,
                            usePointStyle: true,
                            pointStyle: 'circle',
                            padding: 10,
                            font: {
                                size: 11,
                                family: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif'
                            }
                        }
                    },
                    title: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.85)',
                        titleColor: '#f8fafc',
                        bodyColor: '#e2e8f0',
                        borderColor: '#475569',
                        borderWidth: 1,
                        padding: 10
                    }
                },
                scales: {
                    x: {
                        display: true,
                        title: {
                            display: true,
                            text: 'Time',
                            color: '#94a3b8'
                        },
                        grid: {
                            color: 'rgba(148, 163, 184, 0.08)'
                        },
                        ticks: {
                            color: '#94a3b8',
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 6
                        }
                    },
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: title,
                            color: '#94a3b8'
                        },
                        grid: {
                            color: 'rgba(148, 163, 184, 0.12)'
                        },
                        ticks: {
                            color: '#cbd5f5'
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 2,
                        hoverRadius: 4
                    },
                    line: {
                        tension: 0.45,
                        borderWidth: 2
                    }
                }
            };
        }

        function clearCharts(utilityId) {
            if (chartData[utilityId]) {
                chartData[utilityId].voltage = { labels: [], datasets: [] };
                chartData[utilityId].current = { labels: [], datasets: [] };
                chartData[utilityId].power = { labels: [], datasets: [] };
                chartData[utilityId].powerFactor = { labels: [], datasets: [] };
            }

            if (chartInstances[utilityId]) {
                if (chartInstances[utilityId].voltage) {
                    chartInstances[utilityId].voltage.data = chartData[utilityId].voltage;
                    chartInstances[utilityId].voltage.update();
                }
                if (chartInstances[utilityId].current) {
                    chartInstances[utilityId].current.data = chartData[utilityId].current;
                    chartInstances[utilityId].current.update();
                }
                if (chartInstances[utilityId].power) {
                    chartInstances[utilityId].power.data = chartData[utilityId].power;
                    chartInstances[utilityId].power.update();
                }
                if (chartInstances[utilityId].powerFactor) {
                    chartInstances[utilityId].powerFactor.data = chartData[utilityId].powerFactor;
                    chartInstances[utilityId].powerFactor.update();
                }
            }
        }

        function updateCharts(utilityId, utilityData) {
            if (!chartData[utilityId] || !utilityData.registers) return;

            // Check if chart instances exist (don't require all charts to exist)
            if (!chartInstances[utilityId]) {
                console.log(`Chart instances missing for ${utilityId}, skipping update`);
                return;
            }

            const now = new Date().toLocaleTimeString();
            const maxDataPoints = 50; // Keep last 50 data points

            // Prepare voltage, current, power and power factor data
            const voltageData = {};
            const currentData = {};
            const powerData = {};
            const powerFactorData = {};

            // Extract voltage, current, power and power factor values
            for (const [regKey, regData] of Object.entries(utilityData.registers)) {
                const description = regData.description.toLowerCase();
                const unit = (regData.unit || '').toLowerCase();
                const category = (regData.category || '').toLowerCase();
                const value = parseFloat(regData.value);

                if (!isNaN(value)) {
                    if (category === 'voltages' || description.includes('voltage') || description.includes('tensione') || unit === 'v') {
                        voltageData[regData.description] = value;
                    } else if (category === 'currents' || description.includes('current') || description.includes('corrente') || unit === 'a') {
                        currentData[regData.description] = value;
                    } else if (category === 'power' || (description.includes('power') && !description.includes('factor'))) {
                        powerData[regData.description] = value;
                    } else if (category === 'power_factors' || description.includes('power factor') || description.includes('fattore di potenza') || description.includes('cos')) {
                        powerFactorData[regData.description] = value;
                    }
                }
            }

            // Update voltage chart data
            if (Object.keys(voltageData).length > 0) {
                if (chartData[utilityId].voltage.labels.length >= maxDataPoints) {
                    chartData[utilityId].voltage.labels.shift();
                    chartData[utilityId].voltage.datasets.forEach(dataset => dataset.data.shift());
                }

                chartData[utilityId].voltage.labels.push(now);

                // Update datasets
                Object.entries(voltageData).forEach(([description, value], index) => {
                    const displayLabel = cleanLabel(description, 'voltages');
                    if (!chartData[utilityId].voltage.datasets[index]) {
                        chartData[utilityId].voltage.datasets[index] = {
                            label: displayLabel,
                            data: [],
                            ...chartConfig.voltage,
                            borderColor: `hsl(${index * 30}, 70%, 50%)`,
                            backgroundColor: `hsla(${index * 30}, 70%, 50%, 0.1)`
                        };
                    }
                    chartData[utilityId].voltage.datasets[index].label = displayLabel;
                    chartData[utilityId].voltage.datasets[index].data.push(value);
                });
            }

            // Update current chart data
            if (Object.keys(currentData).length > 0) {
                if (chartData[utilityId].current.labels.length >= maxDataPoints) {
                    chartData[utilityId].current.labels.shift();
                    chartData[utilityId].current.datasets.forEach(dataset => dataset.data.shift());
                }

                chartData[utilityId].current.labels.push(now);

                // Update datasets
                Object.entries(currentData).forEach(([description, value], index) => {
                    const displayLabel = cleanLabel(description, 'currents');
                    if (!chartData[utilityId].current.datasets[index]) {
                        chartData[utilityId].current.datasets[index] = {
                            label: displayLabel,
                            data: [],
                            ...chartConfig.current,
                            borderColor: `hsl(${200 + index * 30}, 70%, 50%)`,
                            backgroundColor: `hsla(${200 + index * 30}, 70%, 50%, 0.1)`
                        };
                    }
                    chartData[utilityId].current.datasets[index].label = displayLabel;
                    chartData[utilityId].current.datasets[index].data.push(value);
                });
            }

            // Update power chart data
            if (Object.keys(powerData).length > 0) {
                if (chartData[utilityId].power.labels.length >= maxDataPoints) {
                    chartData[utilityId].power.labels.shift();
                    chartData[utilityId].power.datasets.forEach(dataset => dataset.data.shift());
                }

                chartData[utilityId].power.labels.push(now);

                Object.entries(powerData).forEach(([description, value], index) => {
                    const displayLabel = cleanLabel(description, 'power');
                    if (!chartData[utilityId].power.datasets[index]) {
                        chartData[utilityId].power.datasets[index] = {
                            label: displayLabel,
                            data: [],
                            ...chartConfig.power,
                            borderColor: `hsl(${30 + index * 30}, 70%, 50%)`,
                            backgroundColor: `hsla(${30 + index * 30}, 70%, 50%, 0.1)`
                        };
                    }
                    chartData[utilityId].power.datasets[index].label = displayLabel;
                    chartData[utilityId].power.datasets[index].data.push(value);
                });
            }

            // Update power factor chart data
            if (Object.keys(powerFactorData).length > 0) {
                if (chartData[utilityId].powerFactor.labels.length >= maxDataPoints) {
                    chartData[utilityId].powerFactor.labels.shift();
                    chartData[utilityId].powerFactor.datasets.forEach(dataset => dataset.data.shift());
                }

                chartData[utilityId].powerFactor.labels.push(now);

                // Update datasets
                Object.entries(powerFactorData).forEach(([description, value], index) => {
                    const displayLabel = cleanLabel(description, 'power_factors');
                    if (!chartData[utilityId].powerFactor.datasets[index]) {
                        chartData[utilityId].powerFactor.datasets[index] = {
                            label: displayLabel,
                            data: [],
                            ...chartConfig.powerFactor,
                            borderColor: `hsl(${270 + index * 30}, 70%, 50%)`,
                            backgroundColor: `hsla(${270 + index * 30}, 70%, 50%, 0.1)`
                        };
                    }
                    chartData[utilityId].powerFactor.datasets[index].label = displayLabel;
                    chartData[utilityId].powerFactor.datasets[index].data.push(value);
                });
            }

            // Update chart instances with error handling
            try {
                if (chartInstances[utilityId].voltage && chartInstances[utilityId].voltage.canvas) {
                    chartInstances[utilityId].voltage.update('none');
                }
            } catch (e) {
                console.error(`Error updating voltage chart for ${utilityId}:`, e);
                // Try to reinitialize the chart
                setTimeout(() => {
                    initializeCharts(utilityId);
                }, 100);
            }

            try {
                if (chartInstances[utilityId].current && chartInstances[utilityId].current.canvas) {
                    chartInstances[utilityId].current.update('none');
                }
            } catch (e) {
                console.error(`Error updating current chart for ${utilityId}:`, e);
                // Try to reinitialize the chart
                setTimeout(() => {
                    initializeCharts(utilityId);
                }, 100);
            }

            try {
                if (chartInstances[utilityId].power && chartInstances[utilityId].power.canvas) {
                    chartInstances[utilityId].power.update('none');
                }
            } catch (e) {
                console.error(`Error updating power chart for ${utilityId}:`, e);
                setTimeout(() => {
                    initializeCharts(utilityId);
                }, 100);
            }

            try {
                if (chartInstances[utilityId].powerFactor && chartInstances[utilityId].powerFactor.canvas) {
                    chartInstances[utilityId].powerFactor.update('none');
                }
            } catch (e) {
                console.error(`Error updating power factor chart for ${utilityId}:`, e);
                // Try to reinitialize the chart
                setTimeout(() => {
                    initializeCharts(utilityId);
                }, 100);
            }
        }

        // Load initial data when page loads
        document.addEventListener('DOMContentLoaded', function() {
            loadConfiguration();
            loadReadings();
            
            // No automatic refresh - user controls all updates via buttons
        });

        // Cleanup monitoring intervals when page is closed
        window.addEventListener('beforeunload', function() {
            Object.values(monitoringIntervals).forEach(interval => {
                clearInterval(interval);
            });
        });

        // Pause monitoring when page is not visible, resume when visible
        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                // Page is hidden, pause all monitoring
                Object.keys(monitoringIntervals).forEach(utilityId => {
                    clearInterval(monitoringIntervals[utilityId]);
                    // Don't delete the key, just clear the interval
                });
                console.log('Page hidden - paused all monitoring');
            } else {
                // Page is visible, resume monitoring for previously active utilities
                Object.keys(monitoringIntervals).forEach(utilityId => {
                    if (monitoringIntervals[utilityId] === null || monitoringIntervals[utilityId] === undefined) {
                        // Restart the interval
                        monitoringIntervals[utilityId] = setInterval(async () => {
                            try {
                                await refreshUtility(utilityId, null);
                            } catch (error) {
                                console.error(`Error in continuous monitoring for ${utilityId}:`, error);
                            }
                        }, 2000);
                    }
                });
                console.log('Page visible - resumed monitoring');
            }
        });

        async function loadConfiguration() {
            try {
                const response = await fetch('/api/configuration');
                const data = await response.json();
                
                console.log('Configuration loaded:', data);
                domRefs.utilitiesCount.textContent =
                    `Utilities: ${data.utilities_count} | Registers: ${data.registers_count}`;
                
            } catch (error) {
                console.error('Error loading configuration:', error);
            }
        }

        async function loadReadings() {
            if (isRefreshing) return;
            
            try {
                const response = await fetch('/api/readings');
                const data = await response.json();
                
                updateUI(data);
                
            } catch (error) {
                console.error('Error loading readings:', error);
                showError('Failed to load readings. Please check connection.');
            }
        }

        function updateUI(data) {
            if (!data) return;

            if (data.connection_status && data.connection_status.includes('Connected')) {
                domRefs.connectionIndicator.className = 'status-indicator connected';
                domRefs.connectionStatus.textContent = data.connection_status;
            } else {
                domRefs.connectionIndicator.className = 'status-indicator';
                domRefs.connectionStatus.textContent = data.connection_status || 'Disconnected';
            }

            domRefs.lastUpdate.textContent = `Last Update: ${data.last_update || 'Never'}`;

            if (!data.readings || Object.keys(data.readings).length === 0) {
                requestAnimationFrame(() => {
                    domRefs.utilitiesGrid.innerHTML = `
                        <div class="no-data">
                            <h3>No data available</h3>
                            <p>Click "Refresh All" to load readings from all utilities.</p>
                        </div>
                    `;
                });
                return;
            }

            const currentUtilityIds = Object.keys(data.readings);
            const monitoredUtilityIds = Object.keys(monitoringIntervals);

            monitoredUtilityIds.forEach(utilityId => {
                if (!currentUtilityIds.includes(utilityId)) {
                    console.log(`Stopping monitoring for removed utility: ${utilityId}`);
                    clearInterval(monitoringIntervals[utilityId]);
                    delete monitoringIntervals[utilityId];
                }
            });

            let html = '';
            currentUtilityIds.forEach(utilityId => {
                html += createUtilityCard(utilityId, data.readings[utilityId]);
            });

            const monitoredActiveIds = currentUtilityIds.filter(utilityId => monitoringIntervals.hasOwnProperty(utilityId));

            requestAnimationFrame(() => {
                domRefs.utilitiesGrid.innerHTML = html;
                applyDynamicBadgeColors(domRefs.utilitiesGrid);

                monitoredActiveIds.forEach(utilityId => {
                    setTimeout(() => {
                        initializeCharts(utilityId);
                    }, 0);
                });
            });

            updateMonitoringCount();
        }

        function calculatePowerBadge(utilityData) {
            // Calculate instantaneous 3-phase power: P = √3 × V × I × PF
            // P (kW) = √3 × V_avg × I_avg × PF_avg / 1000
            
            if (!utilityData.registers || Object.keys(utilityData.registers).length === 0) {
                return `
                    <div class="power-badge no-data">
                        <span class="power-label">⚡ Power</span>
                        <span class="power-value">N/A</span>
                    </div>
                `;
            }
            
            // Extract voltage, current, and power factor values
            let voltages = [];
            let currents = [];
            let powerFactors = [];
            
            for (const [regKey, regData] of Object.entries(utilityData.registers)) {
                if (regData.status === 'OK' && typeof regData.value === 'number') {
                    if (regData.category === 'voltages') {
                        voltages.push(regData.value);
                    } else if (regData.category === 'currents') {
                        currents.push(regData.value);
                    } else if (regData.category === 'power_factors') {
                        powerFactors.push(regData.value);
                    }
                }
            }
            
            // Need at least one voltage and one current to calculate power
            if (voltages.length === 0 || currents.length === 0) {
                return `
                    <div class="power-badge no-data">
                        <span class="power-label">⚡ Power</span>
                        <span class="power-value">N/A</span>
                    </div>
                `;
            }
            
            // Calculate averages
            const avgVoltage = voltages.reduce((a, b) => a + b, 0) / voltages.length;
            const avgCurrent = currents.reduce((a, b) => a + b, 0) / currents.length;
            const avgPF = powerFactors.length > 0 
                ? powerFactors.reduce((a, b) => a + b, 0) / powerFactors.length 
                : 0.85; // Default power factor if not available
            
            // Calculate 3-phase power in kW
            // P = √3 × V × I × PF / 1000
            const power = Math.sqrt(3) * avgVoltage * avgCurrent * avgPF / 1000;
            
            // Determine badge class based on power level
            let badgeClass = 'power-badge';
            if (power > 50) {
                badgeClass += ' high-power';
            } else if (power < 10) {
                badgeClass += ' low-power';
            }
            
            return `
                <div class="${badgeClass}" title="Calculated from V×I×PF (3-phase)">
                    <span class="power-label">⚡ Instantaneous Power</span>
                    <span class="power-value">${power.toFixed(2)} kW</span>
                </div>
            `;
        }

        function createUtilityCard(utilityId, utilityData) {
            const statusClass = getStatusClass(utilityData.status);
            const isMonitoring = monitoringIntervals.hasOwnProperty(utilityId);
            let registersHtml = '';
            if (utilityData.registers && Object.keys(utilityData.registers).length > 0) {
                // Dynamically categorize registers by their category field (no 'other' fallback)
                const categories = {};
                for (const [regKey, regData] of Object.entries(utilityData.registers)) {
                    if (regData.category) {
                        let cat = regData.category;
                        if (!categories[cat]) categories[cat] = [];
                        categories[cat].push({key: regKey, data: regData});
                    }
                }
                // Group categories: voltages/currents/power_factors on same row, then others
                const firstRowCats = ['voltages', 'currents', 'power', 'power_factors'];
                const allCats = Object.keys(categories);
                const sortedCats = [
                    ...firstRowCats.filter(c => allCats.includes(c)),
                    ...allCats.filter(c => !firstRowCats.includes(c)).sort()
                ];
                // Responsive row: voltages, currents, power_factors on first row, others on separate rows
                registersHtml = '<div class="registers-container">';
                
                // First row: voltages, currents, power_factors
                const firstRowCategories = sortedCats.filter(c => firstRowCats.includes(c));
                if (firstRowCategories.length > 0) {
                    registersHtml += '<div class="voltage-current-row">';
                    firstRowCategories.forEach((cat) => {
                        // Section title and icon
                        let icon = '';
                        if (cat === 'voltages') icon = '⚡';
                        else if (cat === 'currents') icon = '🔌';
                        else if (cat === 'power') icon = '⚡';
                        else if (cat === 'power_factors') icon = '📊';
                        else icon = '📊';
                        // Section CSS class
                        let sectionClass = `${cat}-section`;
                        // Grid class
                        let gridClass = ''
                        if (cat === 'voltages' || cat === 'currents') {
                            gridClass = `${cat.slice(0, -1)}-grid`;
                        } else if (cat === 'power_factors') {
                            gridClass = 'power_factor-grid';
                        } else if (cat === 'power') {
                            gridClass = 'power-grid';
                        }
                        const normalizedCategory = normalizeCategory(cat);
                        // Badge color class is the category name
                        registersHtml += `
                            <div class="readings-section ${sectionClass}">
                                <div class="section-title">${icon} ${cat.replace(/_/g, ' ').replace(\w/g, l => l.toUpperCase())} Readings</div>
                                <div class="registers-grid ${gridClass}">
                        `;
                        registersHtml += renderRegisterRows(categories[cat], normalizedCategory);
                        registersHtml += '</div></div>';
                    });
                    registersHtml += '</div>';
                }
                
                // Other categories on separate rows
                const otherCategories = sortedCats.filter(c => !firstRowCats.includes(c));
                if (otherCategories.length > 0) {
                    let maxPerRow = 3;
                    let rowCount = 0;
                    registersHtml += '<div class="voltage-current-row">';
                    otherCategories.forEach((cat, idx) => {
                        // Section title and icon
                        let icon = '';
                        if (cat === 'voltage') icon = '⚡';
                        else if (cat === 'current') icon = '🔌';
                        else if (cat === 'energy') icon = '🔋';
                        else icon = '📊';
                        // Section CSS class
                        let sectionClass = `${cat}-section`;
                        // Grid class
                        let gridClass = ''
                        if (cat === 'voltage' || cat === 'current') {
                            gridClass = `${cat}-grid`;
                        } else if (cat === 'power_factor') {
                            gridClass = 'power_factor-grid';
                        } else if (cat === 'power') {
                            gridClass = 'power-grid';
                        }
                        const normalizedCategory = normalizeCategory(cat);
                        // Badge color class is the category name
                        registersHtml += `
                            <div class="readings-section ${sectionClass}">
                                <div class="section-title">${icon} ${cat.replace(/_/g, ' ').replace(\w/g, l => l.toUpperCase())} Readings</div>
                                <div class="registers-grid ${gridClass}">
                        `;
                        registersHtml += renderRegisterRows(categories[cat], normalizedCategory);
                        registersHtml += '</div></div>';
                        rowCount++;
                        // If more than maxPerRow, close row and start new
                        if ((rowCount % maxPerRow === 0) && (idx < otherCategories.length - 1)) {
                            registersHtml += '</div><div class="voltage-current-row">';
                        }
                    });
                    registersHtml += '</div>';
                }
                
                registersHtml += '</div>';
                if (isMonitoring) {
                    registersHtml += getChartsHtml(utilityId);
                }
            } else {
                registersHtml = '<div class="no-data"><p>No register data available</p></div>';
            }
            return `
                <div class="utility-card" id="utility-${utilityId}">
                    <div class="utility-header">
                        <div class="utility-info">
                            <h3>${utilityData.name}</h3>
                            <div class="utility-details">
                                Cabinet ${utilityData.cabinet} | Node ${utilityData.node} | ${utilityData.ip_address}
                            </div>
                            <div class="utility-status ${statusClass}">
                                ${utilityData.status}
                            </div>
                            <div class="timestamp">
                                ${utilityData.timestamp || ''}
                            </div>
                            ${isMonitoring ? '<div class="monitor-status">🔴 Live Monitoring Active (2s)</div>' : ''}
                            <div id="power-badge-${utilityId}">
                                ${calculatePowerBadge(utilityData)}
                            </div>
                        </div>
                        <div class="utility-header-actions">
                            <button class="refresh-btn" onclick="refreshUtility('${utilityId}', this)">
                                🔄 Refresh
                            </button>
                            <button class="monitor-toggle ${isMonitoring ? 'active' : ''}" 
                                    onclick="toggleMonitoring('${utilityId}', this)"
                                    title="${isMonitoring ? 'Stop continuous monitoring' : 'Start continuous monitoring (2s)'}">
                                ${isMonitoring ? '🛑 Stop' : '🔴 Monitor'}
                            </button>
                        </div>
                    </div>
                    ${registersHtml}
                </div>
            `;
        }

        function createRegisterBadge(regData, category) {
            const badgeClass = regData.status === 'OK' ? category : 'error';
            const valueClass = regData.status === 'OK' ? '' : 'error';
            // Add data-category for dynamic coloring
            const attrParts = [];
            if (regData.status === 'OK' && !['voltage','current','energy','other'].includes(category)) {
                attrParts.push(`data-category="${category}"`);
            }
            // Show the type/category in the badge for clarity
            let typeLabel = '';
            if (regData.category && regData.category !== category) {
                typeLabel = `<div class='register-type'>${regData.category.replace(/_/g, ' ').replace(/\w/g, l => l.toUpperCase())}</div>`;
            }
            if (regData.description) {
                attrParts.push(`data-description="${escapeAttribute(regData.description)}"`);
            }
            const attrString = attrParts.length ? ` ${attrParts.join(' ')}` : '';
            const displayName = cleanLabel(regData.description || '', regData.category || category);
            return `
                <div class="register-badge ${badgeClass}"${attrString}>
                    ${typeLabel}
                    <div class="register-name">${displayName}</div>
                    <div class="register-measure">
                        <span class="register-value ${valueClass}">${regData.value}</span>
                        <span class="register-unit">${regData.unit || ''}</span>
                    </div>
                </div>
            `;
        }

        function normalizeCategory(category) {
            if (!category) return '';
            if (category === 'power_factors') return 'power_factor';
            if (category.endsWith('ies')) {
                return category.slice(0, -3) + 'y';
            }
            if (category.endsWith('s')) {
                return category.slice(0, -1);
            }
            return category;
        }

        function renderRegisterRows(registerList, categoryName) {
            if (!registerList || registerList.length === 0) {
                return '';
            }
            let rowsHtml = '';
            for (let i = 0; i < registerList.length; i += 3) {
                const rowItems = registerList.slice(i, i + 3);
                rowsHtml += '<div class="registers-row">';
                rowItems.forEach(reg => {
                    rowsHtml += createRegisterBadge(reg.data, categoryName);
                });
                rowsHtml += '</div>';
            }
            return rowsHtml;
        }

        function getStatusClass(status) {
            if (status === 'OK') return 'status-ok';
            if (status === 'PARTIAL') return 'status-partial';
            return 'status-error';
        }

        async function refreshAll() {
            if (isRefreshing) return;
            
            isRefreshing = true;
            const btn = document.getElementById('refreshAllBtn');
            btn.disabled = true;
            btn.textContent = '🔄 Reloading Config & Refreshing...';
            
            try {
                const response = await fetch('/api/refresh_all');
                const data = await response.json();
                
                if (data.success) {
                    // Update utilities count if configuration changed
                    if (data.utilities_count !== undefined && data.registers_count !== undefined) {
                        domRefs.utilitiesCount.textContent =
                            `Utilities: ${data.utilities_count} | Registers: ${data.registers_count}`;
                    }
                    
                    // Show configuration reload message with changes if provided
                    if (data.message) {
                        console.log('Configuration reloaded:', data.message);
                        let message = data.message;
                        if (data.changes && data.changes !== "No changes detected") {
                            message += `
Changes: ${data.changes}`;
                        }
                        showSuccess(message);
                    }
                    
                    // Log specific changes to console for debugging
                    if (data.added_utilities && data.added_utilities.length > 0) {
                        console.log('Added utilities:', data.added_utilities);
                    }
                    if (data.removed_utilities && data.removed_utilities.length > 0) {
                        console.log('Removed utilities:', data.removed_utilities);
                    }
                    
                    updateUI({
                        readings: data.readings,
                        last_update: data.timestamp,
                        connection_status: 'Configuration reloaded and refreshed',
                        utilities_count: data.utilities_count,
                        registers_count: data.registers_count
                    });
                } else {
                    showError(`Failed to refresh: ${data.error || 'Unknown error'}`);
                }
                
            } catch (error) {
                console.error('Error refreshing all:', error);
                showError('Error occurred while refreshing all utilities');
            } finally {
                isRefreshing = false;
                btn.disabled = false;
                btn.textContent = '🔄 Refresh All';
            }
        }

        async function refreshUtility(utilityId, button) {
            if (button && button.disabled) return;
            
            if (button) {
                button.disabled = true;
                button.className = 'refresh-btn loading';
                button.textContent = '🔄 Loading...';
            }
            
            try {
                const response = await fetch(`/api/refresh_utility/${utilityId}`);
                const data = await response.json();
                
                if (data.success) {
                    const isMonitoring = monitoringIntervals.hasOwnProperty(utilityId);
                    
                    if (isMonitoring) {
                        // If monitoring is active, update charts and register values only
                        updateCharts(utilityId, data.utility_data);
                        
                        // Update register values in the existing card
                        const utilityCard = document.getElementById(`utility-${utilityId}`);
                        if (utilityCard && data.utility_data.registers) {
                            Object.entries(data.utility_data.registers).forEach(([regKey, regData]) => {
                                // Update register badges
                                const registerBadges = utilityCard.querySelectorAll('.register-badge');
                                registerBadges.forEach(badge => {
                                    const originalDescription = badge.getAttribute('data-description');
                                    if (originalDescription && originalDescription === regData.description) {
                                            badge.setAttribute('data-description', regData.description || '');
                                            const nameElement = badge.querySelector('.register-name');
                                            const valueElement = badge.querySelector('.register-value');
                                            const unitElement = badge.querySelector('.register-unit');
                                            
                                            if (nameElement) {
                                                nameElement.textContent = cleanLabel(regData.description || '', regData.category || '');
                                            }
                                            if (valueElement) {
                                                valueElement.textContent = regData.value;
                                                valueElement.className = regData.status === 'OK' ? 'register-value' : 'register-value error';
                                            }
                                            if (unitElement) {
                                                unitElement.textContent = regData.unit || '';
                                            }
                                        }
                                    });
                                });

                                applyDynamicBadgeColors(utilityCard);

                            // Update utility status
                            const statusElement = utilityCard.querySelector('.utility-status');
                            if (statusElement) {
                                statusElement.textContent = data.utility_data.status;
                                statusElement.className = `utility-status ${getStatusClass(data.utility_data.status)}`;
                            }
                            
                            // Update timestamp
                            const timestampElement = utilityCard.querySelector('.timestamp');
                            if (timestampElement) {
                                timestampElement.textContent = data.utility_data.timestamp || '';
                            }
                            
                            // Update power badge during monitoring
                            const powerBadgeContainer = document.getElementById(`power-badge-${utilityId}`);
                            if (powerBadgeContainer) {
                                powerBadgeContainer.innerHTML = calculatePowerBadge(data.utility_data);
                            }

                            // Ensure charts are still present and functioning
                            const chartsContainer = document.getElementById(`charts-${utilityId}`);
                            if (!chartsContainer) {
                                console.log(`Charts missing for ${utilityId}, recreating...`);
                                const registersContainer = utilityCard.querySelector('.registers-container');
                                if (registersContainer) {
                                    const chartsHtml = getChartsHtml(utilityId);
                                    registersContainer.insertAdjacentHTML('afterend', chartsHtml);

                                    setTimeout(() => {
                                        initializeCharts(utilityId);
                                    }, 100);
                                }
                            } else {
                                // Charts exist, check if chart instances are still valid
                                const voltageCanvas = document.getElementById(`voltage-chart-${utilityId}`);
                                const currentCanvas = document.getElementById(`current-chart-${utilityId}`);
                                const powerCanvas = document.getElementById(`power-chart-${utilityId}`);
                                const powerFactorCanvas = document.getElementById(`powerfactor-chart-${utilityId}`);
                                
                                if (voltageCanvas && (!chartInstances[utilityId] || !chartInstances[utilityId].voltage)) {
                                    console.log(`Voltage chart instance missing for ${utilityId}, reinitializing...`);
                                    setTimeout(() => {
                                        initializeCharts(utilityId);
                                    }, 100);
                                } else if (currentCanvas && (!chartInstances[utilityId] || !chartInstances[utilityId].current)) {
                                    console.log(`Current chart instance missing for ${utilityId}, reinitializing...`);
                                    setTimeout(() => {
                                        initializeCharts(utilityId);
                                    }, 100);
                                } else if (powerCanvas && (!chartInstances[utilityId] || !chartInstances[utilityId].power)) {
                                    console.log(`Power chart instance missing for ${utilityId}, reinitializing...`);
                                    setTimeout(() => {
                                        initializeCharts(utilityId);
                                    }, 100);
                                } else if (powerFactorCanvas && (!chartInstances[utilityId] || !chartInstances[utilityId].powerFactor)) {
                                    console.log(`Power factor chart instance missing for ${utilityId}, reinitializing...`);
                                    setTimeout(() => {
                                        initializeCharts(utilityId);
                                    }, 100);
                                }
                            }
                        }
                    } else {
                        // Update just this utility in the UI (full card replacement)
                        const utilityCard = document.getElementById(`utility-${utilityId}`);
                        if (utilityCard) {
                            const newCardHtml = createUtilityCard(utilityId, data.utility_data);
                            utilityCard.outerHTML = newCardHtml;
                            const updatedCard = document.getElementById(`utility-${utilityId}`);
                            if (updatedCard) {
                                applyDynamicBadgeColors(updatedCard);
                            }
                        }
                    }
                } else {
                    // Check if this is a configuration issue
                    if (data.suggestion === 'reload_config') {
                        showError(`${data.error} Click "Refresh All" to reload configuration.`);
                    } else {
                        showError(`Failed to refresh utility: ${data.error || 'Unknown error'}`);
                    }
                }
                
            } catch (error) {
                console.error('Error refreshing utility:', error);
                showError('Error occurred while refreshing utility');
            } finally {
                if (button) {
                    button.disabled = false;
                    button.className = 'refresh-btn';
                    button.textContent = '🔄 Refresh';
                }
            }
        }

        function toggleMonitoring(utilityId, button) {
            if (button.disabled) return;
            
            const isCurrentlyMonitoring = monitoringIntervals.hasOwnProperty(utilityId);
            
            if (isCurrentlyMonitoring) {
                // Stop monitoring
                clearInterval(monitoringIntervals[utilityId]);
                delete monitoringIntervals[utilityId];
                
                button.className = 'monitor-toggle';
                button.textContent = '🔴 Monitor';
                button.title = 'Start continuous monitoring (2s)';
                
                // Remove monitor status
                const utilityCard = document.getElementById(`utility-${utilityId}`);
                const monitorStatus = utilityCard.querySelector('.monitor-status');
                if (monitorStatus) {
                    monitorStatus.remove();
                }

                // Remove charts
                const chartsContainer = document.getElementById(`charts-${utilityId}`);
                if (chartsContainer) {
                    chartsContainer.remove();
                }

                // Clean up chart instances
                if (chartInstances[utilityId]) {
                    if (chartInstances[utilityId].voltage) {
                        chartInstances[utilityId].voltage.destroy();
                    }
                    if (chartInstances[utilityId].current) {
                        chartInstances[utilityId].current.destroy();
                    }
                    if (chartInstances[utilityId].power) {
                        chartInstances[utilityId].power.destroy();
                    }
                    if (chartInstances[utilityId].powerFactor) {
                        chartInstances[utilityId].powerFactor.destroy();
                    }
                    delete chartInstances[utilityId];
                }

                // Clear chart data
                delete chartData[utilityId];
                
                console.log(`Stopped monitoring utility: ${utilityId}`);
                
            } else {
                // Start monitoring
                button.className = 'monitor-toggle active';
                button.textContent = '🛑 Stop';
                button.title = 'Stop continuous monitoring';
                
                // Add monitor status
                const utilityInfo = document.querySelector(`#utility-${utilityId} .utility-info`);
                if (utilityInfo && !utilityInfo.querySelector('.monitor-status')) {
                    const monitorStatus = document.createElement('div');
                    monitorStatus.className = 'monitor-status';
                    monitorStatus.textContent = '🔴 Live Monitoring Active (2s)';
                    utilityInfo.appendChild(monitorStatus);
                }

                // Add charts container
                const utilityCard = document.getElementById(`utility-${utilityId}`);
                const registersContainer = utilityCard.querySelector('.registers-container');
                if (registersContainer && !document.getElementById(`charts-${utilityId}`)) {
                    const chartsHtml = getChartsHtml(utilityId);
                    registersContainer.insertAdjacentHTML('afterend', chartsHtml);
                }

                // Initialize charts (clear any existing data)
                clearCharts(utilityId);
                setTimeout(() => {
                    initializeCharts(utilityId);
                }, 100);
                
                // Start interval for continuous monitoring
                monitoringIntervals[utilityId] = setInterval(async () => {
                    try {
                        await refreshUtility(utilityId, null); // Don't pass button to avoid UI changes
                    } catch (error) {
                        console.error(`Error in continuous monitoring for ${utilityId}:`, error);
                    }
                }, 2000); // 2 second interval
                
                console.log(`Started continuous monitoring for utility: ${utilityId}`);
            }
            
            // Update monitoring count in status bar
            updateMonitoringCount();
        }

        function updateMonitoringCount() {
            const monitoringCount = Object.keys(monitoringIntervals).length;
            const countElement = domRefs.monitoringCount;
            if (countElement) {
                countElement.textContent = `Live Monitoring: ${monitoringCount}`;
                countElement.style.color = monitoringCount > 0 ? '#e74c3c' : '#7f8c8d';
                countElement.style.fontWeight = monitoringCount > 0 ? 'bold' : 'normal';
            }
        }

        function showError(message) {
            const grid = domRefs.utilitiesGrid;
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.textContent = message;

            // Insert at the top
            grid.insertBefore(errorDiv, grid.firstChild);
            
            // Remove after 5 seconds
            setTimeout(() => {
                if (errorDiv.parentNode) {
                    errorDiv.parentNode.removeChild(errorDiv);
                }
            }, 5000);
        }

        function showSuccess(message) {
            const grid = domRefs.utilitiesGrid;
            const successDiv = document.createElement('div');
            successDiv.className = 'success-message';
            successDiv.textContent = message;
            
            // Insert at the top
            grid.insertBefore(successDiv, grid.firstChild);
            
            // Remove after 5 seconds
            setTimeout(() => {
                if (successDiv.parentNode) {
                    successDiv.parentNode.removeChild(successDiv);
                }
            }, 5000);
        }
    </script>
</body>
</html>'''
    
    with open('templates/energy_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("HTML template created: templates/energy_dashboard.html")

if __name__ == '__main__':
    # Avvia il server Flask sulla porta 5050
    app.run(host='0.0.0.0', port=5050, debug=True)
    print("Energy Meter Web Server - Excel Configuration Based")
    print("=" * 60)
    print()
    
    # Create HTML template
    create_html_template()
    
    # Perform initial reading in background thread (one time only)
    print("Performing initial reading of all utilities (startup only)...")
    bg_thread = threading.Thread(target=background_reading_thread, daemon=True)
    bg_thread.start()
    
    # Wait for initial reading to complete
    bg_thread.join(timeout=10)  # Wait max 10 seconds for initial reading
    
    print(f"\nStarting web server on http://localhost:5000")
    print(f"Configuration: {len(utilities_config)} utilities, {len(registers_config)} registers")
    print("📋 Use 'Refresh All' or individual 'Refresh' buttons to update readings")
    print("🔴 Use 'Monitor' buttons for real-time monitoring (2s intervals)")
    print("Press Ctrl+C to stop the server")
    print()
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user")

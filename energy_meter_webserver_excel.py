#!/usr/bin/env python3
"""
Energy Meter Web Server - Enhanced with Excel Configuration
Displays energy meter readings in a web interface using configuration from Excel files:
- Utenze.xlsx: Contains the specific utilities to monitor (Cabinet, Node, Utility name)
- registri.xlsx: Contains the registers to read with Report column filtering
Features individual machine refresh buttons and real-time updates
"""

from flask import Flask, render_template, jsonify, request
from pymodbus.constants import Endian
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
        """Load register configuration from registri.xlsx (only Report=Yes registers)"""
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
                    'target_unit': target_unit
                }
                
                print(f"  ✅ Register: {description} (Address: {start_address}-{end_address})")
            
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
            request = client.read_holding_registers(address=start_address, count=register_count, slave=node_id)
            
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
                            'status': 'OK'
                        }
                    else:
                        utility_data['registers'][register_key] = {
                            'description': register_info['description'],
                            'value': 'N/A',
                            'unit': register_info.get('target_unit', ''),
                            'status': 'ERROR'
                        }
                        utility_data['status'] = 'PARTIAL'
                        
                except Exception as e:
                    register_key = f"reg_{start_address}"
                    utility_data['registers'][register_key] = {
                        'description': register_info['description'],
                        'value': 'ERROR',
                        'unit': register_info.get('target_unit', ''),
                        'status': 'ERROR'
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
    """API endpoint to refresh all utilities"""
    print("Manual refresh of all utilities requested")
    readings = energy_reader.read_all_utilities()
    
    return jsonify({
        'success': True,
        'readings': readings,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

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
        return jsonify({'success': False, 'error': 'Utility not found'}), 404
    
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
    """Background thread to periodically read all utilities"""
    global energy_reader
    
    print("Starting background reading thread...")
    
    while True:
        try:
            print("Background reading cycle starting...")
            energy_reader.read_all_utilities()
            print("Background reading cycle completed")
            
            # Wait 30 seconds before next reading
            time.sleep(30)
            
        except Exception as e:
            print(f"Error in background reading: {e}")
            time.sleep(10)  # Wait less time on error

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
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
            color: white;
            padding: 20px 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .status-bar {
            background: #ecf0f1;
            padding: 15px 30px;
            border-bottom: 1px solid #bdc3c7;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }

        .status-item {
            display: flex;
            align-items: center;
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
        }

        .utility-card {
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }

        .utility-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.15);
        }

        .utility-header {
            background: #f8f9fa;
            padding: 20px;
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .utility-info h3 {
            color: #2c3e50;
            font-size: 1.3em;
            margin-bottom: 5px;
        }

        .utility-details {
            color: #7f8c8d;
            font-size: 0.9em;
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

        .registers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px;
            padding: 20px;
        }

        .register-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #3498db;
        }

        .register-item.error {
            border-left-color: #e74c3c;
            background: #fdf2f2;
        }

        .register-item.ok {
            border-left-color: #27ae60;
        }

        .register-name {
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 8px;
            font-size: 0.9em;
            line-height: 1.3;
        }

        .register-value {
            font-size: 1.4em;
            font-weight: bold;
            color: #3498db;
        }

        .register-value.error {
            color: #e74c3c;
        }

        .register-unit {
            color: #7f8c8d;
            font-size: 0.8em;
            margin-left: 5px;
        }

        .utility-status {
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: bold;
            text-transform: uppercase;
        }

        .status-ok {
            background: #d5edda;
            color: #155724;
        }

        .status-error {
            background: #f8d7da;
            color: #721c24;
        }

        .status-partial {
            background: #fff3cd;
            color: #856404;
        }

        .loading {
            opacity: 0.7;
            pointer-events: none;
        }

        .timestamp {
            color: #7f8c8d;
            font-size: 0.8em;
            margin-top: 5px;
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

            .registers-grid {
                grid-template-columns: 1fr;
            }

            .header h1 {
                font-size: 2em;
            }
        }

        .no-data {
            text-align: center;
            padding: 50px;
            color: #7f8c8d;
        }

        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            border: 1px solid #f5c6cb;
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

        // Load initial data when page loads
        document.addEventListener('DOMContentLoaded', function() {
            loadConfiguration();
            loadReadings();
            
            // Auto-refresh every 30 seconds
            setInterval(loadReadings, 30000);
        });

        async function loadConfiguration() {
            try {
                const response = await fetch('/api/configuration');
                const data = await response.json();
                
                console.log('Configuration loaded:', data);
                document.getElementById('utilitiesCount').textContent = 
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
            // Update connection status
            const indicator = document.getElementById('connectionIndicator');
            const status = document.getElementById('connectionStatus');
            const lastUpdate = document.getElementById('lastUpdate');
            
            if (data.connection_status && data.connection_status.includes('Connected')) {
                indicator.className = 'status-indicator connected';
                status.textContent = data.connection_status;
            } else {
                indicator.className = 'status-indicator';
                status.textContent = data.connection_status || 'Disconnected';
            }
            
            lastUpdate.textContent = `Last Update: ${data.last_update || 'Never'}`;
            
            // Update utilities grid
            const grid = document.getElementById('utilitiesGrid');
            
            if (!data.readings || Object.keys(data.readings).length === 0) {
                grid.innerHTML = `
                    <div class="no-data">
                        <h3>No data available</h3>
                        <p>Click "Refresh All" to load readings from all utilities.</p>
                    </div>
                `;
                return;
            }
            
            let html = '';
            for (const [utilityId, utilityData] of Object.entries(data.readings)) {
                html += createUtilityCard(utilityId, utilityData);
            }
            
            grid.innerHTML = html;
        }

        function createUtilityCard(utilityId, utilityData) {
            const statusClass = getStatusClass(utilityData.status);
            
            let registersHtml = '';
            if (utilityData.registers && Object.keys(utilityData.registers).length > 0) {
                registersHtml = '<div class="registers-grid">';
                for (const [regKey, regData] of Object.entries(utilityData.registers)) {
                    const registerClass = regData.status === 'OK' ? 'ok' : 'error';
                    const valueClass = regData.status === 'OK' ? '' : 'error';
                    
                    registersHtml += `
                        <div class="register-item ${registerClass}">
                            <div class="register-name">${regData.description}</div>
                            <div class="register-value ${valueClass}">
                                ${regData.value}
                                <span class="register-unit">${regData.unit || ''}</span>
                            </div>
                        </div>
                    `;
                }
                registersHtml += '</div>';
            } else {
                registersHtml = '<div class="no-data"><p>No register data available</p></div>';
            }
            
            return `
                <div class="utility-card">
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
                        </div>
                        <button class="refresh-btn" onclick="refreshUtility('${utilityId}', this)">
                            🔄 Refresh
                        </button>
                    </div>
                    ${registersHtml}
                </div>
            `;
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
            btn.textContent = '🔄 Refreshing...';
            
            try {
                const response = await fetch('/api/refresh_all');
                const data = await response.json();
                
                if (data.success) {
                    updateUI({
                        readings: data.readings,
                        last_update: data.timestamp,
                        connection_status: 'Manual refresh completed'
                    });
                } else {
                    showError('Failed to refresh all utilities');
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
            if (button.disabled) return;
            
            button.disabled = true;
            button.className = 'refresh-btn loading';
            button.textContent = '🔄 Loading...';
            
            try {
                const response = await fetch(`/api/refresh_utility/${utilityId}`);
                const data = await response.json();
                
                if (data.success) {
                    // Update just this utility in the UI
                    const utilityCard = button.closest('.utility-card');
                    const newCardHtml = createUtilityCard(utilityId, data.utility_data);
                    utilityCard.outerHTML = newCardHtml;
                } else {
                    showError(`Failed to refresh utility: ${data.error || 'Unknown error'}`);
                }
                
            } catch (error) {
                console.error('Error refreshing utility:', error);
                showError('Error occurred while refreshing utility');
            } finally {
                button.disabled = false;
                button.className = 'refresh-btn';
                button.textContent = '🔄 Refresh';
            }
        }

        function showError(message) {
            const grid = document.getElementById('utilitiesGrid');
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
    </script>
</body>
</html>'''
    
    with open('templates/energy_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("HTML template created: templates/energy_dashboard.html")

if __name__ == '__main__':
    print("Energy Meter Web Server - Excel Configuration Based")
    print("=" * 60)
    print()
    
    # Create HTML template
    create_html_template()
    
    # Perform initial reading
    print("Performing initial reading of all utilities...")
    energy_reader.read_all_utilities()
    
    # Start background thread for automatic readings
    bg_thread = threading.Thread(target=background_reading_thread, daemon=True)
    bg_thread.start()
    
    print(f"\nStarting web server on http://localhost:5000")
    print(f"Configuration: {len(utilities_config)} utilities, {len(registers_config)} registers")
    print("Press Ctrl+C to stop the server")
    print()
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user")

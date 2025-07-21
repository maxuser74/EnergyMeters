#!/usr/bin/env python3
"""
Energy Meter Web Server
Displays energy meter readings in a web interface with automatic refresh
Updated with multi-cabinet functionality
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

app = Flask(__name__)

# Global variables to store the latest readings
latest_readings = {}
last_update_time = None
connection_status = "Disconnected"
historical_data = []  # Store historical data for graphs

class EnergyMeterReader:
    def __init__(self):
        # Multiple energy meter configurations (individual meters for detailed view)
        self.energy_meters = [
            {
                'id': 'cabinet1_node1',
                'name': 'Cabinet 1 - Node 1',
                'cabina': '192.168.156.75',
                'nodo': 1,
                'port': 502
            },
            {
                'id': 'cabinet1_node13',
                'name': 'Cabinet 1 - Node 13',
                'cabina': '192.168.156.75',
                'nodo': 13,
                'port': 502
            },
            {
                'id': 'cabinet2_node1',
                'name': 'Cabinet 2 - Node 1',
                'cabina': '192.168.156.76',
                'nodo': 1,
                'port': 502
            },
            {
                'id': 'cabinet2_node14',
                'name': 'Cabinet 2 - Node 14',
                'cabina': '192.168.156.76',
                'nodo': 14,
                'port': 502
            },
            {
                'id': 'cabinet3_node1',
                'name': 'Cabinet 3 - Node 1',
                'cabina': '192.168.156.77',
                'nodo': 1,
                'port': 502
            }
        ]
        
        # Cabinet configurations for multi-node view (all nodes in each cabinet)
        self.cabinets = [
            {'name': 'Cabinet 1', 'ip': '192.168.156.75', 'nodes': range(1, 27)},
            {'name': 'Cabinet 2', 'ip': '192.168.156.76', 'nodes': range(1, 22)},
            {'name': 'Cabinet 3', 'ip': '192.168.156.77', 'nodes': range(1, 16)}
        ]
        
        # Register definitions (corrected based on register analysis)
        self.registers = {
            358: "Tensione RMS stella L1-N V (RMS star voltage L1-N V)",
            374: "Corrente di linea L1 A (Line current L1 A)", 
            376: "Corrente di linea L2 A (Line current L2 A)",
            378: "Corrente di linea L3 A (Line current L3 A)",
            390: "Potenza ATTIVA somma RMS Watt (RMS sum active power Watt)"
        }
        
        # Simplified registers for multi-cabinet view (current only)
        self.simple_registers = {
            374: "Current L1 (A)", 
            376: "Current L2 (A)",
            378: "Current L3 (A)",
        }
        
    def read_single_register(self, client, registro, nodo):
        """Read a single register and return the float value"""
        try:
            request = client.read_holding_registers(address=registro, count=2, slave=nodo)
            
            if request.isError():
                return None
                
            # Convert the two 16-bit registers to a 32-bit float
            high_word = request.registers[0]
            low_word = request.registers[1]
            
            # Convert to 32-bit float: word order is little endian (low word first)
            packed_data = struct.pack('>HH', low_word, high_word)
            valore = struct.unpack('>f', packed_data)[0]
            
            return valore
            
        except Exception as e:
            print(f"Error reading register {registro} from node {nodo}: {e}")
            return None
    
    def read_single_meter(self, meter_config):
        """Read all registers from a single energy meter with resilience"""
        cabina = meter_config['cabina']
        nodo = meter_config['nodo']
        port = meter_config['port']
        meter_id = meter_config['id']
        meter_name = meter_config['name']
        
        # Set shorter timeout to avoid hanging
        client = ModbusTcpClient(cabina, port=port, timeout=3)
        
        try:
            print(f"Attempting connection to {meter_name} ({cabina}:{port}, node {nodo})...")
            
            # Connect to the device with timeout handling
            connection_result = client.connect()
            if not connection_result:
                print(f"WARNING Connection failed: {meter_name} at {cabina}:{port}")
                return {
                    'meter_id': meter_id,
                    'meter_name': meter_name,
                    'connection_status': 'Connection Failed',
                    'connection_info': {
                        'ip_address': cabina,
                        'port': port,
                        'device_id': nodo
                    },
                    'readings': {},
                    'error_details': f'Cannot connect to {cabina}:{port}'
                }
            
            print(f"Connected to {meter_name}")
            results = {}
            failed_registers = []
            
            # Read each register with individual error handling
            for registro, description in self.registers.items():
                try:
                    value = self.read_single_register(client, registro, nodo)
                    if value is not None:
                        results[registro] = {
                            'value': value,
                            'description': description
                        }
                        print(f"  Register {registro}: {value:.2f}")
                    else:
                        failed_registers.append(registro)
                        print(f"  Register {registro}: No data")
                except Exception as reg_error:
                    failed_registers.append(registro)
                    print(f"  Register {registro}: Error - {reg_error}")
            
            # Determine connection status based on successful reads
            if len(results) == len(self.registers):
                status = 'Connected'
            elif len(results) > 0:
                status = f'Partial ({len(results)}/{len(self.registers)} registers)'
            else:
                status = 'No Data'
            
            return {
                'meter_id': meter_id,
                'meter_name': meter_name,
                'connection_status': status,
                'connection_info': {
                    'ip_address': cabina,
                    'port': port,
                    'device_id': nodo
                },
                'readings': results,
                'failed_registers': failed_registers,
                'registers_read': f"{len(results)}/{len(self.registers)}"
            }
            
        except ConnectionException as conn_error:
            print(f"Connection error for {meter_name}: {conn_error}")
            return {
                'meter_id': meter_id,
                'meter_name': meter_name,
                'connection_status': 'Connection Error',
                'connection_info': {
                    'ip_address': cabina,
                    'port': port,
                    'device_id': nodo
                },
                'readings': {},
                'error_details': f'Connection error: {str(conn_error)}'
            }
        except Exception as e:
            print(f"Unexpected error reading {meter_name}: {e}")
            return {
                'meter_id': meter_id,
                'meter_name': meter_name,
                'connection_status': f'Error: {type(e).__name__}',
                'connection_info': {
                    'ip_address': cabina,
                    'port': port,
                    'device_id': nodo
                },
                'readings': {},
                'error_details': f'Unexpected error: {str(e)}'
            }
            
        finally:
            try:
                client.close()
                print(f"Connection closed for {meter_name}")
            except Exception as close_error:
                print(f"Error closing connection for {meter_name}: {close_error}")

    def read_all_registers(self):
        """Read all energy meter registers from all configured meters with resilience"""
        global latest_readings, last_update_time, connection_status, historical_data
        
        all_results = {}
        successful_connections = 0
        partial_connections = 0
        
        print(f"Reading from {len(self.energy_meters)} energy meters...")
        
        for meter_config in self.energy_meters:
            print(f"Processing {meter_config['name']}...")
            meter_result = self.read_single_meter(meter_config)
            all_results[meter_result['meter_id']] = meter_result
            
            # Count connection types for overall status
            status = meter_result['connection_status']
            if status == 'Connected':
                successful_connections += 1
            elif 'Partial' in status:
                partial_connections += 1
                print(f"WARNING {meter_config['name']}: Partial connection - {status}")
            else:
                print(f"ERROR {meter_config['name']}: Connection failed - {status}")
        
        # Update global variables
        latest_readings = all_results
        current_time = datetime.now()
        last_update_time = current_time
        
        # Update overall connection status
        total_meters = len(self.energy_meters)
        if successful_connections == total_meters:
            connection_status = "All Connected"
        elif successful_connections + partial_connections == total_meters:
            connection_status = f"WARNING {successful_connections} Connected, {partial_connections} Partial"
        elif successful_connections > 0:
            failed_connections = total_meters - successful_connections - partial_connections
            connection_status = f"MIXED {successful_connections} Connected, {partial_connections} Partial, {failed_connections} Failed"
        else:
            connection_status = "All Disconnected"
        
        # Store historical data for graphs (keep last 50 readings)
        # Only store data from meters that have at least some readings
        if all_results:
            data_point = {
                'timestamp': current_time.isoformat()
            }
            
            # Add data for each meter that has readings
            for meter_id, meter_data in all_results.items():
                readings = meter_data.get('readings', {})
                if readings:  # Only add data if we have readings
                    data_point[meter_id] = {
                        'voltage': readings.get(358, {}).get('value', 0),
                        'current_l1': readings.get(374, {}).get('value', 0),
                        'current_l2': readings.get(376, {}).get('value', 0),
                        'current_l3': readings.get(378, {}).get('value', 0),
                        'power': readings.get(390, {}).get('value', 0)
                    }
            
            # Only store historical point if we have at least one meter with data
            if any(meter_id in data_point for meter_id in all_results.keys() if meter_id != 'timestamp'):
                historical_data.append(data_point)
                
                # Keep only last 50 readings (about 4 minutes of data)
                if len(historical_data) > 50:
                    historical_data = historical_data[-50:]
        
        successful_readings = successful_connections + partial_connections
        print(f"Summary: {successful_connections} fully connected, {partial_connections} partial, {total_meters - successful_readings} failed")
        print(f"Update completed at {last_update_time.strftime('%H:%M:%S')}")
        
        # Return True if we have at least some data (even partial)
        return successful_readings > 0

    def read_all_cabinet_data(self):
        """
        Read current data from all nodes in all cabinets (like energy_meter_reader.py)
        Returns simplified data structure for tabular display
        """
        all_data = []
        port = 502
        
        print(f"Reading all cabinet data from {len(self.cabinets)} cabinets...")
        
        for cabinet in self.cabinets:
            cabinet_name = cabinet['name']
            cabina = cabinet['ip']
            nodes = cabinet['nodes']
            
            # Create Modbus TCP client for this cabinet
            client = ModbusTcpClient(cabina, port=port, timeout=3)
            
            try:
                # Connect to the device
                connection_result = client.connect()
                if not connection_result:
                    print(f"ERROR Cannot connect to {cabinet_name} at {cabina}:{port}")
                    # Add error row to data
                    all_data.append({
                        'cabinet': cabinet_name,
                        'ip_address': cabina,
                        'node': 'N/A',
                        'current_l1_a': None,
                        'current_l2_a': None, 
                        'current_l3_a': None,
                        'status': 'CONNECTION_FAILED',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    continue
                
                print(f"Connected to {cabinet_name}")
                
                # Iterate through nodes for this cabinet
                for nodo in nodes:
                    node_results = {}
                    node_status = "OK"
                    
                    # Read each register for this node
                    for registro, description in self.simple_registers.items():
                        try:
                            # Read 2 registers (32-bit float)
                            request = client.read_holding_registers(address=registro, count=2, slave=nodo)
                            
                            if request.isError():
                                node_results[registro] = None
                                node_status = "ERROR"
                                continue
                                
                            # Decode the 32-bit float value
                            high_word = request.registers[0]
                            low_word = request.registers[1]
                            
                            # Convert to 32-bit float: word order is little endian (low word first)
                            packed_data = struct.pack('>HH', low_word, high_word)
                            valore = struct.unpack('>f', packed_data)[0]
                            
                            # Round to 2 decimal places
                            valore = round(valore, 2)
                            
                            # Store result
                            node_results[registro] = valore
                            
                        except Exception as e:
                            node_results[registro] = None
                            node_status = "FAIL"
                    
                    # Add to data collection
                    all_data.append({
                        'cabinet': cabinet_name,
                        'ip_address': cabina,
                        'node': nodo,
                        'current_l1_a': node_results.get(374, None),
                        'current_l2_a': node_results.get(376, None), 
                        'current_l3_a': node_results.get(378, None),
                        'status': node_status,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                
            except Exception as e:
                print(f"ERROR connecting to {cabinet_name}: {e}")
                # Add error row to data
                all_data.append({
                    'cabinet': cabinet_name,
                    'ip_address': cabina,
                    'node': 'N/A',
                    'current_l1_a': None,
                    'current_l2_a': None, 
                    'current_l3_a': None,
                    'status': f'EXCEPTION: {str(e)[:50]}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                
            finally:
                # Always close the connection
                try:
                    client.close()
                    print(f"Connection closed for {cabinet_name}")
                except:
                    pass
        
        print(f"Cabinet data read complete: {len(all_data)} total nodes")
        return all_data

# Initialize the energy meter reader
meter_reader = EnergyMeterReader()

def background_reader():
    """Background thread to continuously read energy meter data"""
    while True:
        meter_reader.read_all_registers()
        time.sleep(5)  # Wait 5 seconds before next reading

@app.route('/')
def index():
    """Main page showing energy meter readings"""
    return render_template('index.html')

@app.route('/api/readings')
def api_readings():
    """API endpoint to get current readings as JSON"""
    global latest_readings, last_update_time, connection_status, historical_data
    
    # Meter configurations for display
    meter_configs = [
        {
            'id': meter['id'],
            'name': meter['name'],
            'ip_address': meter['cabina'],
            'port': meter['port'],
            'device_id': meter['nodo']
        }
        for meter in meter_reader.energy_meters
    ]
    
    return jsonify({
        'readings': latest_readings,
        'meter_configs': meter_configs,
        'historical_data': historical_data,
        'last_update': last_update_time.isoformat() if last_update_time else None,
        'connection_status': connection_status,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/status')
def api_status():
    """API endpoint to get connection status"""
    return jsonify({
        'status': connection_status,
        'last_update': last_update_time.isoformat() if last_update_time else None,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/cabinet-data')
def api_cabinet_data():
    """API endpoint to get all cabinet data (all nodes from all cabinets)"""
    try:
        # Read all cabinet data
        cabinet_data = meter_reader.read_all_cabinet_data()
        
        # Calculate summary statistics
        valid_data = [row for row in cabinet_data if row['status'] == 'OK']
        total_nodes = len(cabinet_data)
        successful_nodes = len(valid_data)
        
        # Calculate current statistics if we have valid data
        stats = {
            'total_nodes': total_nodes,
            'successful_nodes': successful_nodes,
            'failed_nodes': total_nodes - successful_nodes
        }
        
        if valid_data:
            l1_currents = [row['current_l1_a'] for row in valid_data if row['current_l1_a'] is not None]
            l2_currents = [row['current_l2_a'] for row in valid_data if row['current_l2_a'] is not None]
            l3_currents = [row['current_l3_a'] for row in valid_data if row['current_l3_a'] is not None]
            
            if l1_currents:
                stats['l1_max'] = round(max(l1_currents), 2)
                stats['l1_avg'] = round(sum(l1_currents) / len(l1_currents), 2)
            if l2_currents:
                stats['l2_max'] = round(max(l2_currents), 2)
                stats['l2_avg'] = round(sum(l2_currents) / len(l2_currents), 2)
            if l3_currents:
                stats['l3_max'] = round(max(l3_currents), 2)
                stats['l3_avg'] = round(sum(l3_currents) / len(l3_currents), 2)
        
        return jsonify({
            'success': True,
            'data': cabinet_data,
            'statistics': stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """API endpoint to get or update configuration"""
    global meter_reader, historical_data
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Update configuration
            if 'ip_address' in data:
                meter_reader.cabina = data['ip_address']
            if 'port' in data:
                meter_reader.port = int(data['port'])
            if 'device_id' in data:
                meter_reader.nodo = int(data['device_id'])
            
            # Clear historical data when configuration changes
            historical_data.clear()
            
            return jsonify({
                'success': True,
                'message': 'Configuration updated successfully',
                'config': {
                    'ip_address': meter_reader.cabina,
                    'port': meter_reader.port,
                    'device_id': meter_reader.nodo
                }
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error updating configuration: {str(e)}'
            }), 400
    
    else:  # GET request
        return jsonify({
            'config': {
                'ip_address': meter_reader.cabina,
                'port': meter_reader.port,
                'device_id': meter_reader.nodo
            }
        })

if __name__ == '__main__':
    # Create templates directory and HTML template
    import os
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    
    # Create the HTML template with tabs
    html_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Energy Meter Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            padding: 30px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 3px solid #667eea;
            padding-bottom: 20px;
        }
        
        .header h1 {
            color: #667eea;
            margin: 0 0 15px 0;
            font-size: 2.5em;
        }
        
        /* Tab styles */
        .tabs {
            display: flex;
            border-bottom: 2px solid #e9ecef;
            margin-bottom: 20px;
        }
        
        .tab {
            padding: 12px 24px;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 16px;
            font-weight: 600;
            color: #6c757d;
            border-bottom: 3px solid transparent;
            transition: all 0.3s ease;
            position: relative;
        }
        
        .tab:hover {
            color: #667eea;
            background-color: #f8f9fa;
        }
        
        .tab.active {
            color: #667eea;
            border-bottom-color: #667eea;
            background-color: #f8f9fa;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .connection-info {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            border-left: 4px solid #667eea;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        
        .card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
            text-align: center;
            min-height: 120px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        
        .card:hover {
            transform: translateY(-5px);
        }
        
        .card h3 {
            margin: 0 0 8px 0;
            color: #495057;
            font-size: 0.95em;
        }
        
        .card .value {
            font-size: 1.8em;
            font-weight: bold;
            color: #667eea;
            margin: 5px 0;
        }
        
        .card .unit {
            color: #6c757d;
            font-size: 0.9em;
        }
        
        /* Table styles for cabinet view */
        .table-container {
            overflow-x: auto;
            margin-bottom: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        
        .data-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
        }
        
        .data-table th,
        .data-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
        }
        
        .data-table th {
            background-color: #667eea;
            color: white;
            font-weight: 600;
            position: sticky;
            top: 0;
        }
        
        .data-table tr:hover {
            background-color: #f8f9fa;
        }
        
        .status-ok {
            color: #28a745;
            font-weight: bold;
        }
        
        .status-error {
            color: #dc3545;
            font-weight: bold;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            border-left: 4px solid #667eea;
        }
        
        .stat-value {
            font-size: 1.5em;
            font-weight: bold;
            color: #667eea;
        }
        
        .stat-label {
            color: #6c757d;
            font-size: 0.9em;
            margin-top: 5px;
        }
        
        .controls {
            margin-bottom: 20px;
            text-align: center;
        }
        
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            margin: 0 10px;
            transition: background-color 0.3s ease;
        }
        
        .btn:hover {
            background: #5a6fd8;
        }
        
        .btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
        }
        
        .loading {
            text-align: center;
            padding: 20px;
            color: #6c757d;
            font-style: italic;
        }
        
        .last-update {
            text-align: center;
            color: #6c757d;
            margin-top: 20px;
            font-style: italic;
        }
        
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            border: 1px solid #f5c6cb;
        }
        
        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            border: 1px solid #c3e6cb;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ Energy Meter Monitor</h1>
            <div id="connection-info" class="connection-info">
                <div class="loading">Loading connection info...</div>
            </div>
        </div>
        
        <!-- Tab Navigation -->
        <div class="tabs">
            <button class="tab active" onclick="switchTab('individual')">📊 Individual Meters</button>
            <button class="tab" onclick="switchTab('cabinet')">🏗️ All Cabinets</button>
        </div>
        
        <!-- Individual Meters Tab -->
        <div id="individual-tab" class="tab-content active">
            <div id="status" class="status">
                <div class="loading">Loading...</div>
            </div>
            
            <div id="readings-container">
                <div class="loading">Fetching energy meter data...</div>
            </div>
        </div>
        
        <!-- Cabinet View Tab -->
        <div id="cabinet-tab" class="tab-content">
            <div class="controls">
                <button class="btn" onclick="loadCabinetData()" id="refreshCabinetBtn">🔄 Refresh Cabinet Data</button>
                <button class="btn" onclick="exportCabinetData()" id="exportBtn" disabled>📥 Export to CSV</button>
            </div>
            
            <div id="cabinet-stats" class="stats-grid" style="display: none;">
                <!-- Statistics will be populated here -->
            </div>
            
            <div id="cabinet-data-container">
                <div class="loading">Click "Refresh Cabinet Data" to load all meters...</div>
            </div>
        </div>
        
        <div id="last-update" class="last-update"></div>
    </div>
    
    <script>
        let currentData = {};
        let cabinetData = [];
        
        // Tab switching functionality
        function switchTab(tabName) {
            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab content
            document.getElementById(tabName + '-tab').classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
        }
        
        // Individual meters functions
        function updateReadings() {
            fetch('/api/readings')
                .then(response => response.json())
                .then(data => {
                    currentData = data;
                    displayReadings(data);
                    updateConnectionInfo(data);
                    updateLastUpdate(data.last_update);
                })
                .catch(error => {
                    console.error('Error fetching readings:', error);
                    document.getElementById('readings-container').innerHTML = 
                        '<div class="error-message">Error fetching readings: ' + error.message + '</div>';
                });
        }
        
        function displayReadings(data) {
            if (!data.readings || Object.keys(data.readings).length === 0) {
                document.getElementById('readings-container').innerHTML = 
                    '<div class="loading">No energy meter data available</div>';
                return;
            }
            
            let html = '<div class="grid">';
            
            // Process each meter
            Object.keys(data.readings).forEach(meterId => {
                const meter = data.readings[meterId];
                const meterName = meter.meter_name || meterId;
                const connectionStatus = meter.connection_status || 'Unknown';
                const readings = meter.readings || {};
                
                // Status indicator
                let statusClass = 'status-error';
                let statusIcon = '❌';
                if (connectionStatus === 'Connected') {
                    statusClass = 'status-ok';
                    statusIcon = '✅';
                } else if (connectionStatus.includes('Partial')) {
                    statusClass = 'status-warning';
                    statusIcon = '⚠️';
                }
                
                html += `
                    <div class="card">
                        <h3>${meterName}</h3>
                        <div class="${statusClass}">${statusIcon} ${connectionStatus}</div>
                        <div style="margin-top: 10px; font-size: 0.8em; color: #6c757d;">
                            ${meter.connection_info ? meter.connection_info.ip_address + ':' + meter.connection_info.port + ' (Node ' + meter.connection_info.device_id + ')' : ''}
                        </div>
                        <div style="margin-top: 10px;">
                            ${Object.keys(readings).length > 0 ? 
                                Object.keys(readings).map(regKey => {
                                    const reading = readings[regKey];
                                    return `<div style="margin: 5px 0;"><strong>${reading.description.split('(')[0]}</strong><br>${reading.value.toFixed(2)} ${regKey == 358 ? 'V' : regKey == 390 ? 'W' : 'A'}</div>`;
                                }).join('')
                                : '<div style="color: #dc3545;">No data available</div>'
                            }
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
            document.getElementById('readings-container').innerHTML = html;
        }
        
        function updateConnectionInfo(data) {
            const connectionInfo = document.getElementById('connection-info');
            const status = data.connection_status || 'Unknown';
            
            connectionInfo.innerHTML = `
                <strong>Connection Status:</strong> ${status}<br>
                <strong>Total Meters:</strong> ${Object.keys(data.readings || {}).length}<br>
                <strong>Last Update:</strong> ${data.last_update ? new Date(data.last_update).toLocaleString() : 'Never'}
            `;
        }
        
        function updateLastUpdate(lastUpdate) {
            const element = document.getElementById('last-update');
            if (lastUpdate) {
                element.textContent = `Last updated: ${new Date(lastUpdate).toLocaleString()}`;
            } else {
                element.textContent = 'No updates available';
            }
        }
        
        // Cabinet data functions
        function loadCabinetData() {
            const refreshBtn = document.getElementById('refreshCabinetBtn');
            const container = document.getElementById('cabinet-data-container');
            
            refreshBtn.disabled = true;
            refreshBtn.textContent = '🔄 Loading...';
            container.innerHTML = '<div class="loading">Loading cabinet data, please wait...</div>';
            
            fetch('/api/cabinet-data')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        cabinetData = data.data;
                        displayCabinetData(data.data, data.statistics);
                        document.getElementById('exportBtn').disabled = false;
                    } else {
                        container.innerHTML = `<div class="error-message">Error: ${data.error}</div>`;
                    }
                })
                .catch(error => {
                    console.error('Error fetching cabinet data:', error);
                    container.innerHTML = `<div class="error-message">Error fetching cabinet data: ${error.message}</div>`;
                })
                .finally(() => {
                    refreshBtn.disabled = false;
                    refreshBtn.textContent = '🔄 Refresh Cabinet Data';
                });
        }
        
        function displayCabinetData(data, stats) {
            // Display statistics
            const statsContainer = document.getElementById('cabinet-stats');
            if (stats) {
                let statsHtml = `
                    <div class="stat-card">
                        <div class="stat-value">${stats.total_nodes}</div>
                        <div class="stat-label">Total Nodes</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.successful_nodes}</div>
                        <div class="stat-label">Connected</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.failed_nodes}</div>
                        <div class="stat-label">Failed</div>
                    </div>
                `;
                
                if (stats.l1_max !== undefined) {
                    statsHtml += `
                        <div class="stat-card">
                            <div class="stat-value">${stats.l1_max}</div>
                            <div class="stat-label">Max L1 Current (A)</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${stats.l2_max}</div>
                            <div class="stat-label">Max L2 Current (A)</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${stats.l3_max}</div>
                            <div class="stat-label">Max L3 Current (A)</div>
                        </div>
                    `;
                }
                
                statsContainer.innerHTML = statsHtml;
                statsContainer.style.display = 'grid';
            }
            
            // Display table
            const container = document.getElementById('cabinet-data-container');
            
            if (!data || data.length === 0) {
                container.innerHTML = '<div class="loading">No cabinet data available</div>';
                return;
            }
            
            let tableHtml = `
                <div class="table-container">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Cabinet</th>
                                <th>IP Address</th>
                                <th>Node</th>
                                <th>Current L1 (A)</th>
                                <th>Current L2 (A)</th>
                                <th>Current L3 (A)</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            
            data.forEach(row => {
                const statusClass = row.status === 'OK' ? 'status-ok' : 'status-error';
                tableHtml += `
                    <tr>
                        <td>${row.cabinet}</td>
                        <td>${row.ip_address}</td>
                        <td>${row.node}</td>
                        <td>${row.current_l1_a !== null ? row.current_l1_a.toFixed(2) : 'N/A'}</td>
                        <td>${row.current_l2_a !== null ? row.current_l2_a.toFixed(2) : 'N/A'}</td>
                        <td>${row.current_l3_a !== null ? row.current_l3_a.toFixed(2) : 'N/A'}</td>
                        <td class="${statusClass}">${row.status}</td>
                    </tr>
                `;
            });
            
            tableHtml += `
                        </tbody>
                    </table>
                </div>
            `;
            
            container.innerHTML = tableHtml;
        }
        
        function exportCabinetData() {
            if (!cabinetData || cabinetData.length === 0) {
                alert('No data to export. Please refresh cabinet data first.');
                return;
            }
            
            // Create CSV content
            let csvContent = "Cabinet,IP Address,Node,Current L1 (A),Current L2 (A),Current L3 (A),Status,Timestamp\\n";
            
            cabinetData.forEach(row => {
                csvContent += `"${row.cabinet}","${row.ip_address}","${row.node}",`;
                csvContent += `"${row.current_l1_a !== null ? row.current_l1_a.toFixed(2) : 'N/A'}",`;
                csvContent += `"${row.current_l2_a !== null ? row.current_l2_a.toFixed(2) : 'N/A'}",`;
                csvContent += `"${row.current_l3_a !== null ? row.current_l3_a.toFixed(2) : 'N/A'}",`;
                csvContent += `"${row.status}","${row.timestamp}"\\n`;
            });
            
            // Create and download file
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `energy_meter_readings_${new Date().toISOString().slice(0,19).replace(/:/g, '-')}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
        
        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            updateReadings();
            
            // Update individual readings every 5 seconds
            setInterval(updateReadings, 5000);
        });
    </script>
</body>
</html>'''
    
    # Write the HTML template
    with open(os.path.join(templates_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    # Start background thread for reading data
    reader_thread = threading.Thread(target=background_reader, daemon=True)
    reader_thread.start()
    
    print("Starting Energy Meter Web Server...")
    print("Open your browser and go to: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    
    # Start the Flask web server
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\nServer stopped by user.")

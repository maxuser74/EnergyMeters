#!/usr/bin/env python3
"""
Energy Meter Web Server
Displays energy meter readings in a web interface with automatic refresh
"""

from flask import Flask, render_template, jsonify, request
from pymodbus.constants import Endian
from pymodbus.client import ModbusTcpClient
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
        self.cabina = '192.168.156.75'
        self.nodo = 8
        self.port = 502
        self.registers = {
            372: "Tensione RMS media su 3 fasi V",
            374: "Corrente di linea L1 A", 
            376: "Corrente di linea L2 A",
            378: "Corrente di linea L3 A",
            390: "Potenza ATTIVA istantanea media RMS Watt"
        }
        
    def read_single_register(self, client, registro):
        """Read a single register and return the float value"""
        try:
            request = client.read_holding_registers(address=registro, count=2, slave=self.nodo)
            
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
            print(f"Error reading register {registro}: {e}")
            return None
    
    def read_all_registers(self):
        """Read all energy meter registers and return results"""
        global latest_readings, last_update_time, connection_status, historical_data
        
        client = ModbusTcpClient(self.cabina, port=self.port)
        
        try:
            # Connect to the device
            connection_result = client.connect()
            if not connection_result:
                connection_status = "Connection Failed"
                print(f"ERROR: Cannot connect to energy meter at {self.cabina}:{self.port}")
                return False
                
            connection_status = "Connected"
            results = {}
            
            # Read each register
            for registro, description in self.registers.items():
                value = self.read_single_register(client, registro)
                if value is not None:
                    results[registro] = {
                        'value': value,
                        'description': description
                    }
            
            # Update global variables
            latest_readings = results
            current_time = datetime.now()
            last_update_time = current_time
            
            # Store historical data for graphs (keep last 50 readings)
            if results:
                data_point = {
                    'timestamp': current_time.isoformat(),
                    'voltage': results.get(372, {}).get('value', 0),
                    'current_l1': results.get(374, {}).get('value', 0),
                    'current_l2': results.get(376, {}).get('value', 0),
                    'current_l3': results.get(378, {}).get('value', 0),
                    'power': results.get(390, {}).get('value', 0)
                }
                historical_data.append(data_point)
                
                # Keep only last 50 readings (about 4 minutes of data)
                if len(historical_data) > 50:
                    historical_data.pop(0)
            
            print(f"Successfully read {len(results)} registers at {last_update_time.strftime('%H:%M:%S')}")
            return True
            
        except Exception as e:
            connection_status = f"Error: {str(e)}"
            print(f"ERROR: {e}")
            return False
            
        finally:
            client.close()

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
    
    # Calculate summary values
    summary = {}
    if latest_readings:
        if 372 in latest_readings:
            summary['voltage'] = latest_readings[372]['value']
        if 374 in latest_readings and 376 in latest_readings and 378 in latest_readings:
            summary['total_current'] = (
                latest_readings[374]['value'] + 
                latest_readings[376]['value'] + 
                latest_readings[378]['value']
            )
        if 390 in latest_readings:
            summary['power'] = latest_readings[390]['value']
    
    # Connection parameters for display
    connection_info = {
        'ip_address': meter_reader.cabina,
        'port': meter_reader.port,
        'device_id': meter_reader.nodo
    }
    
    return jsonify({
        'readings': latest_readings,
        'summary': summary,
        'connection_info': connection_info,
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
    
    # Create the HTML template
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
            max-width: 1200px;
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
        
        .connection-info {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            border-left: 4px solid #667eea;
        }
        
        .connection-params {
            display: flex;
            justify-content: center;
            gap: 30px;
            flex-wrap: wrap;
            margin-top: 10px;
        }
        
        .param-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            min-width: 120px;
        }
        
        .param-label {
            font-size: 0.85em;
            color: #6c757d;
            margin-bottom: 5px;
            text-transform: uppercase;
            font-weight: 600;
        }
        
        .param-value {
            font-size: 1.1em;
            color: #495057;
            font-weight: bold;
            font-family: 'Courier New', monospace;
        }
        
        .status {
            text-align: center;
            margin-bottom: 20px;
            padding: 15px;
            border-radius: 10px;
            font-weight: bold;
        }
        
        .status.connected {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .status.error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
        }
        
        .card h3 {
            margin: 0 0 10px 0;
            color: #495057;
            font-size: 1.1em;
        }
        
        .card .value {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin: 10px 0;
        }
        
        .card .unit {
            color: #6c757d;
            font-size: 1.2em;
        }
        
        .summary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 15px;
            padding: 25px;
            margin-top: 20px;
        }
        
        .summary h2 {
            margin: 0 0 20px 0;
            text-align: center;
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .summary-item {
            text-align: center;
            padding: 15px;
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
        }
        
        .summary-item .label {
            font-size: 0.9em;
            opacity: 0.8;
        }
        
        .summary-item .value {
            font-size: 1.8em;
            font-weight: bold;
            margin-top: 5px;
        }
        
        .last-update {
            text-align: center;
            color: #6c757d;
            margin-top: 20px;
            font-style: italic;
        }
        
        .loading {
            text-align: center;
            color: #667eea;
            font-size: 1.2em;
            margin: 20px 0;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        .loading {
            animation: pulse 2s infinite;
        }
        
        .charts-section {
            margin-top: 40px;
            padding-top: 30px;
            border-top: 3px solid #667eea;
        }
        
        .charts-title {
            text-align: center;
            color: #667eea;
            font-size: 2em;
            margin-bottom: 30px;
        }
        
        .charts-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 30px;
        }
        
        .chart-container {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            border: 1px solid #e9ecef;
        }
        
        .chart-title {
            text-align: center;
            color: #495057;
            font-size: 1.4em;
            margin-bottom: 20px;
            font-weight: 600;
        }
        
        .chart-canvas {
            position: relative;
            height: 300px;
            width: 100%;
        }
        
        @media (min-width: 1200px) {
            .charts-grid {
                grid-template-columns: 1fr 1fr;
            }
        }
        
        .config-section {
            margin-bottom: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            padding: 20px;
            border: 1px solid #dee2e6;
        }
        
        .config-title {
            color: #495057;
            font-size: 1.2em;
            margin-bottom: 15px;
            font-weight: 600;
        }
        
        .config-form {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            align-items: end;
        }
        
        .form-group {
            display: flex;
            flex-direction: column;
        }
        
        .form-group label {
            font-size: 0.9em;
            color: #6c757d;
            margin-bottom: 5px;
            font-weight: 600;
        }
        
        .form-group input {
            padding: 8px 12px;
            border: 1px solid #ced4da;
            border-radius: 5px;
            font-size: 1em;
            font-family: 'Courier New', monospace;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.25);
        }
        
        .btn {
            padding: 10px 20px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            transition: background-color 0.3s ease;
        }
        
        .btn:hover {
            background: #5a6fd8;
        }
        
        .btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
        }
        
        .config-message {
            margin-top: 10px;
            padding: 10px;
            border-radius: 5px;
            display: none;
        }
        
        .config-message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .config-message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
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
        
        <!-- Configuration Section -->
        <div class="config-section">
            <h3 class="config-title">⚙️ Connection Configuration</h3>
            <form class="config-form" id="configForm">
                <div class="form-group">
                    <label for="ipAddress">IP Address (Cabina)</label>
                    <input type="text" id="ipAddress" name="ipAddress" placeholder="192.168.156.75" pattern="^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$">
                </div>
                <div class="form-group">
                    <label for="port">Port</label>
                    <input type="number" id="port" name="port" placeholder="502" min="1" max="65535">
                </div>
                <div class="form-group">
                    <label for="deviceId">Device ID (Nodo)</label>
                    <input type="number" id="deviceId" name="deviceId" placeholder="8" min="1" max="255">
                </div>
                <div class="form-group">
                    <button type="submit" class="btn" id="updateConfigBtn">Update Configuration</button>
                </div>
            </form>
            <div id="configMessage" class="config-message"></div>
        </div>
        
        <div id="status" class="status">
            <div class="loading">Loading...</div>
        </div>
        
        <div id="readings-container">
            <div class="loading">Fetching energy meter data...</div>
        </div>
        
        <div id="last-update" class="last-update"></div>
        
        <!-- Charts Section -->
        <div class="charts-section">
            <h2 class="charts-title">📊 Real-time Trends</h2>
            <div class="charts-grid">
                <!-- Phase Currents Chart -->
                <div class="chart-container">
                    <h3 class="chart-title">🔌 Phase Currents (L1, L2, L3)</h3>
                    <div class="chart-canvas">
                        <canvas id="currentChart"></canvas>
                    </div>
                </div>
                
                <!-- Voltage Chart -->
                <div class="chart-container">
                    <h3 class="chart-title">⚡ System Voltage</h3>
                    <div class="chart-canvas">
                        <canvas id="voltageChart"></canvas>
                    </div>
                </div>
                
                <!-- Power Chart -->
                <div class="chart-container" style="grid-column: 1 / -1;">
                    <h3 class="chart-title">⚡ Active Power Consumption</h3>
                    <div class="chart-canvas">
                        <canvas id="powerChart"></canvas>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let lastUpdateTime = null;
        let currentChart, voltageChart, powerChart;
        
        // Initialize charts
        function initializeCharts() {
            // Phase Currents Chart
            const currentCtx = document.getElementById('currentChart').getContext('2d');
            currentChart = new Chart(currentCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'L1 Current (A)',
                            data: [],
                            borderColor: '#ff6384',
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            borderWidth: 2,
                            fill: false,
                            tension: 0.4
                        },
                        {
                            label: 'L2 Current (A)',
                            data: [],
                            borderColor: '#36a2eb',
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            borderWidth: 2,
                            fill: false,
                            tension: 0.4
                        },
                        {
                            label: 'L3 Current (A)',
                            data: [],
                            borderColor: '#4bc0c0',
                            backgroundColor: 'rgba(75, 192, 192, 0.1)',
                            borderWidth: 2,
                            fill: false,
                            tension: 0.4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Current (A)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    }
                }
            });
            
            // Voltage Chart
            const voltageCtx = document.getElementById('voltageChart').getContext('2d');
            voltageChart = new Chart(voltageCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Voltage (V)',
                        data: [],
                        borderColor: '#ffce56',
                        backgroundColor: 'rgba(255, 206, 86, 0.1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: false,
                            title: {
                                display: true,
                                text: 'Voltage (V)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    }
                }
            });
            
            // Power Chart
            const powerCtx = document.getElementById('powerChart').getContext('2d');
            powerChart = new Chart(powerCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Active Power (W)',
                        data: [],
                        borderColor: '#9966ff',
                        backgroundColor: 'rgba(153, 102, 255, 0.1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Power (W)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    }
                }
            });
        }
        
        function updateReadings() {
            fetch('/api/readings')
                .then(response => response.json())
                .then(data => {
                    updateStatus(data.connection_status);
                    updateConnectionInfo(data.connection_info);
                    displayReadings(data.readings, data.summary);
                    updateLastUpdateTime(data.last_update);
                    updateCharts(data.historical_data);
                })
                .catch(error => {
                    console.error('Error fetching readings:', error);
                    updateStatus('Connection Error');
                });
        }
        
        function updateStatus(status) {
            const statusEl = document.getElementById('status');
            statusEl.innerHTML = `<strong>Status:</strong> ${status}`;
            
            if (status === 'Connected') {
                statusEl.className = 'status connected';
            } else {
                statusEl.className = 'status error';
            }
        }
        
        function updateConnectionInfo(connectionInfo) {
            const connectionEl = document.getElementById('connection-info');
            if (connectionInfo) {
                connectionEl.innerHTML = `
                    <div style="text-align: center; color: #495057; margin-bottom: 10px;">
                        <strong>📡 Connection Parameters</strong>
                    </div>
                    <div class="connection-params">
                        <div class="param-item">
                            <div class="param-label">IP Address (Cabina)</div>
                            <div class="param-value">${connectionInfo.ip_address}</div>
                        </div>
                        <div class="param-item">
                            <div class="param-label">Port</div>
                            <div class="param-value">${connectionInfo.port}</div>
                        </div>
                        <div class="param-item">
                            <div class="param-label">Device ID (Nodo)</div>
                            <div class="param-value">${connectionInfo.device_id}</div>
                        </div>
                    </div>
                `;
            }
        }
        
        function displayReadings(readings, summary) {
            const container = document.getElementById('readings-container');
            
            if (!readings || Object.keys(readings).length === 0) {
                container.innerHTML = '<div class="loading">No data available</div>';
                return;
            }
            
            // Create individual register cards
            let html = '<div class="grid">';
            
            const registerNames = {
                372: { name: 'Voltage (3-phase avg)', unit: 'V', icon: '⚡' },
                374: { name: 'Current L1', unit: 'A', icon: '🔌' },
                376: { name: 'Current L2', unit: 'A', icon: '🔌' },
                378: { name: 'Current L3', unit: 'A', icon: '🔌' },
                390: { name: 'Active Power', unit: 'W', icon: '⚡' }
            };
            
            Object.keys(readings).sort((a, b) => parseInt(a) - parseInt(b)).forEach(register => {
                const reading = readings[register];
                const info = registerNames[register] || { name: `Register ${register}`, unit: '', icon: '📊' };
                
                html += `
                    <div class="card">
                        <h3>${info.icon} ${info.name}</h3>
                        <div class="value">${reading.value.toFixed(2)}</div>
                        <div class="unit">${info.unit}</div>
                    </div>
                `;
            });
            
            html += '</div>';
            
            // Add summary section
            if (summary && Object.keys(summary).length > 0) {
                html += `
                    <div class="summary">
                        <h2>📊 Summary</h2>
                        <div class="summary-grid">
                `;
                
                if (summary.voltage !== undefined) {
                    html += `
                        <div class="summary-item">
                            <div class="label">System Voltage</div>
                            <div class="value">${summary.voltage.toFixed(1)} V</div>
                        </div>
                    `;
                }
                
                if (summary.total_current !== undefined) {
                    html += `
                        <div class="summary-item">
                            <div class="label">Total Current</div>
                            <div class="value">${summary.total_current.toFixed(2)} A</div>
                        </div>
                    `;
                }
                
                if (summary.power !== undefined) {
                    html += `
                        <div class="summary-item">
                            <div class="label">Active Power</div>
                            <div class="value">${summary.power.toFixed(1)} W</div>
                        </div>
                    `;
                }
                
                html += '</div></div>';
            }
            
            container.innerHTML = html;
        }
        
        function updateLastUpdateTime(updateTime) {
            const lastUpdateEl = document.getElementById('last-update');
            if (updateTime) {
                const date = new Date(updateTime);
                lastUpdateEl.innerHTML = `Last updated: ${date.toLocaleString()}`;
            }
        }
        
        function updateCharts(historicalData) {
            if (!historicalData || historicalData.length === 0) return;
            
            // Prepare data for charts
            const labels = historicalData.map(point => {
                const date = new Date(point.timestamp);
                return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
            });
            
            const currentL1Data = historicalData.map(point => point.current_l1);
            const currentL2Data = historicalData.map(point => point.current_l2);
            const currentL3Data = historicalData.map(point => point.current_l3);
            const voltageData = historicalData.map(point => point.voltage);
            const powerData = historicalData.map(point => point.power);
            
            // Update Current Chart
            if (currentChart) {
                currentChart.data.labels = labels;
                currentChart.data.datasets[0].data = currentL1Data;
                currentChart.data.datasets[1].data = currentL2Data;
                currentChart.data.datasets[2].data = currentL3Data;
                currentChart.update('none'); // No animation for real-time updates
            }
            
            // Update Voltage Chart
            if (voltageChart) {
                voltageChart.data.labels = labels;
                voltageChart.data.datasets[0].data = voltageData;
                voltageChart.update('none');
            }
            
            // Update Power Chart
            if (powerChart) {
                powerChart.data.labels = labels;
                powerChart.data.datasets[0].data = powerData;
                powerChart.update('none');
            }
        }
        
        function loadConfiguration() {
            fetch('/api/config')
                .then(response => response.json())
                .then(data => {
                    if (data.config) {
                        document.getElementById('ipAddress').value = data.config.ip_address;
                        document.getElementById('port').value = data.config.port;
                        document.getElementById('deviceId').value = data.config.device_id;
                    }
                })
                .catch(error => {
                    console.error('Error loading configuration:', error);
                });
        }
        
        function updateConfiguration(event) {
            event.preventDefault();
            
            const formData = new FormData(event.target);
            const config = {
                ip_address: formData.get('ipAddress'),
                port: parseInt(formData.get('port')),
                device_id: parseInt(formData.get('deviceId'))
            };
            
            // Validate inputs
            if (!config.ip_address || !config.port || !config.device_id) {
                showConfigMessage('Please fill in all fields', 'error');
                return;
            }
            
            // Validate IP address format
            const ipRegex = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/;
            if (!ipRegex.test(config.ip_address)) {
                showConfigMessage('Please enter a valid IP address', 'error');
                return;
            }
            
            // Validate port range
            if (config.port < 1 || config.port > 65535) {
                showConfigMessage('Port must be between 1 and 65535', 'error');
                return;
            }
            
            // Validate device ID range
            if (config.device_id < 1 || config.device_id > 255) {
                showConfigMessage('Device ID must be between 1 and 255', 'error');
                return;
            }
            
            // Disable button during update
            const updateBtn = document.getElementById('updateConfigBtn');
            updateBtn.disabled = true;
            updateBtn.textContent = 'Updating...';
            
            fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(config)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showConfigMessage(data.message, 'success');
                    // Clear charts when configuration changes
                    if (currentChart) currentChart.data.labels = [];
                    if (currentChart) currentChart.data.datasets.forEach(dataset => dataset.data = []);
                    if (voltageChart) voltageChart.data.labels = [];
                    if (voltageChart) voltageChart.data.datasets[0].data = [];
                    if (powerChart) powerChart.data.labels = [];
                    if (powerChart) powerChart.data.datasets[0].data = [];
                    
                    // Update charts
                    if (currentChart) currentChart.update();
                    if (voltageChart) voltageChart.update();
                    if (powerChart) powerChart.update();
                } else {
                    showConfigMessage(data.message, 'error');
                }
            })
            .catch(error => {
                console.error('Error updating configuration:', error);
                showConfigMessage('Error updating configuration', 'error');
            })
            .finally(() => {
                // Re-enable button
                updateBtn.disabled = false;
                updateBtn.textContent = 'Update Configuration';
            });
        }
        
        function showConfigMessage(message, type) {
            const messageEl = document.getElementById('configMessage');
            messageEl.textContent = message;
            messageEl.className = `config-message ${type}`;
            messageEl.style.display = 'block';
            
            // Hide message after 5 seconds
            setTimeout(() => {
                messageEl.style.display = 'none';
            }, 5000);
        }
        
        // Initial load
        document.addEventListener('DOMContentLoaded', function() {
            initializeCharts();
            loadConfiguration();
            updateReadings();
            
            // Set up configuration form handler
            document.getElementById('configForm').addEventListener('submit', updateConfiguration);
            
            // Update every 2 seconds (readings are updated every 5 seconds on server)
            setInterval(updateReadings, 2000);
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

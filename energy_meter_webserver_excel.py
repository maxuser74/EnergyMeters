import os
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
# Global variables to store the latest readings
MODE = 'PRODUCTION'  # Default
if os.path.exists('env'):
    with open('env', 'r') as f:
        for line in f:
            if line.strip().startswith('MODE'):
                MODE = line.strip().split('=')[1].strip().upper()

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
                    category = str(row['Type']).strip().lower()
                    category = category.replace(' ', '_').replace('/', '_')
                    if category == 'currents':
                        category = 'current'
                    elif category == 'voltages':
                        category = 'voltage'
                    elif category == 'power_factors':
                        category = 'power_factor'
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

        # In dummy mode generate simulated data without connecting
        if MODE == 'DUMMY' or 'dummy' in utility_id.lower():
            import random
            v1 = round(random.uniform(398, 403), 1)
            v2 = round(random.uniform(398, 403), 1)
            v3 = round(random.uniform(398, 403), 1)
            c1 = round(random.uniform(195, 205), 1)
            c2 = round(random.uniform(195, 205), 1)
            c3 = round(random.uniform(195, 205), 1)
            pf1 = round(random.uniform(0.88, 0.93), 2)
            pf2 = round(random.uniform(0.88, 0.93), 2)
            pf3 = round(random.uniform(0.88, 0.93), 2)
            p_tot_kw = round((v1 * c1 * pf1 + v2 * c2 * pf2 + v3 * c3 * pf3) / 1000, 2)

            return {
                'id': utility_id,
                'name': utility_name,
                'cabinet': utility['cabinet'],
                'node': node_id,
                'ip_address': ip_address,
                'status': 'OK',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'registers': {
                    'voltage_L1': {'description': 'Voltage L1', 'value': v1, 'unit': 'V', 'category': 'voltage', 'status': 'OK'},
                    'voltage_L2': {'description': 'Voltage L2', 'value': v2, 'unit': 'V', 'category': 'voltage', 'status': 'OK'},
                    'voltage_L3': {'description': 'Voltage L3', 'value': v3, 'unit': 'V', 'category': 'voltage', 'status': 'OK'},
                    'current_L1': {'description': 'Current L1', 'value': c1, 'unit': 'A', 'category': 'current', 'status': 'OK'},
                    'current_L2': {'description': 'Current L2', 'value': c2, 'unit': 'A', 'category': 'current', 'status': 'OK'},
                    'current_L3': {'description': 'Current L3', 'value': c3, 'unit': 'A', 'category': 'current', 'status': 'OK'},
                    'power_factor_L1': {'description': 'Power Factor L1', 'value': pf1, 'unit': '', 'category': 'power_factor', 'status': 'OK'},
                    'power_factor_L2': {'description': 'Power Factor L2', 'value': pf2, 'unit': '', 'category': 'power_factor', 'status': 'OK'},
                    'power_factor_L3': {'description': 'Power Factor L3', 'value': pf3, 'unit': '', 'category': 'power_factor', 'status': 'OK'},
                    'active_power': {'description': 'Active Power', 'value': p_tot_kw, 'unit': 'kW', 'category': 'power', 'status': 'OK'}
                }
            }

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
        """Read all utilities and update global readings. If none are available, add a dummy utility with example values. In DUMMY mode, only use the dummy."""
        global latest_readings, last_update_time, connection_status, utilities_config, MODE

        if MODE == 'DUMMY':
            import random
            print("DUMMY MODE: Only simulated data will be used.")
            dummy_id = 'dummy_cabinet1_node1'
            # Generate random but realistic values for each refresh
            v1 = round(random.uniform(398, 403), 1)
            v2 = round(random.uniform(398, 403), 1)
            v3 = round(random.uniform(398, 403), 1)
            c1 = round(random.uniform(195, 205), 1)
            c2 = round(random.uniform(195, 205), 1)
            c3 = round(random.uniform(195, 205), 1)
            pf1 = round(random.uniform(0.88, 0.93), 2)
            pf2 = round(random.uniform(0.88, 0.93), 2)
            pf3 = round(random.uniform(0.88, 0.93), 2)
            # Active power per phase: P = V * I * PF
            p1 = v1 * c1 * pf1
            p2 = v2 * c2 * pf2
            p3 = v3 * c3 * pf3
            p_tot_kw = round((p1 + p2 + p3) / 1000, 2)  # kW
            all_readings = {
                dummy_id: {
                    'id': dummy_id,
                    'name': 'DEMO DUMMY MACHINE',
                    'cabinet': 1,
                    'node': 1,
                    'ip_address': '127.0.0.1',
                    'status': 'OK',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'registers': {
                        'voltage_L1': {
                            'description': 'Voltage L1',
                            'value': v1,
                            'unit': 'V',
                            'category': 'voltage',
                            'status': 'OK'
                        },
                        'voltage_L2': {
                            'description': 'Voltage L2',
                            'value': v2,
                            'unit': 'V',
                            'category': 'voltage',
                            'status': 'OK'
                        },
                        'voltage_L3': {
                            'description': 'Voltage L3',
                            'value': v3,
                            'unit': 'V',
                            'category': 'voltage',
                            'status': 'OK'
                        },
                        'current_L1': {
                            'description': 'Current L1',
                            'value': c1,
                            'unit': 'A',
                            'category': 'current',
                            'status': 'OK'
                        },
                        'current_L2': {
                            'description': 'Current L2',
                            'value': c2,
                            'unit': 'A',
                            'category': 'current',
                            'status': 'OK'
                        },
                        'current_L3': {
                            'description': 'Current L3',
                            'value': c3,
                            'unit': 'A',
                            'category': 'current',
                            'status': 'OK'
                        },
                        'power_factor_L1': {
                            'description': 'Power Factor L1',
                            'value': pf1,
                            'unit': '',
                            'category': 'power_factor',
                            'status': 'OK'
                        },
                        'power_factor_L2': {
                            'description': 'Power Factor L2',
                            'value': pf2,
                            'unit': '',
                            'category': 'power_factor',
                            'status': 'OK'
                        },
                        'power_factor_L3': {
                            'description': 'Power Factor L3',
                            'value': pf3,
                            'unit': '',
                            'category': 'power_factor',
                            'status': 'OK'
                        },
                        'active_power': {
                            'description': 'Active Power',
                            'value': p_tot_kw,
                            'unit': 'kW',
                            # Use the general power category so the badge
                            # styling matches existing power metrics
                            'category': 'power',
                            'status': 'OK'
                        }
                    }
                }
            }
            utilities_config = [{
                'id': dummy_id,
                'cabinet': 1,
                'node': 1,
                'utility_name': 'DEMO DUMMY MACHINE',
                'ip_address': '127.0.0.1',
                'port': 502
            }]
            connection_status = 'DEMO MODE: Dummy machine shown'
            latest_readings = all_readings
            last_update_time = datetime.now()
            print("Completed reading: 1/1 utilities successful (dummy)")
            return all_readings

        print(f"Reading all {len(utilities_config)} utilities...")

        all_readings = {}
        successful_count = 0

        for utility in utilities_config:
            utility_data = self.read_single_utility(utility)
            all_readings[utility_data['id']] = utility_data
            if utility_data['status'] in ['OK', 'PARTIAL']:
                successful_count += 1

        # Se nessuna utility reale è disponibile, aggiungi una dummy anche a utilities_config
        if not all_readings or all(v['status'] != 'OK' for v in all_readings.values()):
            print("No real readings available, adding dummy utility for demo.")
            dummy_id = 'dummy_cabinet1_node1'
            all_readings[dummy_id] = {
                'id': dummy_id,
                'name': 'DEMO DUMMY MACHINE',
                'cabinet': 1,
                'node': 1,
                'ip_address': '127.0.0.1',
                'status': 'OK',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'registers': {
                    'voltage_L1': {
                        'description': 'Voltage L1',
                        'value': 400.2,
                        'unit': 'V',
                        'category': 'voltage',
                        'status': 'OK'
                    },
                    'voltage_L2': {
                        'description': 'Voltage L2',
                        'value': 399.8,
                        'unit': 'V',
                        'category': 'voltage',
                        'status': 'OK'
                    },
                    'voltage_L3': {
                        'description': 'Voltage L3',
                        'value': 401.1,
                        'unit': 'V',
                        'category': 'voltage',
                        'status': 'OK'
                    },
                    'current_L1': {
                        'description': 'Current L1',
                        'value': 200.5,
                        'unit': 'A',
                        'category': 'current',
                        'status': 'OK'
                    },
                    'current_L2': {
                        'description': 'Current L2',
                        'value': 198.7,
                        'unit': 'A',
                        'category': 'current',
                        'status': 'OK'
                    },
                    'current_L3': {
                        'description': 'Current L3',
                        'value': 201.2,
                        'unit': 'A',
                        'category': 'current',
                        'status': 'OK'
                    },
                    'power_factor_L1': {
                        'description': 'Power Factor L1',
                        'value': 0.91,
                        'unit': '',
                        'category': 'power_factor',
                        'status': 'OK'
                    },
                    'power_factor_L2': {
                        'description': 'Power Factor L2',
                        'value': 0.89,
                        'unit': '',
                        'category': 'power_factor',
                        'status': 'OK'
                    },
                    'power_factor_L3': {
                        'description': 'Power Factor L3',
                        'value': 0.92,
                        'unit': '',
                        'category': 'power_factor',
                        'status': 'OK'
                    }
                }
            }
            # Aggiorna anche utilities_config per la dashboard, dummy in alto
            utilities_config = [{
                'id': dummy_id,
                'cabinet': 1,
                'node': 1,
                'utility_name': 'DEMO DUMMY MACHINE',
                'ip_address': '127.0.0.1',
                'port': 502
            }]
            connection_status = 'DEMO MODE: Dummy machine shown'
        elif successful_count > 0:
            connection_status = f"Connected ({successful_count}/{len(utilities_config)} utilities)"
        else:
            connection_status = "All connections failed"

        # Update global variables
        latest_readings = all_readings
        last_update_time = datetime.now()

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
        # Reload configuration from Excel files
        print("Reloading configuration from Excel files...")
        energy_reader.load_configuration()
        
        # Update global variables with new configuration
        utilities_config = energy_reader.load_utilities_from_excel()
        registers_config = energy_reader.load_registers_from_excel()
        
        print(f"Configuration reloaded: {len(utilities_config)} utilities, {len(registers_config)} registers")
        
        # Read all utilities with new configuration
        readings = energy_reader.read_all_utilities()
        
        return jsonify({
            'success': True,
            'readings': readings,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': f'Configuration reloaded: {len(utilities_config)} utilities, {len(registers_config)} registers',
            'utilities_count': len(utilities_config),
            'registers_count': len(registers_config)
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
    """Create the HTML template for the dashboard.
    If the template already exists, leave it untouched so custom
    modifications are preserved."""

    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)

    template_path = 'templates/energy_dashboard.html'
    if os.path.exists(template_path):
        print("HTML template exists, skipping creation")
        return

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
        }

        .monitor-status {
            font-size: 0.8em;
            color: #e74c3c;
            font-weight: bold;
            margin-top: 5px;
        }

        .charts-container {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }

        .charts-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 15px;
        }

        .chart-section {
            background: white;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }

        .chart-title {
            font-weight: bold;
            margin-bottom: 10px;
            padding: 8px 12px;
            border-radius: 5px;
            text-align: center;
            color: white;
        }

        .chart-title.voltage {
            background: linear-gradient(135deg, #e74c3c, #c0392b);
        }

        .chart-title.current {
            background: linear-gradient(135deg, #3498db, #2980b9);
        }

        .chart-canvas {
            height: 200px;
        }

        @media (max-width: 768px) {
            .charts-grid {
                grid-template-columns: 1fr;
            }
        }

        .registers-container {
            padding: 20px;
        }

        .readings-section {
            margin-bottom: 25px;
        }

        .section-title {
            font-size: 1.1em;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 15px;
            padding: 8px 12px;
            border-radius: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .voltage-section .section-title {
            background: linear-gradient(135deg, #e74c3c, #c0392b);
            color: white;
        }

        .current-section .section-title {
            background: linear-gradient(135deg, #3498db, #2980b9);
            color: white;
        }

        .power-section .section-title {
            background: linear-gradient(135deg, #27ae60, #229954);
            color: white;
        }

        .power_factor-section .section-title {
            background: linear-gradient(135deg, #f1c40f, #f39c12);
            color: white;
        }

        .other-section .section-title {
            background: linear-gradient(135deg, #9b59b6, #8e44ad);
            color: white;
        }

        .registers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 10px;
        }

        .registers-grid.voltage-grid, .registers-grid.current-grid, .registers-grid.power_factor-grid {
            grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
            gap: 6px;
        }

        .register-badge {
            background: white;
            border: 2px solid #e0e0e0;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            transition: all 0.3s ease;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }

        .register-badge.voltage, .register-badge.current, .register-badge.power_factor {
            padding: 5px;
        }

        .register-name {
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 6px;
            font-size: 0.7em;
            line-height: 1.1;
            min-height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .register-badge.voltage .register-name, .register-badge.current .register-name, .register-badge.power_factor .register-name {
            font-size: 0.65em;
            min-height: 24px;
            margin-bottom: 4px;
        }

        .register-value {
            font-size: 1.4em;
            font-weight: bold;
            margin-bottom: 3px;
        }

        .register-badge.voltage .register-value, .register-badge.current .register-value, .register-badge.power_factor .register-value {
            font-size: 1.1em;
            margin-bottom: 1px;
        }


        .register-badge.voltage {
            border-color: #e74c3c;
            background: linear-gradient(135deg, #fff5f5, #ffeaea);
        }

        .register-badge.current {
            border-color: #3498db;
            background: linear-gradient(135deg, #f0f8ff, #e6f3ff);
        }

        .register-badge.power {
            border-color: #27ae60;
            background: linear-gradient(135deg, #f0fff4, #e6ffed);
        }

        .register-badge.power_factor {
            border-color: #8e44ad;
            background: linear-gradient(135deg, #f5e6ff, #f3e8ff);
        }

        .register-badge.other {
            border-color: #9b59b6;
            background: linear-gradient(135deg, #faf5ff, #f3e8ff);
        }

        /* Dynamic badge color for new categories (fallback: HSL by category name hash) */
        [class*="register-badge."], .register-badge {
            /* fallback, will be overridden below */
        }
        /* Example for a few possible new categories */
        .register-badge.frequency {
            border-color: #f39c12;
            background: linear-gradient(135deg, #fffbe6, #fff3cd);
        }
        .register-badge.temperature {
            border-color: #16a085;
            background: linear-gradient(135deg, #e6fffa, #e0f7fa);
        }
        /* Generic fallback for any unknown category: use HSL based on category name hash */
        .register-badge[data-category] {
            /* JS will set style if not matched above */
        }

        .register-badge.error {
            border-color: #e74c3c;
            background: #fdf2f2;
        }

        .voltage-current-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 25px;
        }

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

            .registers-grid {
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
            .registers-grid {
                grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
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

        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            border: 1px solid #c3e6cb;
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

        // Chart configuration
        const chartConfig = {
            voltage: {
                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                borderColor: 'rgba(231, 76, 60, 1)',
                pointBackgroundColor: 'rgba(231, 76, 60, 1)'
            },
            current: {
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                borderColor: 'rgba(52, 152, 219, 1)',
                pointBackgroundColor: 'rgba(52, 152, 219, 1)'
            }
        };

        function initializeCharts(utilityId) {
            // Initialize chart data storage for this utility
            if (!chartData[utilityId]) {
                chartData[utilityId] = {
                    voltage: { labels: [], datasets: [] },
                    current: { labels: [], datasets: [] }
                };
            }

            // Initialize chart instances
            if (!chartInstances[utilityId]) {
                chartInstances[utilityId] = { voltage: null, current: null };
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
        }

        function getChartOptions(title) {
            return {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    title: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        display: true,
                        title: {
                            display: true,
                            text: 'Time'
                        }
                    },
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: title
                        }
                    }
                },
                elements: {
                    point: {
                        radius: 2
                    },
                    line: {
                        tension: 0.1
                    }
                }
            };
        }

        function clearCharts(utilityId) {
            if (chartData[utilityId]) {
                chartData[utilityId].voltage = { labels: [], datasets: [] };
                chartData[utilityId].current = { labels: [], datasets: [] };
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
            }
        }

        function updateCharts(utilityId, utilityData) {
            if (!chartData[utilityId] || !utilityData.registers) return;

            // Check if chart instances exist
            if (!chartInstances[utilityId] || 
                !chartInstances[utilityId].voltage || 
                !chartInstances[utilityId].current) {
                console.log(`Chart instances missing for ${utilityId}, skipping update`);
                return;
            }

            const now = new Date().toLocaleTimeString();
            const maxDataPoints = 50; // Keep last 50 data points

            // Prepare voltage and current data
            const voltageData = {};
            const currentData = {};

            // Extract voltage and current values
            for (const [regKey, regData] of Object.entries(utilityData.registers)) {
                const description = regData.description.toLowerCase();
                const unit = (regData.unit || '').toLowerCase();
                const value = parseFloat(regData.value);

                if (!isNaN(value)) {
                    if (description.includes('voltage') || description.includes('tensione') || unit === 'v') {
                        voltageData[regData.description] = value;
                    } else if (description.includes('current') || description.includes('corrente') || unit === 'a') {
                        currentData[regData.description] = value;
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
                    if (!chartData[utilityId].voltage.datasets[index]) {
                        chartData[utilityId].voltage.datasets[index] = {
                            label: description,
                            data: [],
                            ...chartConfig.voltage,
                            borderColor: `hsl(${index * 30}, 70%, 50%)`,
                            backgroundColor: `hsla(${index * 30}, 70%, 50%, 0.1)`
                        };
                    }
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
                    if (!chartData[utilityId].current.datasets[index]) {
                        chartData[utilityId].current.datasets[index] = {
                            label: description,
                            data: [],
                            ...chartConfig.current,
                            borderColor: `hsl(${200 + index * 30}, 70%, 50%)`,
                            backgroundColor: `hsla(${200 + index * 30}, 70%, 50%, 0.1)`
                        };
                    }
                    chartData[utilityId].current.datasets[index].data.push(value);
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
            
            // Check for utilities that no longer exist in the new configuration
            const currentUtilityIds = Object.keys(data.readings);
            const monitoredUtilityIds = Object.keys(monitoringIntervals);
            
            // Stop monitoring for utilities that no longer exist
            monitoredUtilityIds.forEach(utilityId => {
                if (!currentUtilityIds.includes(utilityId)) {
                    console.log(`Stopping monitoring for removed utility: ${utilityId}`);
                    clearInterval(monitoringIntervals[utilityId]);
                    delete monitoringIntervals[utilityId];
                }
            });
            
            let html = '';
            for (const [utilityId, utilityData] of Object.entries(data.readings)) {
                html += createUtilityCard(utilityId, utilityData);
            }
            
            grid.innerHTML = html;
            
            // Update monitoring count
            updateMonitoringCount();
        }

        function createUtilityCard(utilityId, utilityData) {
            const statusClass = getStatusClass(utilityData.status);
            const isMonitoring = monitoringIntervals.hasOwnProperty(utilityId);
            let registersHtml = '';
            if (utilityData.registers && Object.keys(utilityData.registers).length > 0) {
                // Dynamically categorize registers by their category field
                const categories = {};
                for (const [regKey, regData] of Object.entries(utilityData.registers)) {
                    let cat = regData.category || 'other';
                    if (!categories[cat]) categories[cat] = [];
                    categories[cat].push({key: regKey, data: regData});
                }
                // Sort categories using register 'Type' values
                const mainOrder = ['voltage', 'current', 'power', 'power_factor'];
                const allCats = Object.keys(categories);
                const sortedCats = [
                    ...mainOrder.filter(c => allCats.includes(c)),
                    ...allCats.filter(c => !mainOrder.includes(c)).sort()
                ];
                // Responsive row: try to fit as many as possible on one row, wrap if needed
                registersHtml = '<div class="registers-container">';
                registersHtml += '<div class="voltage-current-row">';
                let rowCount = 0;
                let rowOpen = false;
                let maxPerRow = 3; // Adjust for layout, can be made dynamic
                sortedCats.forEach((cat, idx) => {
                    // Section title and icon
                    let icon = '';
                    if (cat === 'voltage') icon = '⚡';
                    else if (cat === 'current') icon = '🔌';
                    else if (cat === 'power') icon = '🔋';
                    else if (cat === 'power_factor') icon = '📐';
                    else icon = '📊';
                    // Section CSS class
                    let sectionClass = `${cat}-section`;
                    // Grid class
                    let gridClass = (cat === 'voltage' || cat === 'current' || cat === 'power_factor') ? `${cat}-grid` : '';
                    // Badge color class is the category name
                    registersHtml += `
                        <div class="readings-section ${sectionClass}">
                            <div class="section-title">${icon} ${cat.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())} Readings</div>
                            <div class="registers-grid ${gridClass}">
                    `;
                    for (const reg of categories[cat]) {
                        registersHtml += createRegisterBadge(reg.data, cat);
                    }
                    registersHtml += '</div></div>';
                    rowCount++;
                    // If more than maxPerRow, close row and start new
                    if ((rowCount % maxPerRow === 0) && (idx < sortedCats.length - 1)) {
                        registersHtml += '</div><div class="voltage-current-row">';
                    }
                });
                registersHtml += '</div>';
                registersHtml += '</div>';
                // Add charts section if monitoring is active
                if (isMonitoring) {
                    registersHtml += `
                        <div class="charts-container" id="charts-${utilityId}">
                            <div style="text-align: center; font-weight: bold; margin-bottom: 10px;">
                                📈 Real-time Monitoring Charts
                            </div>
                            <div class="charts-grid">
                                <div class="chart-section">
                                    <div class="chart-title voltage">⚡ Voltage</div>
                                    <div class="chart-canvas">
                                        <canvas id="voltage-chart-${utilityId}"></canvas>
                                    </div>
                                </div>
                                <div class="chart-section">
                                    <div class="chart-title current">🔌 Current</div>
                                    <div class="chart-canvas">
                                        <canvas id="current-chart-${utilityId}"></canvas>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
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
            let dataAttr = '';
            if (regData.status === 'OK' && !['voltage','current','power','power_factor','other'].includes(category)) {
                dataAttr = `data-category="${category}"`;
            }
            // Show the type/category in the badge for clarity
            let typeLabel = '';
            if (regData.category && regData.category !== category) {
                typeLabel = `<div class='register-type'>${regData.category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</div>`;
            }
            return `
                <div class="register-badge ${badgeClass}" ${dataAttr}>
                    ${typeLabel}
                    <div class="register-name">${regData.description}</div>
                    <div class="register-value ${valueClass}">
                        ${regData.value}
                    </div>
                    <div class="register-unit">${regData.unit || ''}</div>
                </div>
            `;
        }

        // Dynamic coloring for unknown categories using HSL hash
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(() => {
                document.querySelectorAll('.register-badge[data-category]').forEach(badge => {
                    const cat = badge.getAttribute('data-category');
                    if (!badge.classList.contains('frequency') && !badge.classList.contains('temperature') && !badge.classList.contains('power_factor')) {
                        // Hash category name to HSL color
                        let hash = 0;
                        for (let i = 0; i < cat.length; i++) hash = cat.charCodeAt(i) + ((hash << 5) - hash);
                        const hue = Math.abs(hash) % 360;
                        badge.style.borderColor = `hsl(${hue},70%,50%)`;
                        badge.style.background = `linear-gradient(135deg, hsl(${hue},100%,98%), hsl(${hue},100%,92%))`;
                    }
                });
            }, 100);
        });

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
                        document.getElementById('utilitiesCount').textContent = 
                            `Utilities: ${data.utilities_count} | Registers: ${data.registers_count}`;
                    }
                    
                    // Show configuration reload message if provided
                    if (data.message) {
                        console.log('Configuration reloaded:', data.message);
                        showSuccess(data.message);
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
                                    const nameElement = badge.querySelector('.register-name');
                                    if (nameElement && nameElement.textContent.trim() === regData.description) {
                                        const valueElement = badge.querySelector('.register-value');
                                        const unitElement = badge.querySelector('.register-unit');
                                        
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

                            // Ensure charts are still present and functioning
                            const chartsContainer = document.getElementById(`charts-${utilityId}`);
                            if (!chartsContainer) {
                                // Charts container is missing, recreate it
                                console.log(`Charts missing for ${utilityId}, recreating...`);
                                const registersContainer = utilityCard.querySelector('.registers-container');
                                if (registersContainer) {
                                    const chartsHtml = `
                                        <div class="charts-container" id="charts-${utilityId}">
                                            <div style="text-align: center; font-weight: bold; margin-bottom: 10px;">
                                                📈 Real-time Monitoring Charts
                                            </div>
                                            <div class="charts-grid">
                                                <div class="chart-section">
                                                    <div class="chart-title voltage">⚡ Voltage</div>
                                                    <div class="chart-canvas">
                                                        <canvas id="voltage-chart-${utilityId}"></canvas>
                                                    </div>
                                                </div>
                                                <div class="chart-section">
                                                    <div class="chart-title current">🔌 Current</div>
                                                    <div class="chart-canvas">
                                                        <canvas id="current-chart-${utilityId}"></canvas>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    `;
                                    registersContainer.insertAdjacentHTML('afterend', chartsHtml);
                                    
                                    // Reinitialize charts
                                    setTimeout(() => {
                                        initializeCharts(utilityId);
                                    }, 100);
                                }
                            } else {
                                // Charts exist, check if chart instances are still valid
                                const voltageCanvas = document.getElementById(`voltage-chart-${utilityId}`);
                                const currentCanvas = document.getElementById(`current-chart-${utilityId}`);
                                
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
                                }
                            }
                        }
                    } else {
                        // Update just this utility in the UI (full card replacement)
                        const utilityCard = document.getElementById(`utility-${utilityId}`);
                        if (utilityCard) {
                            const newCardHtml = createUtilityCard(utilityId, data.utility_data);
                            utilityCard.outerHTML = newCardHtml;
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
                    const chartsHtml = `
                        <div class="charts-container" id="charts-${utilityId}">
                            <div style="text-align: center; font-weight: bold; margin-bottom: 10px;">
                                📈 Real-time Monitoring Charts
                            </div>
                            <div class="charts-grid">
                                <div class="chart-section">
                                    <div class="chart-title voltage">⚡ Voltage</div>
                                    <div class="chart-canvas">
                                        <canvas id="voltage-chart-${utilityId}"></canvas>
                                    </div>
                                </div>
                                <div class="chart-section">
                                    <div class="chart-title current">🔌 Current</div>
                                    <div class="chart-canvas">
                                        <canvas id="current-chart-${utilityId}"></canvas>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
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
            const countElement = document.getElementById('monitoringCount');
            if (countElement) {
                countElement.textContent = `Live Monitoring: ${monitoringCount}`;
                countElement.style.color = monitoringCount > 0 ? '#e74c3c' : '#7f8c8d';
                countElement.style.fontWeight = monitoringCount > 0 ? 'bold' : 'normal';
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

        function showSuccess(message) {
            const grid = document.getElementById('utilitiesGrid');
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
        app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user")

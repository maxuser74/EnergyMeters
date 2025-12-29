// ============================================================================
// Energy Meters Web Datalogger
// ============================================================================
// This application reads energy meter data via Modbus TCP and serves it to a 
// web interface using Express and Socket.io.
//
// Key Features:
// - Reads configuration from config.md, Utenze.xlsx, and registri.csv
// - Polls Modbus TCP devices sequentially
// - Broadcasts real-time updates to connected web clients
// - Handles network errors gracefully
// - Supports auto-reloading on code changes (via nodemon)
// ============================================================================

const fs = require('fs');
const path = require('path');
const ModbusRTU = require('modbus-serial');
const XLSX = require('xlsx');
const chalk = require('chalk');
const express = require('express');
const http = require('http');
const https = require('https');
const { Server } = require('socket.io');

// Load .env manually since dotenv is not installed
try {
    const envPath = path.join(__dirname, '.env');
    if (fs.existsSync(envPath)) {
        const envConfig = fs.readFileSync(envPath, 'utf8');
        envConfig.split(/\r?\n/).forEach(line => {
            const cleanLine = line.trim();
            if (!cleanLine || cleanLine.startsWith('#')) return;
            
            const match = cleanLine.match(/^([^=]+)=(.*)$/);
            if (match) {
                const key = match[1].trim();
                const value = match[2].trim();
                process.env[key] = value;
            }
        });
        console.log(chalk.green('Loaded configuration from .env'));
        // Debug: Check if keys are loaded
        if (!process.env.INFLUXDB_URL) console.warn(chalk.yellow('Warning: INFLUXDB_URL not found in .env'));
        if (!process.env.INFLUXDB_TOKEN) console.warn(chalk.yellow('Warning: INFLUXDB_TOKEN not found in .env'));
    } else {
        console.warn(chalk.yellow('.env file not found at ' + envPath));
    }
} catch (e) {
    console.warn('Could not load .env file', e);
}

// ============================================================================
// Global Error Handling
// ============================================================================
// Prevent the application from crashing due to common network timeouts or 
// unhandled promise rejections from the Modbus library.
process.on('uncaughtException', (err) => {
    if (err.code === 'ETIMEDOUT' || err.code === 'EHOSTUNREACH' || err.code === 'ECONNREFUSED') {
        // Ignore common network errors to keep the server running
        return;
    }
    console.error('Uncaught Exception:', err.message);
});

process.on('unhandledRejection', (reason, promise) => {
    if (reason.code === 'ETIMEDOUT' || reason.code === 'EHOSTUNREACH' || reason.code === 'ECONNREFUSED') {
        // Ignore common network errors
        return;
    }
    console.error('Unhandled Rejection:', reason);
});

// ============================================================================
// Configuration & State
// ============================================================================
const CONFIG_FILE = 'config.md';
let UTILITIES_FILE = 'Utenze_main.xlsx';
const REGISTERS_FILE = 'registri.csv';
const PORT = 3000;

// Parse command line arguments to allow overriding the utilities file
// Usage: node web_datalogger.js --utilities MyFile.xlsx
const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) {
    if (args[i] === '--utilities' || args[i] === '-u') {
        if (args[i + 1]) {
            UTILITIES_FILE = args[i + 1];
            i++;
        }
    }
}

console.log(chalk.blue(`Using utilities file: ${UTILITIES_FILE}`));

// ============================================================================
// Web Server Setup
// ============================================================================
const app = express();
const server = http.createServer(app);
const io = new Server(server);

// Serve static files from the 'public' directory (index.html, css, etc.)
app.use(express.static(path.join(__dirname, 'public')));
// Expose local vendor assets (Chart.js) to avoid CDN dependency in offline networks
app.use('/vendor', express.static(path.join(__dirname, 'node_modules', 'chart.js', 'dist')));

// Socket.IO Connection Handling
io.on('connection', (socket) => {
    // Send list of available configuration files
    const files = getReadFiles();
    socket.emit('fileList', files);

    // Handle request for file list refresh
    socket.on('getFiles', () => {
        const files = getReadFiles();
        socket.emit('fileList', files);
    });

    // Handle file selection
    socket.on('selectFile', (filename) => {
        if (fs.existsSync(filename) && path.basename(filename).startsWith('Read_')) {
            UTILITIES_FILE = filename;
            utilities = []; // Clear current utilities to force reload
            latestResults = {};
            console.log(chalk.green(`Client selected utilities file: ${UTILITIES_FILE}`));
            
            // Immediately try to load to give feedback
            loadUtilities();
            broadcastUpdate();
        }
    });

    // Handle pause toggle
    socket.on('togglePause', () => {
        isPaused = !isPaused;
        console.log(chalk.yellow(isPaused ? 'Paused polling' : 'Resumed polling'));
        broadcastUpdate();
    });

    // Handle filter updates
    socket.on('updateFilters', (filters) => {
        activeFilters = {
            ...activeFilters,
            ...filters,
            selectedMachines: Array.isArray(filters.selectedMachines) ? filters.selectedMachines : [],
            onlySelected: !!filters.onlySelected
        };
        console.log(chalk.magenta('Filters updated:', JSON.stringify(activeFilters)));
        loadUtilities(); // Reload to apply filters
        broadcastUpdate();
        needsReload = true; // Trigger immediate restart of polling loop
    });

    // Handle history request
    socket.on('getHistory', (utilId) => {
        if (history[utilId]) {
            socket.emit('historyData', {
                id: utilId,
                data: history[utilId]
            });
        }
    });

    // Handle Save to InfluxDB (Manual)
    socket.on('saveSelectedToInflux', (selectedIds) => {
        console.log(chalk.blue(`Saving ${selectedIds.length} machines to InfluxDB...`));
        saveToInflux(selectedIds)
            .then(msg => {
                console.log(chalk.green(msg));
                socket.emit('saveResult', { success: true, message: msg });
            })
            .catch(err => {
                console.error(chalk.red(err));
                socket.emit('saveResult', { success: false, message: err });
            });
    });

    // Handle Toggle Auto-Save
    socket.on('toggleAutoSave', (shouldSave) => {
        isSavingDB = !!shouldSave;
        console.log(chalk.magenta(`Auto-Save to InfluxDB is now ${isSavingDB ? 'ON' : 'OFF'}`));
        // Broadcast status to all clients so UI stays in sync
        io.emit('autoSaveStatus', isSavingDB);
    });
});

function getReadFiles() {
    try {
        return fs.readdirSync(__dirname)
            .filter(f => f.startsWith('Read_') && (f.endsWith('.xlsx') || f.endsWith('.csv')))
            .map(f => ({
                filename: f,
                displayName: f.substring(5) // Remove 'Read_' prefix
            }));
    } catch (e) {
        console.error('Error scanning files:', e);
        return [];
    }
}

// Application State
let config = {
    measurement_interval_ms: 1000,
    modbus_timeout_s: 3
};
let utilities = [];
let registers = [];
let latestResults = {};
let history = {}; // Store historical data for graphs
const MAX_HISTORY_POINTS = 60; // Keep last 60 readings
let isPaused = false;
let availableFilters = { group1: [], group2: [] };
let activeFilters = { group1: [], group2: [], minCurrent: 'all', onlyErrors: false, selectedMachines: [], onlySelected: false };
let needsReload = false;

let isSavingDB = false;

function saveToInflux(selectedIds) {
    if (!process.env.INFLUXDB_URL || !process.env.INFLUXDB_TOKEN) {
        console.error('InfluxDB credentials missing in .env');
        return Promise.reject('InfluxDB credentials missing');
    }

    const lines = [];
    const timestamp = Math.floor(Date.now() / 1000); // Seconds precision

    // If no specific IDs selected, maybe save all? 
    // But the request says "save selected data". 
    // If selectedIds is empty, we assume nothing to save.
    if (!selectedIds || selectedIds.length === 0) {
        return Promise.resolve('No machines selected');
    }

    // console.log(chalk.yellow(`Debug: Saving ${selectedIds.length} IDs. Available utilities: ${utilities.length}`));

    selectedIds.forEach(id => {
        // We need to find the utility info. 
        const util = utilities.find(u => u.id === id);
        const res = latestResults[id];
        
        // Allow saving if status is OK or READING (as long as we have values)
        const isValidStatus = res && (res.status === 'OK' || res.status === 'READING');
        const hasValues = res && res.values && Object.keys(res.values).length > 0;

        if (util && isValidStatus && hasValues) {
            // Tags
            const tags = [
                `machine=${util.name.replace(/ /g, '_')}`,
                `group1=${(util.group1 || util.group || 'Unknown').replace(/ /g, '_')}`,
                `cabinet=${util.cabinet}`,
                `node=${util.node}`
            ];
            
            // Fields
            const fields = [];
            registers.forEach(reg => {
                const val = res.values[reg.startAddress];
                if (val !== undefined && val !== null) {
                    // Clean label for field key
                    let key = reg.label.trim().replace(/ /g, '_').replace(/[^a-zA-Z0-9_]/g, '');
                    
                    // Explicitly ensure kW is saved if label is 'kW'
                    if (reg.label === 'kW') key = 'kW';

                    fields.push(`${key}=${val}`);
                } else {
                    // Debug missing values for kW
                    if (reg.label === 'kW') {
                        console.log(chalk.yellow(`Debug: Missing value for kW (Addr: ${reg.startAddress}) on ${util.id}`));
                    }
                }
            });

            if (fields.length > 0) {
                const line = `energy_meter,${tags.join(',')} ${fields.join(',')} ${timestamp}`;
                lines.push(line);
                // Debug log for the first machine to see what's being sent
                if (lines.length === 1) {
                    console.log(chalk.gray(`Debug Influx Line: ${line}`));
                }
            }
        }
    });

    if (lines.length === 0) {
        return Promise.resolve('No valid data to save for selected machines');
    }

    const data = lines.join('\n');
    const urlStr = `${process.env.INFLUXDB_URL}/api/v2/write?org=${encodeURIComponent(process.env.INFLUXDB_ORG)}&bucket=${encodeURIComponent(process.env.INFLUXDB_BUCKET)}&precision=s`;
    const url = new URL(urlStr);

    return new Promise((resolve, reject) => {
        const options = {
            method: 'POST',
            headers: {
                'Authorization': `Token ${process.env.INFLUXDB_TOKEN}`,
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Length': Buffer.byteLength(data)
            }
        };

        const req = (process.env.INFLUXDB_URL.startsWith('https') ? https : http).request(url, options, (res) => {
            if (res.statusCode >= 200 && res.statusCode < 300) {
                resolve('Data saved to InfluxDB');
            } else {
                let body = '';
                res.on('data', chunk => body += chunk);
                res.on('end', () => {
                    // console.error(`InfluxDB Error (${res.statusCode}): ${body}`);
                    reject(`InfluxDB Error: ${res.statusCode} ${body}`);
                });
            }
        });

        req.on('error', (e) => {
            console.error('InfluxDB Request Error:', e);
            reject(`Request Error: ${e.message}`);
        });

        req.write(data);
        req.end();
    });
}

// ============================================================================
// Data Loading Functions
// ============================================================================

/**
 * Reads configuration settings from config.md
 * Parses key:value pairs for intervals, timeouts, and formatting options.
 */
function loadConfig() {
    try {
        if (fs.existsSync(CONFIG_FILE)) {
            const content = fs.readFileSync(CONFIG_FILE, 'utf8');
            const lines = content.split('\n');
            for (const line of lines) {
                if (line.includes(':')) {
                    const [key, val] = line.split(':', 2);
                    const cleanKey = key.trim();
                    const cleanVal = val.trim();
                    if (cleanKey === 'measurement_interval_ms') {
                        config.measurement_interval_ms = parseInt(cleanVal, 10);
                    } else if (cleanKey === 'modbus_timeout_s') {
                        config.modbus_timeout_s = parseFloat(cleanVal);
                    } else if (cleanKey.startsWith('decimals_')) {
                        config[cleanKey] = parseInt(cleanVal, 10);
                    } else if (cleanKey.startsWith('integers_')) {
                        config[cleanKey] = parseInt(cleanVal, 10);
                    } else if (cleanKey.startsWith('pf_')) {
                        config[cleanKey] = parseFloat(cleanVal);
                    } else if (cleanKey.startsWith('v_')) {
                        config[cleanKey] = parseInt(cleanVal, 10);
                    }
                }
            }
        }
    } catch (e) {
        console.error('Error loading config:', e.message);
    }
}

/**
 * Helper to read the first sheet of an Excel or CSV file
 */
function readDataFile(filePath) {
    if (!filePath || !fs.existsSync(filePath)) {
        // console.error(chalk.red(`File not found: ${filePath}`));
        return [];
    }
    const workbook = XLSX.readFile(filePath);
    const sheetName = workbook.SheetNames[0];
    return XLSX.utils.sheet_to_json(workbook.Sheets[sheetName]);
}

/**
 * Loads the list of meters (utilities) to poll.
 * Handles mapping of Cabinet/Node to IP addresses if IP is missing.
 */
function loadUtilities() {
    try {
        const rawData = readDataFile(UTILITIES_FILE);
        const allUtilities = rawData.map(row => {
            const name = row['Machine'] || row['Name'] || row['Nome'] || 'Unknown';
            const cabinet = row['Cabinet'] || row['Quadro'];
            const node = row['Node'] || row['Nodo'];
            const group1 = row['Group1'] || row['Group 1'] || row['Main Group'] || row['Group'] || 'Unknown';
            const group2 = row['Group2'] || row['Group 2'] || row['Aux Group'] || row['SubGroup'] || 'Unknown';
            let ip = row['IP'] || row['Indirizzo IP'];
            
            // Fallback: Map Cabinet ID to known IP addresses if not specified in file
            if (!ip && cabinet) {
                const cabinetIps = {
                    1: "192.168.156.75",
                    2: "192.168.156.76",
                    3: "192.168.156.77"
                };
                ip = cabinetIps[cabinet];
            }

            return {
                id: `cab${cabinet}_node${node}`,
                name: name,
                cabinet: cabinet,
                node: node,
                group1,
                group2,
                ip: ip,
                port: row['Port'] || 502
            };
        }).filter(u => u.ip && u.node);

        // Extract available options
        const group1 = [...new Set(allUtilities.map(u => u.group1))].sort();
        const group2 = [...new Set(allUtilities.map(u => u.group2))].sort();
        availableFilters = { group1, group2 };
        const selectedSet = new Set((activeFilters.selectedMachines || []).map(id => String(id)));
        const enforceSelected = activeFilters.onlySelected;

        // Apply filters
        utilities = allUtilities.filter(u => {
            const group1Selected = activeFilters.group1.length > 0;
            const group2Selected = activeFilters.group2.length > 0;
            const group1Match = group1Selected ? activeFilters.group1.includes(u.group1) : true;
            const group2Match = group2Selected ? activeFilters.group2.includes(u.group2) : true;
            const selectionMatch = enforceSelected ? selectedSet.has(String(u.id)) : true;

            return group1Match && group2Match && selectionMatch;
        });

    } catch (e) {
        console.error('Error loading utilities:', e.message);
    }
}

/**
 * Loads the Modbus register definitions.
 * Filters out registers marked as 'Report: No'.
 * Applies special handling for 'W' to 'kW' conversion.
 */
function loadRegisters() {
    try {
        const rawData = readDataFile(REGISTERS_FILE);
        registers = rawData.filter(row => {
            const report = row['Report'];
            return !report || ['y', 'yes', 'true', '1'].includes(String(report).toLowerCase());
        }).map(row => {
            const endAddress = parseInt(row['Registro']);
            const dataType = (row['Lenght'] || row['Length'] || 'float').toLowerCase();
            
            // Determine register count based on data type
            let count = 2;
            if (dataType.includes('long long')) count = 4;
            else if (dataType.includes('short')) count = 1;
            else if (dataType.includes('float')) count = 2;

            // Calculate start address (Modbus often uses End Address in docs)
            const startAddress = endAddress - (count - 1);
            
            let label = (row['Title'] || row['Lettura'] || `Reg ${endAddress}`).trim();
            let factor = parseFloat(row['Factor'] || 1.0);

            // Auto-convert W to kW for better readability
            if (label === 'W' || label === 'Active Power W') {
                label = 'kW';
                factor = 0.001;
            }

            return {
                startAddress: startAddress,
                count: count,
                label: label,
                unit: row['Convert to'] || row['Readings'] || '',
                dataType: dataType,
                rounding: row['Rounding'] || row['rounding'],
                factor: factor
            };
        });
    } catch (e) {
        console.error('Error loading registers:', e.message);
    }
}

// ============================================================================
// Modbus Communication
// ============================================================================

/**
 * Reads a single register from a connected Modbus client.
 * Handles data type conversion (Float, Short) and Endianness swapping.
 */
async function readRegister(client, register, nodeId) {
    try {
        client.setID(nodeId);
        const data = await client.readHoldingRegisters(register.startAddress, register.count);
        
        if (data.buffer) {
            const buffer = data.buffer;
            if (register.dataType.includes('float')) {
                if (buffer.length >= 4) {
                    // Handle Modbus Float Endianness (Swap words)
                    // [Word1, Word2] -> [Word2, Word1] -> FloatBE
                    const buf = Buffer.alloc(4);
                    buf.writeUInt16BE(data.data[1], 0); // Low word
                    buf.writeUInt16BE(data.data[0], 2); // High word
                    return buf.readFloatBE(0);
                }
            } else if (register.dataType.includes('short')) {
                return data.data[0];
            }
        }
        return null;
    } catch (e) {
        return null;
    }
}

/**
 * Connects to a utility (meter) and polls all configured registers.
 * Returns an object with values or error status.
 */
async function pollUtility(utility) {
    const client = new ModbusRTU();
    client.on('error', (e) => {}); // Suppress internal library errors

    const result = {
        values: {},
        status: 'OK',
        error: null
    };

    try {
        client.setTimeout(config.modbus_timeout_s * 1000);
        await client.connectTCP(utility.ip, { port: utility.port });
        
        for (const reg of registers) {
            const val = await readRegister(client, reg, utility.node);
            if (val !== null) {
                result.values[reg.startAddress] = val * reg.factor;
            }
        }
    } catch (e) {
        result.status = 'ERROR';
        result.error = e.message;
    } finally {
        try {
            client.close();
        } catch (e) {}
    }
    return result;
}

// ============================================================================
// Main Execution Loop
// ============================================================================

const START_TIME = Date.now();

/**
 * Sends the current state to all connected web clients.
 * Includes a timestamp to trigger client-side reloads if the server restarts.
 */
function broadcastUpdate() {
    io.emit('update', {
        utilities,
        registers,
        latestResults,
        config,
        startTime: START_TIME,
        isPaused,
        isSavingDB, // Send saving status
        availableFilters,
        activeFilters
    });
}

async function run() {
    console.log("Starting Web Datalogger...");
    
    // Start the HTTP server
    server.listen(PORT, () => {
        console.log(`Server running at http://localhost:${PORT}`);
        console.log(chalk.cyan(`Energy Meters Web Logger | Interval: ${config.measurement_interval_ms}ms`));
    });

    // Infinite polling loop
    let loopCounter = 0;
    const FULL_SCAN_INTERVAL = 20; // Every 20 cycles, scan everything to catch status changes

    while (true) {
        loopCounter++;
        const isFullScan = (loopCounter % FULL_SCAN_INTERVAL === 0);
        needsReload = false;

        // Reload config on every iteration to allow hot-swapping settings
        loadConfig();
        loadUtilities();
        loadRegisters();

        if (utilities.length === 0 || registers.length === 0) {
            console.log("Waiting for configuration...");
            await new Promise(r => setTimeout(r, 1000));
            continue;
        }

        if (isPaused) {
            broadcastUpdate();
            await new Promise(r => setTimeout(r, 500));
            continue;
        }

        // Sequential Polling
        for (const util of utilities) {
            if (needsReload) break; // Stop current cycle if filters changed

            // --- Dynamic Filtering Logic ---
            // Skip nodes that don't match the active dynamic filters (Current/Errors)
            // unless it's a Full Scan cycle or we have no data for the node yet.
            if (!isFullScan) {
                const res = latestResults[util.id];
                
                if (res && res.values) {
                    let shouldPoll = true;

                    // 1. Check Current Filter
                    if (activeFilters.minCurrent && activeFilters.minCurrent !== 'all') {
                        let threshold = 5;
                        if (activeFilters.minCurrent === 'high20') threshold = 20;
                        if (activeFilters.minCurrent === 'high40') threshold = 40;
                        
                        let hasHighCurrent = false;
                        for (const reg of registers) {
                            if (reg.label.includes('A L') || reg.label.includes('Current')) {
                                const val = res.values[reg.startAddress] || 0;
                                if (val >= threshold) hasHighCurrent = true;
                            }
                        }
                        if (!hasHighCurrent) shouldPoll = false;
                    }

                    // 2. Check Error Filter
                    if (shouldPoll && activeFilters.onlyErrors) {
                        let hasError = false;
                        for (const reg of registers) {
                            const val = res.values[reg.startAddress];
                            if (val !== undefined) {
                                // PF Check
                                if (reg.label.includes('PF')) {
                                    const redMax = config.pf_red_max !== undefined ? config.pf_red_max : 0.4;
                                    if (val < redMax) hasError = true;
                                }
                                // Voltage Check
                                else if (reg.label.includes('V')) {
                                    let min, max;
                                    if (reg.label.includes('L1-L2') || reg.label.includes('L2-L3') || reg.label.includes('L3-L1')) {
                                        min = config.v_ll_min !== undefined ? config.v_ll_min : 380;
                                        max = config.v_ll_max !== undefined ? config.v_ll_max : 420;
                                    } else if (reg.label.includes('L1-N') || reg.label.includes('L2-N') || reg.label.includes('L3-N')) {
                                        min = config.v_ln_min !== undefined ? config.v_ln_min : 210;
                                        max = config.v_ln_max !== undefined ? config.v_ln_max : 250;
                                    }
                                    if (min !== undefined && max !== undefined) {
                                        if (val < min || val > max) hasError = true;
                                    }
                                }
                                // Negative Check
                                else if (val < 0) {
                                    hasError = true;
                                }
                            }
                        }
                        if (!hasError) shouldPoll = false;
                    }

                    if (!shouldPoll) continue; // Skip this node
                }
            }
            // -------------------------------

            // 1. Notify clients that we are reading this utility
            latestResults[util.id] = { ...latestResults[util.id], status: 'READING' };
            broadcastUpdate();

            // 2. Perform the Modbus read
            const result = await pollUtility(util);
            
            // 3. Update results and notify clients
            latestResults[util.id] = result;
            
            // Update History
            if (!history[util.id]) history[util.id] = [];
            if (result.status === 'OK') {
                history[util.id].push({
                    timestamp: Date.now(),
                    values: result.values
                });
                // Trim history
                if (history[util.id].length > MAX_HISTORY_POINTS) {
                    history[util.id].shift();
                }
            }

            broadcastUpdate();
        }

        // --- Continuous Saving Logic ---
        if (isSavingDB && activeFilters.selectedMachines && activeFilters.selectedMachines.length > 0) {
            // Save silently (no console spam unless error)
            saveToInflux(activeFilters.selectedMachines).catch(err => {
                console.error(chalk.red('Auto-Save Error: ' + err));
            });
        }

        // If reloading, skip the wait interval to start immediately
        if (needsReload) continue;

        // Wait before next cycle
        await new Promise(r => setTimeout(r, config.measurement_interval_ms));
    }
}

run();

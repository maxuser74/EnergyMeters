const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const ModbusRTU = require('modbus-serial');

// Global Error Handling to prevent crashes on network timeouts
process.on('uncaughtException', (err) => {
    console.error('Uncaught Exception:', err.message);
});

process.on('unhandledRejection', (reason, promise) => {
    // Ignore common network timeouts that are already logged
    if (reason && (reason.message === 'TCP Connection Timed Out' || reason.code === 'ETIMEDOUT')) {
        return;
    }
    console.error('Unhandled Rejection:', reason);
});

// Fix for "Unable to move the cache: Access denied" error on Windows
app.disableHardwareAcceleration();

let mainWindow;

// Configuration
const METERS = [
    { name: "CAB1 GEN1", ip: "192.168.156.75", id: 1 },
    { name: "CAB1 GEN2", ip: "192.168.156.75", id: 13 },
    { name: "CAB2 GEN1", ip: "192.168.156.76", id: 1 },
    { name: "CAB2 GEN2", ip: "192.168.156.76", id: 14 },
    { name: "CAB3 GEN",  ip: "192.168.156.77", id: 1 }
];

const POLL_INTERVAL_MS = 5000;
const MODBUS_TIMEOUT_MS = 2000;
const REGISTER_ADDR = 390; // Active Power W (Float)
const REGISTER_LEN = 2;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 400,
        height: 220,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        },
        backgroundColor: '#1e1e1e',
        autoHideMenuBar: true
    });

    mainWindow.loadFile('index.html');
}

app.whenReady().then(() => {
    createWindow();

    app.on('activate', function () {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });

    // Start Polling Loop
    pollMeters();
    setInterval(pollMeters, POLL_INTERVAL_MS);
});

app.on('window-all-closed', function () {
    if (process.platform !== 'darwin') app.quit();
});

async function pollMeters() {
    if (!mainWindow) return;

    const results = [];
    let totalKw = 0;

    for (const meter of METERS) {
        const client = new ModbusRTU();
        
        // Add error listener to prevent unhandled error events
        client.on('error', (e) => {
            // console.error(`Modbus Client Error (${meter.name}):`, e.message);
        });

        let value = 0;
        let status = 'OK';

        try {
            client.setTimeout(MODBUS_TIMEOUT_MS);
            await client.connectTCP(meter.ip, { port: 502 });
            client.setID(meter.id);

            const data = await client.readHoldingRegisters(REGISTER_ADDR, REGISTER_LEN);
            
            // Parse Float with Word Swapping (Modbus Standard for many meters)
            // [Word1, Word2] -> [Word2, Word1] -> FloatBE
            if (data.data && data.data.length >= 2) {
                const buf = Buffer.alloc(4);
                buf.writeUInt16BE(data.data[1], 0); // Low word (at index 1) becomes High word
                buf.writeUInt16BE(data.data[0], 2); // High word (at index 0) becomes Low word
                value = buf.readFloatBE(0);
            } else {
                value = 0;
            }
            
            // Convert W to kW
            value = value / 1000.0;

            // Sanity check
            if (isNaN(value)) value = 0;

            totalKw += value;

        } catch (e) {
            console.error(`Error reading ${meter.name}:`, e.message);
            status = 'ERROR';
            value = 0;
        } finally {
            try {
                client.close();
            } catch (e) {}
        }

        results.push({
            name: meter.name,
            kw: value,
            status: status
        });
    }

    // Send data to renderer
    mainWindow.webContents.send('update-data', {
        meters: results,
        total: totalKw,
        timestamp: new Date().toLocaleTimeString()
    });
}

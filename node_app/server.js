const express = require('express');
const path = require('path');
const cors = require('cors');
const fs = require('fs');
const xlsx = require('xlsx');
const modbus = require('jsmodbus');
const net = require('net');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Global configuration data
let utilitiesConfig = [];
let registersConfig = [];
let latestReadings = {};
let connectionStatus = 'Disconnected';

// Cabinet to IP mapping
const cabinetIPs = {
  1: '192.168.156.75',
  2: '192.168.156.76',
  3: '192.168.156.77'
};

function loadUtilitiesFromExcel() {
  const workbook = xlsx.readFile(path.join(__dirname, '..', 'Utenze.xlsx'));
  const sheet = workbook.Sheets[workbook.SheetNames[0]];
  const json = xlsx.utils.sheet_to_json(sheet);
  utilitiesConfig = json.map(row => {
    const cabinet = Number(row['Cabinet']);
    const node = Number(row['Nodo']);
    return {
      id: `cabinet${cabinet}_node${node}`,
      cabinet,
      node,
      utility_name: String(row['Utenza']),
      ip_address: cabinetIPs[cabinet],
      port: 502
    };
  }).filter(u => u.ip_address);
}

function loadRegistersFromExcel() {
  const workbook = xlsx.readFile(path.join(__dirname, '..', 'registri.xlsx'));
  const sheet = workbook.Sheets[workbook.SheetNames[0]];
  const json = xlsx.utils.sheet_to_json(sheet);
  registersConfig = json.filter(r => String(r['Report']).toLowerCase() === 'yes')
    .map(r => ({
      register: Number(r['Registro']),
      type: r['Type'],
      description: r['Readings'],
      convert: r['Convert to']
    }));
}

function loadConfiguration() {
  loadUtilitiesFromExcel();
  loadRegistersFromExcel();
  console.log(`Loaded ${utilitiesConfig.length} utilities, ${registersConfig.length} registers`);
}

async function readSingleUtility(util) {
  const socket = new net.Socket();
  const client = new modbus.client.TCP(socket);
  const options = { host: util.ip_address, port: util.port };
  return new Promise((resolve, reject) => {
    socket.on('connect', async () => {
      try {
        const res = await client.readHoldingRegisters( util.node, registersConfig.length );
        const readings = {};
        registersConfig.forEach((reg, idx) => {
          readings[reg.description] = res.response._body.valuesAsArray[idx];
        });
        socket.end();
        resolve(readings);
      } catch (err) {
        socket.end();
        reject(err);
      }
    });
    socket.on('error', reject);
    socket.connect(options);
  });
}

async function readAllUtilities() {
  connectionStatus = 'Reading';
  const result = {};
  for (const util of utilitiesConfig) {
    try {
      const readings = await readSingleUtility(util);
      result[util.id] = { success: true, readings };
    } catch (err) {
      result[util.id] = { success: false, error: err.message };
    }
  }
  latestReadings = result;
  connectionStatus = 'Idle';
}

app.get('/api/configuration', (req, res) => {
  res.json({ utilities: utilitiesConfig, registers: registersConfig });
});

app.get('/api/readings', (req, res) => {
  res.json({ readings: latestReadings, connection_status: connectionStatus });
});

app.get('/api/refresh_all', async (req, res) => {
  loadConfiguration();
  await readAllUtilities();
  res.json({ success: true, readings: latestReadings });
});

app.get('/api/refresh_utility/:id', async (req, res) => {
  const util = utilitiesConfig.find(u => u.id === req.params.id);
  if (!util) return res.status(404).json({ error: 'Utility not found' });
  try {
    const readings = await readSingleUtility(util);
    latestReadings[util.id] = { success: true, readings };
    res.json({ success: true, readings });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Initialize and start server
loadConfiguration();
readAllUtilities().catch(err => console.error(err));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});

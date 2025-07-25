# Node.js Energy Meter Dashboard

This sample shows how to read configuration from Excel files and expose the same endpoints as the Python version using **Express.js**. A small frontend powered by **Tailwind CSS 4** displays the readings.

## Usage

1. Install dependencies:
   ```bash
   cd node_app
   npm install
   ```
2. Run the server:
   ```bash
   npm start
   ```
3. Open <http://localhost:3000> in a browser.

The application loads `Utenze.xlsx` and `registri.xlsx` from the repository root. When `Refresh All` or a single `Refresh` button is pressed, it performs Modbus reads using the configuration from those files.

# Energy Meters Datalogger

A Node.js application for reading energy meter data via Modbus TCP. This project provides a real-time web dashboard for monitoring energy consumption.

## Features

*   **Modbus TCP Polling**: Reads data from multiple energy meters sequentially.
*   **Configurable**: Uses Excel and CSV files to define meters and registers.
*   **Web Dashboard**: Provides a dark-themed, responsive web interface with real-time updates via WebSockets.
*   **Live Filtering**: Filter displayed meters by Cabinet and Group directly from the UI.
*   **Visual Alarms**: 
    *   **Power Factor (PF)**: Colors values Red (< 0.4) or Yellow (< 0.7).
    *   **Voltage**: Colors values Red if outside configured ranges (L-L: 380-420V, L-N: 210-250V).
    *   **Active Power (kW)**: Turns Red if the Power Factor for that meter is critical.
*   **Multiple Utility Files**: Switch between different meter configurations (files starting with `Read_*.xlsx`) directly from the web interface.
*   **Auto-Reload**: The web server automatically restarts when code or configuration changes.
*   **Custom Formatting**: Supports configurable decimal places and integer padding for Voltage (V), Current (A), Power Factor (PF), and Power (kW).
*   **Detail View & Charts**: Click a table row to open a per-meter modal with badges and history charts for currents and power (Chart.js served locally with CDN fallback).

## Prerequisites

*   **Node.js**: Version 16 or higher is recommended.
*   **PowerShell**: For running the startup scripts (Windows).

## Installation

1.  Clone or download this repository.
2.  Open a terminal in the project folder.
3.  Install the main dependencies:

    ```powershell
    npm install
    ```
4.  (Optional) If you plan to use the **Plant Total App**:
    
    ```powershell
    cd plant_total
    npm install
    cd ..
    ```

## Configuration

The application uses three main configuration files:

1.  **`config.md`**: General settings.
    *   `measurement_interval_ms`: Time in milliseconds between polling cycles.
    *   `modbus_timeout_s`: Timeout in seconds for Modbus connections.
    *   `decimals_*`: Number of decimal places for V, A, PF, kW.
    *   `integers_*`: Minimum integer digits (padding) for V, A, PF.
    *   `pf_red_max` / `pf_yellow_max`: Thresholds for Power Factor coloring.
    *   `v_ll_min` / `v_ll_max`: Voltage range for Line-to-Line (default 380-420).
    *   `v_ln_min` / `v_ln_max`: Voltage range for Line-to-Neutral (default 210-250).

2.  **`Utenze_main.xlsx`**: Defines the meters to poll.
    *   Columns: `Machine` (Name), `Cabinet`, `Node`, `Group`, `IP` (optional if Cabinet mapping exists), `Port` (default 502).

3.  **`registri.csv`**: Defines the Modbus registers to read.
    *   Columns: `Registro` (Address), `Lenght` (Type: float, short), `Title` (Label), `Factor` (Multiplier).
    *   *Note: Registers labeled "W" or "Active Power W" are automatically converted to kW (factor 0.001).*

## Usage

### Web Datalogger

The easiest way to start the application is using the provided batch file:

```powershell
.\Launch_App.bat
```

This will:
1.  Kill any existing process on port 3000.
2.  Start the Node.js server with auto-reload.
3.  Open the web dashboard in your default browser at **[http://localhost:3000](http://localhost:3000)**.

Alternatively, you can run it manually:

```powershell
.\run_node_web.ps1
```

*   To use a specific utilities file from command line: `.\run_node_web.ps1 --utilities .\MyFile.xlsx`

### Plant Total App

To launch the standalone desktop view for Plant Totals (Electron App):

```powershell
.\Launch_Plant_Total.bat
```

This opens a dedicated window showing aggregated power data for specific cabinets.

### Features & Navigation

*   **Switching Configurations**: Use the file selector in the UI to switch between utility lists (must be named `Read_*.xlsx`).
*   **Detail View & Charts**: Click any meter row to open the detail modal.
*   **Live Filters**: Use the checkboxes in the top bar to filter by "High Current" or "Errors Only".

## Project Structure

*   `web_datalogger.js`: Main entry point for the web application (Express/Socket.io).
*   `public/`: Contains the HTML/CSS/JS for the web frontend.
*   `plant_total/`: Separate Electron application for "Plant Total" display.
    *   `main.js`: Electron entry point.
    *   `index.html`: UI for the plant total window.
*   `Launch_App.bat`: Window batch script to launch the web dashboard.
*   `Launch_Plant_Total.bat`: Windows batch script to launch the Plant Total app.
*   `config.md`: Configuration file for intervals and formatting.
*   `Utenze_main.xlsx`: Default list of meters.
*   `registri.csv`: Modbus register definitions.

## Troubleshooting

*   **ETIMEDOUT / Connection Errors**: The application is designed to ignore occasional network timeouts and keep running. If a meter is offline, it will show as "ERROR" or "✖" in the status column.
*   **File Not Found**: Ensure `Utenze_main.xlsx` and `registri.csv` are in the root directory.

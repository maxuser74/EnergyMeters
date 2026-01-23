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
*   **Auto-Reload**: The web server automatically restarts when code or configuration changes.
*   **Custom Formatting**: Supports configurable decimal places and integer padding for Voltage (V), Current (A), Power Factor (PF), and Power (kW).
*   **Detail View & Charts**: Click a table row to open a per-meter modal with badges and history charts for currents and power (Chart.js served locally with CDN fallback).

## Prerequisites

*   **Node.js**: Version 16 or higher is recommended.
*   **PowerShell**: For running the startup scripts (Windows).

## Installation

1.  Clone or download this repository.
2.  Open a terminal in the project folder.
3.  Install the dependencies:

    ```powershell
    npm install
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

To start the web server with auto-reload enabled:

```powershell
.\run_node_web.ps1
```

*   Open your browser to **[http://localhost:3000](http://localhost:3000)**.
*   To use a specific utilities file: `.\run_node_web.ps1 --utilities .\MyFile.xlsx`

### Detail View & Charts

*   Click any meter row to open the detail modal.
*   You will see live badges plus two history charts: currents (A) and power (kW).
*   The power chart starts at 0 on the Y axis to make trends clear, and points are small to reduce clutter.
*   Chart.js is served locally from `/vendor/chart.umd.js` with a CDN fallback if needed.
*   Up to 120 recent points per meter are buffered client-side so the graph stays populated while streaming.

## Project Structure

*   `web_datalogger.js`: Main entry point for the web application.
*   `public/`: Contains the HTML/CSS/JS for the web frontend.
*   `run_node_web.ps1`: PowerShell script to launch the web logger with `nodemon`.
*   `config.md`: Configuration file for intervals and formatting.
*   `Utenze_main.xlsx`: Default list of meters.

## Troubleshooting

*   **ETIMEDOUT / Connection Errors**: The application is designed to ignore occasional network timeouts and keep running. If a meter is offline, it will show as "ERROR" or "✖" in the status column.
*   **File Not Found**: Ensure `Utenze_main.xlsx` and `registri.csv` are in the root directory.

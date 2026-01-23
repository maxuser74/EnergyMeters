@echo off
cd /d "%~dp0"
echo Installing Node.js dependencies...
call npm install
if %errorlevel% neq 0 (
    echo.
    echo Error installing dependencies. Please check if Node.js is installed.
    pause
    exit /b %errorlevel%
)
echo.
echo Dependencies installed successfully.
pause

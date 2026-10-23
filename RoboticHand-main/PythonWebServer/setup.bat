@echo off
cd /d "%~dp0"
echo ====================================================
echo Setting up Robotic Hand Python Environment
echo ====================================================

where py -3.13 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Using Python 3.13 launcher...
    py -3.13 -m venv venv
) else (
    echo Using system python...
    python -m venv venv
)

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Failed to create virtual environment. Please ensure Python 3.10-3.13 is installed.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo Installing dependencies from requirements.txt...
pip install --upgrade pip
pip install -r requirements.txt

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env
        echo Created .env from .env.example. Please edit .env with your ESP8266 IP address.
    )
)

echo.
echo ====================================================
echo Setup complete!
echo To run vision hand tracking: venv\Scripts\python.exe app.py
echo To run voice control:        venv\Scripts\python.exe voice_control.py
echo ====================================================
pause

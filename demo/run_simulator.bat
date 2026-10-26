@echo off
cd /d "%~dp0"
title RoboticHand - Unified Command Center
echo ========================================================
echo   RoboticHand Unified Command Center & Simulator
echo ========================================================
echo.
echo Starting Unified Server on http://localhost:5000/ ...
echo   - 🖐️ Bionic Hand Real-Time Model
echo   - 🎚️ 5-Finger Slider Controls
echo   - 📷 Embedded MediaPipe Vision Tracking (Toggle via GUI)
echo   - 🎤 Embedded Voice Control Station (Toggle via GUI)
echo.
start http://localhost:5000/

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "mock_esp8266.py"
) else (
    python "mock_esp8266.py"
)
pause

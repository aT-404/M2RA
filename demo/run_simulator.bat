@echo off
title RoboticHand - Hardware Simulator
echo ========================================================
echo   RoboticHand ESP8266 Hardware Simulator & Visualizer
echo ========================================================
echo.
echo Starting Mock Server on http://localhost:5000/ ...
echo UDP Port: 8888 (Vision Streaming)
echo HTTP Port: 5000 (Web GUI & Voice Commands)
echo.
start http://localhost:5000/
start http://localhost:5000/controlGUI
".venv\Scripts\python.exe" "mock_esp8266.py"
pause

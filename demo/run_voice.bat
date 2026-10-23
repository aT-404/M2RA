@echo off
title RoboticHand - Voice Control
echo ========================================================
echo   RoboticHand Voice Control (SpeechRecognition + TTS)
echo ========================================================
echo.
echo Connecting to Simulated ESP8266 at http://127.0.0.1:5000...
echo Speak commands: 'hand open', 'fist', 'point', 'yo sign', 'wave', 'quit'
echo.
".venv\Scripts\python.exe" "voice_control.py"
pause

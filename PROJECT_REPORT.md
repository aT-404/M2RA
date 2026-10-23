# Comprehensive Technical Report: 5-DOF IoT Bionic Robotic Hand
**Document Version:** 1.0  
**Project Phase:** Phase 1 (Firmware, Multi-Modal Software Control, Mechanical Validation, and Hardware-Free Simulation)  
**Author / Developer:** Albert Toj Kayyalaparambil  
**Date:** October 2026  

---

## Executive Summary

The **RoboticHand** project delivers a fully articulated, five-degree-of-freedom (5-DOF) anthropomorphic robotic hand system engineered to operate at an unprecedented low cost (~₹1,200 / ~$14 USD in electronic components). The project integrates 3D-printed bio-mechanisms with tendon actuation, embedded microcontroller firmware on the ESP8266 (NodeMCU), and high-level multi-modal control pipelines including real-time computer vision hand tracking (MediaPipe + OpenCV), voice command processing (Google Speech Recognition + Microsoft Edge-TTS), an on-device captive web dashboard provisioning system, and a hardware-free simulation environment.

This report documents the architectural audit, verification of codebases, critical defect remediation, hardware interfacing specifications, simulation design, and readiness certification for public version control and deployment.

---

## 1. System Architecture & Component Inventory

### 1.1 Hardware Components & Electrical Topology
- **Microcontroller**: NodeMCU ESP8266 (Lolin V3 / ESP-12E module, Tensilica Xtensa L106 32-bit core @ 80 MHz).
- **Actuation System**: 5x SG90 / MG90S micro servos (0.12s/60° rotational speed, 1.8 kg·cm stall torque at 4.8V).
  - Actuation Principle: Rotational servo horns apply tension to high-strength nylon filaments routed through internal phalangeal and carpal tunnels. Return motion is powered by antagonistic elastic bands on the dorsal side.
- **Diagnostics & Display**: 1.3-inch OLED display (SH1106 driver, 128x64 resolution, I2C interface on GPIO4/GPIO5).
- **Power Architecture**: 
  - Dual-rail topology: Regulated 5V 2A–3A external bus powering high-current servo VCC rails and the NodeMCU VIN pin.
  - Common ground reference bridging ESP8266 logic GND and actuator power GND.

### 1.2 Firmware Architecture (`RoboticHandHardwareSketch`)
- **Framework**: Arduino C++ managed via PlatformIO.
- **Embedded Web Server**: `ESP8266WebServer` serving static captive portals, responsive slider GUIs, and handling REST endpoints.
- **Socket Communication**: `WiFiUDP` listener on port 8888 for sub-10ms packet processing during real-time computer vision streaming.
- **Persistent Storage**: Flash File System (SPIFFS) managing `config.json` via `ArduinoJson` v7 for multi-AP credentials and pin assignments.
- **State Machine**: Non-blocking loop managing UDP parsing, software animations (cascading finger wave), OLED screen refreshes, and command cooldown enforcement.

### 1.3 Computer Vision Pipeline (`PythonWebServer/app.py`)
- **Engine**: Google MediaPipe Hand Landmarker Task model (`hand_landmarker.task`) executed on CPU via TensorFlow Lite XNNPACK delegate.
- **Capture**: OpenCV VideoCapture querying 60fps RGB frames from local webcam.
- **Kinematic Calculation**: Euclidean distance calculations between wrist (`Landmark 0`) and fingertip landmarks (`Landmarks 4, 8, 12, 16, 20`), dynamically calibrated against running `min_distances` and `max_distances` to map directly to angular servo degrees (0° to 180°).
- **EMA Anti-Jitter Filter**: Exponential Moving Average smoothing (`EMA_ALPHA = 0.35`) eliminates micro-tremors from computer vision landmark jitter, preventing servo overheating and mechanical gear wear.
- **Transmission**: Datagram socket broadcasting CSV strings `<Thumb,Index,Middle,Ring,Pinky>` directly to the ESP8266 UDP port.

### 1.4 Voice Interface Pipeline (`PythonWebServer/voice_control.py`)
- **Speech Capture**: PyAudio / SpeechRecognition querying system microphone with ambient noise filtering.
- **Recognition Backend**: Google Web Speech API parsing natural phonemes into normalized command strings.
- **Acoustic Feedback**: Microsoft Edge Neural TTS streaming natural vocal acknowledgments (`en-US-JennyNeural`).
- **Execution**: Direct synchronous HTTP GET queries hitting the ESP8266 `/gesture?type=...` endpoint.

### 1.5 Hardware-Free Simulation Subsystem (`demo/`)
- **Simulator Server (`mock_esp8266.py`)**: A multi-threaded Python server that:
  - Binds UDP port 8888 to process incoming datagram packets from `app.py`.
  - Binds HTTP port 5000 to serve the original on-device Web GUI (`/controlGUI`) and handle REST gesture queries (`/gesture?type=...`) from `voice_control.py`.
  - Features an interactive **SVG 2D Bionic Hand Visualizer** where each finger flexes and curls in real time.
  - Features a **Virtual SH1106 OLED Display** mirroring the physical device's telemetry screens.

---

## 2. Issues Discovered During Audit & Technical Fixes Applied

During our comprehensive end-to-end testing and audit of the original codebase, several breaking issues, version incompatibilities, and path vulnerabilities were identified and resolved:

### Issue 2.1: Hardcoded Personal Credentials in Firmware
- **Root Cause**: The original firmware had hardcoded personal WiFi credentials (`"Room 307"`, `"Akhilesh"`, `"Akhi2468"`) in `RoboticHandHardwareSketch.ino`. On boot, the ESP8266 would fail three connection trials before falling back, creating boot delays and security leaks.
- **Resolution**: Replaced the default configuration with an empty array `[]`. If no known network is found, the microcontroller immediately activates the `ServoGrip` captive setup Access Point, allowing any user to configure their local credentials seamlessly.

### Issue 2.2: Sliced Machine G-Code Bloat (1.7 Million Lines / 45 MB)
- **Root Cause**: The repository included 12 pre-sliced `.gcode` files (`STL Files/gcode/`). G-code is machine-specific (printer bed, nozzle temp, slicing profile) and cannot be generalized across 3D printers. The folder also contained personal non-project prints (`AK2_Batman.gcode`, `AK2_Sword.gcode`).
- **Resolution**: Removed all G-code files from version control. The pure STL models (`1.stl`–`6.stl`, `A.STL`–`N.STL`, `Assemble.stl`) are preserved, enabling users to slice models for their own 3D printers.

### Issue 2.3: Breaking `edge-tts` 403 Forbidden Handshake Error
- **Root Cause**: `requirements.txt` previously pinned `edge-tts==7.2.8`. Microsoft updated the WebSocket authentication parameters (`Sec-MS-GEC` token version) on their backend servers, causing `edge-tts 7.2.8` to fail with `aiohttp.client_exceptions.WSServerHandshakeError: 403, message='Invalid response status'`.
- **Resolution**: Upgraded dependency to `edge-tts>=7.3.0`, which contains the revised client handshake tokens. Validated synthesis of audio files in tests.

### Issue 2.4: Windows Audio File-Locking in Voice Feedback
- **Root Cause**: `voice_control.py` wrote speech audio to a static `temp.mp3` file, launched it via `os.startfile()`, and immediately called `os.remove("temp.mp3")`. Because Windows Media Player locks active files, this raised `PermissionError: [WinError 32] The process cannot access the file because it is being used by another process`.
- **Resolution**: Implemented unique timestamped filenames (`tts_<timestamp>.mp3`) and an asynchronous background cleaner that purges stale audio clips while leaving active streams unlocked.

### Issue 2.5: MediaPipe Video Timestamp Drift on Webcams
- **Root Cause**: `app.py` passed `int(cap.get(cv2.CAP_PROP_POS_MSEC))` into `detect_for_video`. Many USB webcams return 0 or duplicate timestamps for consecutive frames, triggering internal MediaPipe errors (`Input timestamp must be monotonically increasing`).
- **Resolution**: Refactored timestamp generation to use a high-resolution monotonic timer (`int(time.perf_counter() * 1000)`), guaranteeing strictly increasing millisecond timestamps.

### Issue 2.6: Missing Default Environment Template & Path Fragility
- **Root Cause**: Both `app.py` and `voice_control.py` opened `.env` and `hand_landmarker.task` using bare relative filenames. If a user invoked scripts from the repository root, Python crashed with `FileNotFoundError`.
- **Resolution**: Standardized on `Path(__file__).resolve().parent` and `python-dotenv`. Added `.env.example` templates across all environments.

---

## 3. Communication Protocol Specifications

### 3.1 UDP Stream Protocol (Computer Vision Tracking)
- **Port**: `8888`
- **Format**: Comma-separated ASCII string of 5 integers (0–180):
  ```
  <Thumb>,<Index>,<Middle>,<Ring>,<Pinky>
  ```
  - `0`: Finger fully extended (open)
  - `180`: Finger fully curled (closed)
- **Transmission Frequency**: Sent every 4th frame (approx. 15 Hz at 60 FPS) to prevent ESP8266 packet buffer overflow.

### 3.2 HTTP REST Endpoints
| Endpoint | Method | Query / Payload | Function |
| :--- | :---: | :--- | :--- |
| `/controlGUI` | `GET` / `POST` | `thumb`, `index`, `middle`, `ring`, `pinky`, `mode` | Interactive sliders and gesture trigger. |
| `/gesture` | `GET` | `type=<open\|close\|fist\|point\|yo\|wave>` | Named macro gestures. |
| `/controlAll` | `GET` | `thumb=<deg>&index=<deg>&...` | Programmatic multi-finger control. |
| `/addNetwork` | `POST` | `key`, `ssid`, `password` | Captive portal network addition. |
| `/reboot` | `GET` | None | Triggers microcontroller restart. |

---

## 4. Current Status & Readiness Checklist

| Evaluation Item | Status | Verification Detail |
| :--- | :---: | :--- |
| **ESP8266 Firmware** | ✅ READY | Validated routing, WiFi fallback, OLED telemetry, UDP listener. |
| **MediaPipe Landmarker** | ✅ READY | Model loads cleanly with TensorFlow Lite XNNPACK delegate. |
| **OpenCV Video Stream** | ✅ READY | Verified capture loop with monotonic timestamping & EMA filter. |
| **Voice Recognition** | ✅ READY | Microphone capture and Google Speech parser functional. |
| **Edge-TTS Speech Feedback** | ✅ READY | Upgraded to >=7.3.0; timestamped file-lock fix verified. |
| **Hardware-Free Simulator** | ✅ READY | Interactive SVG hand, simulated OLED, UDP:8888 & HTTP:5000 verified. |
| **Repository Hygiene** | ✅ READY | No G-code bloat, no virtual environments committed, clean `.gitignore`. |

---

## 5. Phase 2 Roadmap & Future Enhancements

1. **EMG / Myoelectric Muscle Sensing**: Integrate an AD8232 or MyoWare surface EMG sensor for true biomedical bionic control directly from forearm muscle impulses.
2. **Tactile & Force Feedback**: Embed Force Sensitive Resistors (FSRs) on the 3D-printed fingertips to measure contact pressure and provide adaptive grasping.
3. **Wrist Articulation**: Add a 6th high-torque servo (MG996R) for wrist flexion and pronation/supination.
4. **WebSocket Bidirectional Streaming**: Upgrade from HTTP polling to full-duplex WebSockets for real-time web telemetry.

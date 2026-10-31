# 🤖 RoboticHand — Low-Cost 5-DOF IoT Bionic Robotic Hand

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: ESP8266](https://img.shields.io/badge/Hardware-NodeMCU%20ESP8266-red.svg)](https://www.espressif.com/)
[![Computer Vision: MediaPipe](https://img.shields.io/badge/Vision-Google%20MediaPipe-green.svg)](https://developers.google.com/mediapipe)
[![Framework: PlatformIO](https://img.shields.io/badge/Firmware-PlatformIO%20%7C%20Arduino-orange.svg)](https://platformio.org/)
[![Python: 3.10--3.13](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Status: In Progress](https://img.shields.io/badge/Status-In%20Progress-amber.svg)](#-project-status)

An accessible, tendon-actuated, five-degree-of-freedom (5-DOF) anthropomorphic robotic hand system engineered to operate at an unprecedented low cost (~₹1,200 / ~$14 USD in electronic components). The system pairs 3D-printed bio-mechanisms with an onboard **NodeMCU ESP8266** microcontroller and four multi-modal control pipelines:

1. **Real-Time Computer Vision Tracking** *(Operational)*: OpenCV + MediaPipe 21-point hand tracking with EMA anti-jitter smoothing streamed via low-latency UDP.
2. **Acoustic Voice Control** *(Operational)*: Google Web Speech Recognition with Microsoft Edge Neural TTS audio feedback.
3. **On-Device Responsive Web GUI** *(Operational)*: Live finger slider controls and macro gesture buttons served directly by the ESP8266 HTTP web server.
4. **EEG Brain-Computer Interface (BCI) Control** *(In Progress)*: Non-invasive electroencephalography sensor signal acquisition, artifact filtering, and motor imagery pattern classification for direct neural actuation.

In addition, an **Interactive Hardware-Free Simulator** provides a full browser-based 2D articulated hand model, virtual OLED display, and UDP/HTTP test station for rapid testing without physical hardware.

---

## 📌 Project Status

This project is actively **in progress**. 
- **Completed & Operational:** 5-DOF mechanical design & 3D printing files, ESP8266 firmware, real-time computer vision tracking, speech recognition voice interface, embedded web control station, and the unified hardware-free simulator.
- **Under Active Development:** The **4th control modality — EEG (Electroencephalography) Control**. This pipeline focuses on capturing raw neuro-signals, processing frequency bands (mu/beta rhythms associated with motor intent), and translating classified mental commands into robotic finger flexes.

---

## 📑 Table of Contents
- [Project Status](#-project-status)
- [Project Overview](#-key-features)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Repository Structure](#-repository-structure)
- [Hardware & Bill of Materials](#-hardware--bill-of-materials)
- [Wiring & Pin Configuration](#-wiring--pin-configuration)
- [Getting Started](#-getting-started)
  - [Option A: Hardware-Free Interactive Demo & Simulator](#option-a-hardware-free-interactive-demo--simulator-no-hardware-required)
  - [Option B: Physical Hardware Deployment (ESP8266 + Servos)](#option-b-physical-hardware-deployment-esp8266--servos)
- [Communication Protocol Specs](#-communication-protocol-specs)
- [Troubleshooting & Diagnostics](#-troubleshooting--diagnostics)
- [Project Team](#-project-team)
- [License](#-license)

---

## 🌟 Key Features

- **5-DOF Independent Articulation**: Individual servo motor control for thumb, index, middle, ring, and pinky fingers.
- **Under-Actuated Bio-Mechanical Design**: Tendon flexion cables paired with antagonistic elastic return bands for natural finger curvature.
- **Low-Latency Vision Mimicry**: Real-time 3D hand landmark estimation calculating Euclidean finger curl distances normalized to 0°–180° servo angles, transmitted via UDP on port 8888.
- **Anti-Jitter EMA Filter**: Exponential Moving Average smoothing (`EMA_ALPHA = 0.35`) prevents servo chatter and mechanical wear.
- **Acoustic Feedback**: Hands-free voice commands parsed via Google Speech Recognition with spoken responses synthesized through Microsoft Edge Neural TTS (`en-US-JennyNeural`).
- **EEG Neural Control (In Progress)**: Brain-Computer Interface pipeline for decoding motor intent from EEG brainwave rhythms.
- **Captive Network Provisioning**: On-device soft AP (`ServoGrip`) broadcasts automatically when disconnected, offering a zero-code configuration portal.
- **Hardware-Free Simulation Environment**: Test the Web GUI, vision tracking, and voice control directly on your PC with zero physical hardware connected.

---

## 🏗️ System Architecture

```
                                    +-----------------------------------------+
                                    |         User Control Modalities         |
                                    +-----------------------------------------+
                                                         |
         +--------------------------+--------------------+--------------------+--------------------------+
         |                          |                                         |                          |
         v                          v                                         v                          v
+------------------+      +-------------------+                     +--------------------+      +------------------+
|  Web Dashboard   |      | OpenCV+MediaPipe  |                     | SpeechRecognition  |      |   EEG / Neural   |
| (Browser/Mobile) |      |  (Webcam Vision)  |                     |   & Edge-TTS (Mic) |      | BCI Sensor Stream|
+------------------+      +-------------------+                     +--------------------+      +------------------+
         |                          |                                         |                          |
    HTTP GET/POST                  UDP                                       HTTP                    Bandpass &
 (Port 80 REST API)            (Port 8888)                            (Port 80 /gesture)         Classifier Pipeline
         |                          |                                         |                  (In Development)
         |                          |                                         |                          |
         +--------------------------+--------------------+--------------------+--------------------------+
                                                         |
                                                         v
                                         +-------------------------------+
                                         |   NodeMCU ESP8266 Controller  |
                                         |  (or mock_esp8266.py in Demo) |
                                         +-------------------------------+
                                           |          |              |
                                +----------+          |              +----------+
                                |                     |                         |
                                v                     v                         v
                        +---------------+     +---------------+         +---------------+
                        |  5x SG90/MG90S|     | SH1106 OLED   |         | Non-Volatile  |
                        |  Servo Motors |     | Display 128x64|         | SPIFFS Config |
                        +---------------+     +---------------+         +---------------+
                                |
                                v
                        +---------------+
                        | 3D Tendon Hand|
                        +---------------+
```

---

## 📁 Repository Structure

```
M2RA/
├── demo/                             # Hardware-Free Interactive Simulator
│   ├── mock_esp8266.py               # Simulated ESP8266 (UDP:8888, HTTP:5000 + SVG visualizer)
│   ├── app.py                        # Computer vision hand tracking (points to simulator)
│   ├── voice_control.py              # Voice control with speech synthesis (points to simulator)
│   ├── hand_landmarker.task          # Pre-trained MediaPipe hand landmark model asset
│   ├── requirements.txt              # Dependencies for running the demo
│   ├── .env.example                  # Template configuration for local simulation
│   ├── run_simulator.bat             # One-click launcher: starts simulator & opens browser
│   ├── run_vision.bat                # One-click launcher: starts webcam tracking
│   └── run_voice.bat                 # One-click launcher: starts voice recognition console
├── Drivers/                          # USB-to-UART hardware drivers
│   └── CH34x_Install_Windows_v3_4.EXE# Windows driver for NodeMCU CH340 chip
├── RoboticHand-main/                 # Production Source Code
│   ├── PythonWebServer/              # Python vision & voice production control station
│   │   ├── app.py                    # OpenCV + MediaPipe tracking script
│   │   ├── voice_control.py          # Speech recognition & Edge-TTS script
│   │   ├── hand_landmarker.task      # MediaPipe model asset (CPU/TFLite)
│   │   ├── requirements.txt          # Python dependencies
│   │   ├── setup.bat                 # Automated venv creation & dependency installer
│   │   └── .env.example              # Template configuration for physical ESP8266
│   ├── RoboticHandHardwareSketch/    # Embedded C++ Firmware for ESP8266
│   │   ├── src/
│   │   │   └── RoboticHandHardwareSketch.ino # Main firmware (servos, OLED, web routes, UDP)
│   │   └── platformio.ini            # PlatformIO build & upload specification
│   ├── STL Files/                    # 3D Printable Mechanical Models
│   │   ├── 1.stl - 6.stl             # Articulated phalanges and finger joint segments
│   │   ├── A.STL - N.STL             # Palm chassis, servo brackets, and structural mounts
│   │   ├── P1.stl - P3.stl           # Retaining pins and tendon guides
│   │   └── Assemble.stl              # Complete reference assembly model
│   └── RoboticHand.code-workspace    # Visual Studio Code multi-root workspace
├── .gitignore                        # Git exclusion rules
├── LICENSE                           # MIT Open Source License
└── README.md                         # This documentation guide
```

---

## 🛠️ Hardware & Bill of Materials

| Component | Specification | Quantity | Approx. Cost (INR) |
| :--- | :--- | :---: | :---: |
| **Microcontroller** | NodeMCU ESP8266 (Lolin V3 / ESP-12E) | 1 | ₹280 |
| **Servo Motors** | SG90 or MG90S Micro Servos (180° rotation) | 5 | ₹450 (₹90 ea) |
| **Display** | 1.3-inch OLED (SH1106 driver, I2C, 128x64) | 1 | ₹180 |
| **Power Supply** | 5V 2A–3A DC Wall Adapter / Bench Supply | 1 | ₹150 |
| **Structure** | 3D-Printed PLA/PETG Components (0.2mm layer) | 20 parts | ~₹100 (filament) |
| **Actuation Tendons**| High-tensile Braided Nylon / Fishing Line | ~2 meters| ₹20 |
| **Return Antagonists**| Orthodontic / Mini Elastic Bands | 5–10 pcs | ₹10 |
| **Wiring** | Dupont Jumper Wires (M-M / M-F) | ~20 pcs | ₹30 |
| **TOTAL** | | | **~₹1,220 (~$14 USD)** |

---

## 🔌 Wiring & Pin Configuration

| Component | Pin Function | ESP8266 Pin | GPIO Pin | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Thumb Servo** | PWM Signal | `D0` | GPIO16 | 500µs–2400µs pulse range |
| **Index Servo** | PWM Signal | `D3` | GPIO0 | 500µs–2400µs pulse range |
| **Middle Servo**| PWM Signal | `D5` | GPIO14 | 500µs–2400µs pulse range |
| **Ring Servo** | PWM Signal | `D6` | GPIO12 | 500µs–2400µs pulse range |
| **Pinky Servo** | PWM Signal | `D7` | GPIO13 | 500µs–2400µs pulse range |
| **OLED Display**| I2C SDA | `D1` | GPIO5 | 3.3V / 5V tolerant |
| **OLED Display**| I2C SCL | `D2` | GPIO4 | I2C Address: `0x3C` |
| **All Servos** | VCC Power | External 5V | — | **DO NOT power servos from ESP 3.3V!** |
| **All Servos** | Ground | External GND | GND | **Connect common ground with ESP8266 GND** |

> ⚠️ **Hardware Safety Notice:**  
> SG90/MG90S servos draw up to 800mA stall current each. Simultaneous finger movement can pull up to 2A. Powering servos directly from the ESP8266 onboard 3.3V rail will cause brownout resets and potential hardware damage. Always use an external regulated 5V power supply with a common ground reference.

---

## 🚀 Getting Started

### Option A: Hardware-Free Interactive Demo & Simulator (No Hardware Required!)

You can explore the entire project right now without any physical microcontroller or servos connected.

1. **Prerequisites**: Python 3.10–3.13 installed.
2. **Setup the Virtual Environment**:
   ```powershell
   cd demo
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Launch the Simulator**:
   Double-click [`demo/run_simulator.bat`](demo/run_simulator.bat) (or run `python mock_esp8266.py`).
   - Your browser will open to **http://localhost:5000/** showcasing:
     - Real-time animated 2D bionic hand.
     - Simulated SH1106 OLED screen cycling metrics.
     - Live UDP & HTTP telemetry log.
     - Quick gesture buttons (*Open, Fist, Point, Yo Sign, Wave*).
   - The original on-device Web GUI is available at **http://localhost:5000/controlGUI**.
4. **Launch Vision Tracking**:
   Double-click [`demo/run_vision.bat`](demo/run_vision.bat) (or run `python app.py`).
   - Show your hand to your webcam. As you curl your fingers, the simulator mirrors your hand in real time!
   - Press `q` in the video window to quit.
5. **Launch Voice Control**:
   Double-click [`demo/run_voice.bat`](demo/run_voice.bat) (or run `python voice_control.py`).
   - Speak commands: `"hand open"`, `"fist"`, `"point"`, `"yo sign"`, `"wave"`, `"quit"`.

---

### Option B: Physical Hardware Deployment (ESP8266 + Servos)

#### Step 1: Upload Firmware to ESP8266
1. Install [PlatformIO](https://platformio.org/) in VS Code or PlatformIO Core CLI.
2. Connect your NodeMCU board via Micro-USB. (If port is unrecognized on Windows, install [`Drivers/CH34x_Install_Windows_v3_4.EXE`](Drivers/CH34x_Install_Windows_v3_4.EXE)).
3. Build and upload:
   ```powershell
   cd RoboticHand-main/RoboticHandHardwareSketch
   pio run --target upload
   pio device monitor --baud 74880
   ```

#### Step 2: WiFi Provisioning via Captive Portal
1. On initial boot, the ESP8266 detects no saved networks and broadcasts an open WiFi Access Point:
   - **SSID**: `ServoGrip`
   - **Password**: `Servo@Grip`
2. Connect your smartphone or laptop to `ServoGrip`. Navigate to **http://192.168.2.1/** in your browser.
3. Enter key `Servo@grip`, your local WiFi SSID, and WiFi password. Click **Submit** & **Reboot**.
4. Upon reboot, the onboard OLED displays the assigned local IP address (e.g., `192.168.1.50`).

#### Step 3: Run Python Control Scripts
1. Navigate to the Python control directory:
   ```powershell
   cd RoboticHand-main/PythonWebServer
   .\setup.bat
   ```
2. Create your `.env` file by copying `.env.example`:
   ```powershell
   copy .env.example .env
   ```
3. Edit `.env` with your ESP8266 IP address:
   ```env
   ESP_IP=192.168.1.50
   UDP_PORT=8888
   ```
4. **Run Hand Tracking**:
   ```powershell
   .\venv\Scripts\python.exe app.py
   ```
5. **Run Voice Control**:
   ```powershell
   .\venv\Scripts\python.exe voice_control.py
   ```
6. **Open Mobile / Browser Web GUI**:
   Open `http://192.168.1.50/controlGUI` on any device connected to the same WiFi network.

---

## 📡 Communication Protocol Specs

### 1. High-Speed Vision Tracking (UDP)
- **Transport**: Connectionless UDP datagrams
- **Target**: `ESP_IP:8888`
- **Payload Format**: ASCII CSV string representing angles from 0° (open) to 180° (curled):
  ```
  <Thumb>,<Index>,<Middle>,<Ring>,<Pinky>
  ```
  *Example*: `0,180,180,180,180` (Index, middle, ring, pinky closed; thumb open).
- **Rate**: Transmitted every 4th video frame with Exponential Moving Average (`EMA_ALPHA = 0.35`) smoothing to eliminate jitter.

### 2. HTTP REST Endpoints
| Endpoint | Method | Parameters | Function |
| :--- | :---: | :--- | :--- |
| `/controlGUI` | `GET` / `POST` | `thumb`, `index`, `middle`, `ring`, `pinky`, `mode` | Serves web sliders; updates servos on submit. |
| `/gesture` | `GET` | `?type=<open\|close\|fist\|point\|yo\|wave>` | Executes pre-programmed multi-finger gestures. |
| `/controlAll` | `GET` | `?thumb=<0-180>&index=<0-180>&...` | Programmatic multi-servo angle adjustment. |
| `/addNetwork` | `POST` | `key`, `ssid`, `password` | Saves new WiFi credentials to SPIFFS flash. |
| `/reboot` | `GET` | None | Soft-reboots the ESP8266 microcontroller. |

---

## 🔍 Troubleshooting & Diagnostics

- **Webcam Fails to Start (`app.py`)**: Ensure no other application (Zoom, Teams, Camera app) is using camera index 0. You can change camera index in `cv2.VideoCapture(0)`.
- **Servos Jitter or Hand Resets on Movement**: The power supply is inadequate or brownouts are occurring. Ensure your 5V power supply delivers at least 2A and that the power supply GND is tied to ESP8266 GND.
- **Edge-TTS 403 Forbidden**: Make sure `requirements.txt` installs `edge-tts>=7.3.0`. Older versions (7.2.8) have outdated WebSocket authentication parameters.
- **UDP Packets Not Reaching ESP8266**: Ensure your PC and the ESP8266 are on the same subnet and that your router / Windows Firewall allows UDP traffic on port 8888.

---

## 👥 Project Team

- **Albert Toj Kayyalaparambil**
- **Vivek Viswanath**
- **Ronith Promy**
- **Shifa Mariyam**

---

## 📜 License

This project is licensed under the **MIT License**. See the [**`LICENSE`**](LICENSE) file for complete terms and permissions.

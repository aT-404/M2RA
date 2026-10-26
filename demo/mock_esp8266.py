"""
RoboticHand Unified Command Center & Hardware Simulator
Developers: Albert Toj Kayyalaparambil, Vivek Viswanath, Ronith Promy, Shifa Mariyam

Integrates into a single modern dashboard:
1. Live Animated 2D/3D Bionic Hand Model
2. 5-Finger Slider Controls (Thumb, Index, Middle, Ring, Pinky: 0°-180°)
3. Embedded Computer Vision (MediaPipe + OpenCV) with Start/Stop controls and MJPEG stream
4. Embedded Voice Control (SpeechRecognition + Edge-TTS) with Start/Stop controls & transcription
5. Virtual SH1106 OLED Display (128x64)
6. Real-time Telemetry & Event Console
7. Background UDP Server on port 8888 for external streamers
"""

import http.server
import socket
import socketserver
import threading
import time
import json
import urllib.parse
import os
import math
import platform
import asyncio
from pathlib import Path

# Optional heavy imports for vision & voice
try:
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    HAS_VISION = True
except Exception as e:
    HAS_VISION = False
    print(f"[WARNING] Vision libraries not available: {e}")

try:
    import speech_recognition as sr
    import edge_tts
    HAS_VOICE = True
except Exception as e:
    HAS_VOICE = False
    print(f"[WARNING] Voice libraries not available: {e}")

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "hand_landmarker.task"
HTTP_PORT = 5000
UDP_PORT = 8888

# Global system state
state = {
    "servos": {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0},
    "last_source": "System Ready",
    "last_activity": "Standing by for commands",
    "udp_packets_count": 0,
    "http_requests_count": 0,
    "cooldown_until": 0,
    "start_time": time.time(),
    "camera_active": False,
    "camera_fps": 0.0,
    "voice_active": False,
    "voice_status": "Idle",
    "last_voice_text": "",
    "recent_logs": []
}

state_lock = threading.Lock()

# Global camera streaming frame buffer
current_camera_frame = None
camera_frame_lock = threading.Lock()
camera_thread = None
camera_should_run = False

# Global voice recognition worker
voice_thread = None
voice_should_run = False

def add_log(msg, category="INFO"):
    timestamp = time.strftime("%H:%M:%S")
    entry = f"[{timestamp}] [{category}] {msg}"
    with state_lock:
        state["recent_logs"].insert(0, entry)
        if len(state["recent_logs"]) > 30:
            state["recent_logs"].pop()

def set_cooldown(duration_sec=2.0):
    with state_lock:
        state["cooldown_until"] = time.time() + duration_sec

def set_gesture(gesture_name):
    set_cooldown(2.0)
    name = gesture_name.lower().strip()
    add_log(f"Gesture triggered: '{name}'", "GESTURE")
    
    if name == "open":
        with state_lock:
            state["servos"] = {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0}
            state["last_source"] = "Gesture Command"
            state["last_activity"] = "Gesture: Hand Open"
    elif name in ["close", "fist"]:
        with state_lock:
            state["servos"] = {"thumb": 180, "index": 180, "middle": 180, "ring": 180, "pinky": 180}
            state["last_source"] = "Gesture Command"
            state["last_activity"] = "Gesture: Fist / Closed"
    elif name == "point":
        with state_lock:
            state["servos"] = {"thumb": 180, "index": 0, "middle": 180, "ring": 180, "pinky": 180}
            state["last_source"] = "Gesture Command"
            state["last_activity"] = "Gesture: Point"
    elif name == "yo":
        with state_lock:
            state["servos"] = {"thumb": 0, "index": 0, "middle": 180, "ring": 180, "pinky": 0}
            state["last_source"] = "Gesture Command"
            state["last_activity"] = "Gesture: Yo Sign"
    elif name == "wave":
        def run_wave_animation():
            steps = [
                {"thumb": 180, "index": 180, "middle": 180, "ring": 180, "pinky": 180},
                {"thumb": 180, "index": 180, "middle": 180, "ring": 180, "pinky": 0},
                {"thumb": 180, "index": 180, "middle": 180, "ring": 0, "pinky": 0},
                {"thumb": 180, "index": 180, "middle": 0, "ring": 0, "pinky": 0},
                {"thumb": 180, "index": 0, "middle": 0, "ring": 0, "pinky": 0},
                {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0},
                {"thumb": 180, "index": 0, "middle": 0, "ring": 0, "pinky": 0},
                {"thumb": 180, "index": 180, "middle": 0, "ring": 0, "pinky": 0},
                {"thumb": 180, "index": 180, "middle": 180, "ring": 0, "pinky": 0},
                {"thumb": 180, "index": 180, "middle": 180, "ring": 180, "pinky": 0},
                {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0}
            ]
            for step in steps:
                with state_lock:
                    state["servos"] = step.copy()
                    state["last_source"] = "Gesture Animation (Wave)"
                    state["last_activity"] = "Waving fingers..."
                time.sleep(0.12)
            add_log("Wave animation sequence completed", "GESTURE")
        threading.Thread(target=run_wave_animation, daemon=True).start()

# -------------------------------------------------------------
# Embedded Computer Vision Worker (MediaPipe + OpenCV)
# -------------------------------------------------------------
def calculate_distance(point1, point2):
    return math.sqrt((point1.x - point2.x)**2 + (point1.y - point2.y)**2 + (point1.z - point2.z)**2)

def camera_worker_loop():
    global current_camera_frame, camera_should_run
    if not HAS_VISION:
        add_log("Cannot start camera: OpenCV/MediaPipe not installed", "CAMERA")
        return

    add_log("Opening webcam index 0...", "CAMERA")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        add_log("Error: Could not open webcam device", "CAMERA")
        with state_lock:
            state["camera_active"] = False
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(MODEL_PATH)),
            num_hands=1,
            running_mode=vision.RunningMode.VIDEO)
        landmarker = vision.HandLandmarker.create_from_options(options)
    except Exception as e:
        add_log(f"MediaPipe initialization failed: {e}", "CAMERA")
        cap.release()
        with state_lock:
            state["camera_active"] = False
        return

    min_distances = {"thumb": float('inf'), "index": float('inf'), "middle": float('inf'), "ring": float('inf'), "pinky": float('inf')}
    max_distances = {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0}
    ema_angles = {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0}
    EMA_ALPHA = 0.35

    fps_start = time.perf_counter()
    fps_frames = 0
    fps_val = 0.0

    add_log("Webcam tracking initialized and active", "CAMERA")

    while camera_should_run and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.03)
            continue

        fps_frames += 1
        elapsed = time.perf_counter() - fps_start
        if elapsed >= 1.0:
            fps_val = fps_frames / elapsed
            fps_frames = 0
            fps_start = time.perf_counter()
            with state_lock:
                state["camera_fps"] = round(fps_val, 1)

        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        timestamp_ms = int(time.perf_counter() * 1000)
        results = landmarker.detect_for_video(mp_image, timestamp_ms)

        h, w = frame.shape[:2]

        now = time.time()
        is_cooldown = now < state["cooldown_until"]

        if results.hand_landmarks:
            for hand_landmarks in results.hand_landmarks:
                # Draw skeleton points
                for lm in hand_landmarks:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 4, (0, 240, 255), -1)

                # Connect finger lines
                cv2.line(frame, (int(hand_landmarks[17].x * w), int(hand_landmarks[17].y * h)), (int(hand_landmarks[4].x * w), int(hand_landmarks[4].y * h)), (0, 200, 255), 2)
                cv2.line(frame, (int(hand_landmarks[0].x * w), int(hand_landmarks[0].y * h)), (int(hand_landmarks[8].x * w), int(hand_landmarks[8].y * h)), (0, 200, 255), 2)
                cv2.line(frame, (int(hand_landmarks[0].x * w), int(hand_landmarks[0].y * h)), (int(hand_landmarks[12].x * w), int(hand_landmarks[12].y * h)), (0, 200, 255), 2)
                cv2.line(frame, (int(hand_landmarks[0].x * w), int(hand_landmarks[0].y * h)), (int(hand_landmarks[16].x * w), int(hand_landmarks[16].y * h)), (0, 200, 255), 2)
                cv2.line(frame, (int(hand_landmarks[0].x * w), int(hand_landmarks[0].y * h)), (int(hand_landmarks[20].x * w), int(hand_landmarks[20].y * h)), (0, 200, 255), 2)

                distances = {
                    "thumb": calculate_distance(hand_landmarks[17], hand_landmarks[4]),
                    "index": calculate_distance(hand_landmarks[0], hand_landmarks[8]),
                    "middle": calculate_distance(hand_landmarks[0], hand_landmarks[12]),
                    "ring": calculate_distance(hand_landmarks[0], hand_landmarks[16]),
                    "pinky": calculate_distance(hand_landmarks[0], hand_landmarks[20]),
                }

                for finger in distances:
                    if distances[finger] < min_distances[finger]:
                        min_distances[finger] = distances[finger]
                    if distances[finger] > max_distances[finger]:
                        max_distances[finger] = distances[finger]

                raw_angles = {}
                for finger in distances:
                    span = max_distances[finger] - min_distances[finger]
                    if span == 0:
                        raw_angles[finger] = 0
                    else:
                        raw_angles[finger] = int((max_distances[finger] - distances[finger]) / span * 180)

                for finger in raw_angles:
                    ema_angles[finger] = int(EMA_ALPHA * raw_angles[finger] + (1.0 - EMA_ALPHA) * ema_angles[finger])

                # Update state servos if not locked in 2s HTTP cooldown
                if not is_cooldown:
                    with state_lock:
                        state["servos"]["thumb"] = max(0, min(180, ema_angles["thumb"]))
                        state["servos"]["index"] = max(0, min(180, ema_angles["index"]))
                        state["servos"]["middle"] = max(0, min(180, ema_angles["middle"]))
                        state["servos"]["ring"] = max(0, min(180, ema_angles["ring"]))
                        state["servos"]["pinky"] = max(0, min(180, ema_angles["pinky"]))
                        state["last_source"] = "Webcam Vision (MediaPipe)"
                        state["last_activity"] = f"Tracked: [{state['servos']['thumb']}°, {state['servos']['index']}°, {state['servos']['middle']}°, {state['servos']['ring']}°, {state['servos']['pinky']}°]"

                # Visual HUD overlays
                cv2.putText(frame, f"T:{ema_angles['thumb']:3d} I:{ema_angles['index']:3d} M:{ema_angles['middle']:3d} R:{ema_angles['ring']:3d} P:{ema_angles['pinky']:3d}",
                            (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2, cv2.LINE_AA)
        else:
            cv2.putText(frame, "Show hand to camera", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 165, 255), 2, cv2.LINE_AA)

        # Draw FPS and Status
        cv2.putText(frame, f"FPS: {fps_val:.1f}", (w - 110, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 240, 255), 2, cv2.LINE_AA)
        if is_cooldown:
            cv2.putText(frame, "PAUSED (COOLDOWN)", (w // 2 - 100, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 255), 2, cv2.LINE_AA)

        # Compress to JPEG for HTTP stream
        ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if ret:
            with camera_frame_lock:
                current_camera_frame = jpeg.tobytes()

        time.sleep(0.015)  # Throttle to ~35-40 FPS

    cap.release()
    with camera_frame_lock:
        current_camera_frame = None
    with state_lock:
        state["camera_active"] = False
    add_log("Webcam released and tracking stopped", "CAMERA")

def start_camera():
    global camera_thread, camera_should_run
    if camera_should_run:
        return
    camera_should_run = True
    with state_lock:
        state["camera_active"] = True
    camera_thread = threading.Thread(target=camera_worker_loop, daemon=True)
    camera_thread.start()

def stop_camera():
    global camera_should_run
    camera_should_run = False
    with state_lock:
        state["camera_active"] = False

# -------------------------------------------------------------
# Embedded Voice Recognition Worker (SpeechRecognition + Edge-TTS)
# -------------------------------------------------------------
async def synthesize_speech(text, out_path):
    communicate = edge_tts.Communicate(text, "en-US-JennyNeural")
    await communicate.save(str(out_path))

def speak(text):
    add_log(f"Spoken feedback: \"{text}\"", "VOICE")
    if not HAS_VOICE:
        return
    try:
        temp_file = BASE_DIR / f"tts_{int(time.time() * 1000)}.mp3"
        asyncio.run(synthesize_speech(text, temp_file))
        sys_name = platform.system()
        if sys_name == "Windows":
            try:
                os.startfile(str(temp_file))
            except Exception:
                pass
        elif sys_name == "Darwin":
            os.system(f"afplay \"{temp_file}\"")
        else:
            os.system(f"mpg123 \"{temp_file}\" 2>/dev/null || mplayer -quiet \"{temp_file}\" >/dev/null 2>&1")
    except Exception as e:
        print(f"TTS Error: {e}")

def voice_worker_loop():
    global voice_should_run
    if not HAS_VOICE:
        add_log("Voice mode unavailable: speech_recognition/edge_tts not installed", "VOICE")
        return

    recognizer = sr.Recognizer()
    add_log("Voice recognition worker active. Listening...", "VOICE")
    speak("Voice command station active")

    while voice_should_run:
        with state_lock:
            state["voice_status"] = "Listening for commands..."
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = recognizer.listen(source, timeout=3.5, phrase_time_limit=4.0)

            with state_lock:
                state["voice_status"] = "Recognizing speech..."

            text = recognizer.recognize_google(audio).lower().strip()
            add_log(f"Heard phrase: '{text}'", "VOICE")
            with state_lock:
                state["last_voice_text"] = text

            if "open" in text:
                set_gesture("open")
                speak("Hand opened")
            elif "close" in text or "fist" in text:
                set_gesture("fist")
                speak("Hand closed")
            elif "point" in text:
                set_gesture("point")
                speak("Pointing")
            elif "yo" in text and "sign" in text:
                set_gesture("yo")
                speak("Yo sign")
            elif "wave" in text or "name" in text:
                set_gesture("wave")
                speak("Waving")
            elif "stop" in text or "quit" in text or "exit" in text:
                speak("Stopping voice control")
                stop_voice()
                break

        except (sr.WaitTimeoutError, sr.UnknownValueError):
            with state_lock:
                state["voice_status"] = "Listening..."
        except Exception as e:
            with state_lock:
                state["voice_status"] = "Microphone standby"
            time.sleep(1.0)

    with state_lock:
        state["voice_active"] = False
        state["voice_status"] = "Idle"
    add_log("Voice recognition stopped", "VOICE")

def start_voice():
    global voice_thread, voice_should_run
    if voice_should_run:
        return
    voice_should_run = True
    with state_lock:
        state["voice_active"] = True
        state["voice_status"] = "Starting..."
    voice_thread = threading.Thread(target=voice_worker_loop, daemon=True)
    voice_thread.start()

def stop_voice():
    global voice_should_run
    voice_should_run = False
    with state_lock:
        state["voice_active"] = False
        state["voice_status"] = "Idle"

# -------------------------------------------------------------
# UDP Server Worker (Receives External Streams on Port 8888)
# -------------------------------------------------------------
def start_udp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    print(f"[*] Simulated ESP8266 UDP Server listening on port {UDP_PORT}...")
    while True:
        try:
            data, addr = sock.recvfrom(256)
            text = data.decode('utf-8', errors='ignore').strip()
            now = time.time()
            with state_lock:
                state["udp_packets_count"] += 1
                is_cooldown = now < state["cooldown_until"]
            
            if is_cooldown:
                continue

            parts = [p.strip() for p in text.split(",") if p.strip()]
            if len(parts) == 5:
                try:
                    angles = [int(p) for p in parts]
                    with state_lock:
                        state["servos"]["thumb"] = max(0, min(180, angles[0]))
                        state["servos"]["index"] = max(0, min(180, angles[1]))
                        state["servos"]["middle"] = max(0, min(180, angles[2]))
                        state["servos"]["ring"] = max(0, min(180, angles[3]))
                        state["servos"]["pinky"] = max(0, min(180, angles[4]))
                        state["last_source"] = "External UDP Stream"
                        state["last_activity"] = f"UDP Angles: [{angles[0]}°, {angles[1]}°, {angles[2]}°, {angles[3]}°, {angles[4]}°]"
                    if state["udp_packets_count"] % 20 == 0:
                        add_log(f"UDP datagram received: {text}", "UDP")
                except ValueError:
                    pass
        except Exception as e:
            print(f"UDP Error: {e}")

# -------------------------------------------------------------
# Unified HTTP Server Request Handler
# -------------------------------------------------------------
class UnifiedControlCenterHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress console clutter

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        with state_lock:
            state["http_requests_count"] += 1

        if path == "/api/state":
            now = time.time()
            elapsed = int(now - state["start_time"])
            hours = elapsed // 3600
            mins = (elapsed % 3600) // 60
            secs = elapsed % 60
            uptime_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

            with state_lock:
                cooldown_left = max(0.0, state["cooldown_until"] - now)
                resp_data = {
                    "servos": state["servos"],
                    "camera_active": state["camera_active"],
                    "camera_fps": state["camera_fps"],
                    "voice_active": state["voice_active"],
                    "voice_status": state["voice_status"],
                    "last_voice_text": state["last_voice_text"],
                    "last_source": state["last_source"],
                    "last_activity": state["last_activity"],
                    "udp_packets_count": state["udp_packets_count"],
                    "http_requests_count": state["http_requests_count"],
                    "uptime": uptime_str,
                    "cooldown_active": cooldown_left > 0,
                    "cooldown_seconds": round(cooldown_left, 1),
                    "logs": state["recent_logs"][:15]
                }
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(resp_data).encode('utf-8'))
            return

        elif path == "/video_feed":
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_cors_headers()
            self.end_headers()
            try:
                while camera_should_run:
                    with camera_frame_lock:
                        frame_bytes = current_camera_frame
                    if frame_bytes:
                        self.wfile.write(b'--frame\r\n'
                                         b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    time.sleep(0.03)
            except (ConnectionResetError, BrokenPipeError):
                pass
            return

        elif path == "/gesture":
            g_type = query.get("type", [""])[0]
            if g_type:
                set_gesture(g_type)
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"NICE")
            return

        elif path == "/controlAll":
            set_cooldown(2.0)
            thumb = query.get("thumb", [""])[0]
            index = query.get("index", [""])[0]
            middle = query.get("middle", [""])[0]
            ring = query.get("ring", [""])[0]
            pinky = query.get("pinky", [""])[0]
            with state_lock:
                if thumb != "": state["servos"]["thumb"] = max(0, min(180, int(thumb)))
                if index != "": state["servos"]["index"] = max(0, min(180, int(index)))
                if middle != "": state["servos"]["middle"] = max(0, min(180, int(middle)))
                if ring != "": state["servos"]["ring"] = max(0, min(180, int(ring)))
                if pinky != "": state["servos"]["pinky"] = max(0, min(180, int(pinky)))
                state["last_source"] = "HTTP /controlAll"
                state["last_activity"] = f"Manual Control: T{thumb} I{index} M{middle} R{ring} P{pinky}"
            add_log(f"/controlAll request: {state['servos']}", "HTTP")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"NICE")
            return

        elif path in ["/", "/controlGUI", "/simulator"]:
            self.render_unified_command_center()
            return

        else:
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        # Try JSON body first, then form urlencoded
        body = {}
        if post_data:
            try:
                body = json.loads(post_data)
            except Exception:
                body = urllib.parse.parse_qs(post_data)
                # Flatten single-item lists
                body = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in body.items()}

        if path == "/api/camera/start":
            start_camera()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "active": True}).encode('utf-8'))
            return

        elif path == "/api/camera/stop":
            stop_camera()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "stopped", "active": False}).encode('utf-8'))
            return

        elif path == "/api/voice/start":
            start_voice()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "active": True}).encode('utf-8'))
            return

        elif path == "/api/voice/stop":
            stop_voice()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "stopped", "active": False}).encode('utf-8'))
            return

        elif path == "/api/voice/command":
            cmd = body.get("command", "")
            if cmd:
                add_log(f"Manual text voice command: '{cmd}'", "VOICE")
                set_gesture(cmd)
                speak(f"Command executed: {cmd}")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "executed", "command": cmd}).encode('utf-8'))
            return

        elif path == "/api/servos":
            set_cooldown(2.0)
            with state_lock:
                for f in ["thumb", "index", "middle", "ring", "pinky"]:
                    if f in body:
                        state["servos"][f] = max(0, min(180, int(body[f])))
                state["last_source"] = "Dashboard Sliders"
                state["last_activity"] = f"Sliders: {state['servos']['thumb']}°, {state['servos']['index']}°, {state['servos']['middle']}°, {state['servos']['ring']}°, {state['servos']['pinky']}°"
            add_log(f"Interactive sliders updated: {state['servos']}", "SLIDER")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "updated", "servos": state["servos"]}).encode('utf-8'))
            return

        elif path == "/controlGUI":
            mode = body.get("mode", "manual")
            if mode == "manual":
                set_cooldown(2.0)
                thumb = int(body.get("thumb", 0))
                index = int(body.get("index", 0))
                middle = int(body.get("middle", 0))
                ring = int(body.get("ring", 0))
                pinky = int(body.get("pinky", 0))
                with state_lock:
                    state["servos"] = {
                        "thumb": max(0, min(180, thumb)),
                        "index": max(0, min(180, index)),
                        "middle": max(0, min(180, middle)),
                        "ring": max(0, min(180, ring)),
                        "pinky": max(0, min(180, pinky))
                    }
                    state["last_source"] = "Web GUI Form"
                    state["last_activity"] = f"Form: {thumb}°, {index}°, {middle}°, {ring}°, {pinky}°"
                add_log(f"Form submission: {state['servos']}", "HTTP")
            else:
                set_gesture(mode)

            self.render_unified_command_center()
            return
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def render_unified_command_center(self):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoboticHand - Unified Command Center</title>
    <style>
        :root {
            --bg-color: #090d16;
            --card-bg: #131c2e;
            --card-border: #1e293b;
            --accent-cyan: #00f0ff;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-amber: #f59e0b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --glow: rgba(0, 240, 255, 0.25);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
        body { background: var(--bg-color); color: var(--text-main); min-height: 100vh; padding: 18px; display: flex; flex-direction: column; align-items: center; }
        
        /* Header */
        header { width: 100%; max-width: 1400px; display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--card-border); }
        .logo-area { display: flex; align-items: center; gap: 12px; }
        .logo-icon { font-size: 28px; }
        h1 { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; background: linear-gradient(to right, #00f0ff, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .header-badges { display: flex; align-items: center; gap: 12px; }
        .badge { background: #1e293b; color: var(--text-muted); border: 1px solid #334155; padding: 5px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
        .badge.active { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(52, 211, 153, 0.3); }
        .pulse-dot { width: 8px; height: 8px; background: #34d399; border-radius: 50%; box-shadow: 0 0 8px #34d399; animation: pulse 1.8s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }

        /* Main Grid */
        .dashboard-grid { width: 100%; max-width: 1400px; display: grid; grid-template-columns: 1.15fr 1fr; gap: 20px; }
        @media (max-width: 1050px) { .dashboard-grid { grid-template-columns: 1fr; } }
        
        .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 14px; padding: 20px; display: flex; flex-direction: column; box-shadow: 0 8px 30px rgba(0,0,0,0.4); margin-bottom: 20px; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .card-title { font-size: 15px; font-weight: 700; color: var(--accent-cyan); text-transform: uppercase; letter-spacing: 0.8px; display: flex; align-items: center; gap: 8px; }
        
        /* Bionic Hand SVG Visualizer */
        .hand-stage { width: 100%; height: 350px; background: radial-gradient(circle at center, #111a2e 0%, #080c16 100%); border-radius: 10px; border: 1px solid #1e293b; display: flex; justify-content: center; align-items: center; position: relative; overflow: hidden; }
        svg.hand-svg { width: 100%; height: 100%; }

        /* Finger Meters */
        .meters-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 14px; }
        .meter-card { background: #0b1120; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px; text-align: center; }
        .meter-label { font-size: 11px; color: var(--text-muted); font-weight: 700; text-transform: uppercase; margin-bottom: 4px; }
        .meter-value { font-size: 16px; font-weight: 800; color: #fff; margin-bottom: 6px; }
        .bar-track { background: #1e293b; height: 50px; width: 12px; border-radius: 6px; margin: 0 auto; display: flex; flex-direction: column-reverse; overflow: hidden; }
        .bar-level { width: 100%; background: linear-gradient(to top, #00f0ff, #3b82f6); transition: height 0.08s ease-out; }

        /* Simulated OLED Screen */
        .oled-housing { background: #0d0d0d; padding: 12px; border-radius: 8px; border: 2px solid #222; box-shadow: inset 0 0 12px #000; width: 100%; max-width: 380px; margin: 0 auto; }
        .oled-display { background: #000; border: 1px solid #1c1c1c; border-radius: 4px; padding: 10px 14px; font-family: 'Consolas', 'Courier New', monospace; color: #38bdf8; font-size: 13px; line-height: 1.45; height: 105px; text-shadow: 0 0 5px rgba(56, 189, 248, 0.7); }
        
        /* Sliders Section */
        .slider-row { margin-bottom: 14px; }
        .slider-meta { display: flex; justify-content: space-between; font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 5px; }
        input[type="range"] { width: 100%; height: 6px; border-radius: 3px; background: #1e293b; accent-color: var(--accent-cyan); cursor: pointer; outline: none; }
        
        /* Button Styles */
        .btn { padding: 9px 16px; border-radius: 8px; font-size: 13px; font-weight: 700; border: none; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 8px; transition: all 0.2s; text-decoration: none; }
        .btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
        .btn-green { background: #059669; color: #fff; }
        .btn-red { background: #dc2626; color: #fff; }
        .btn-blue { background: #2563eb; color: #fff; }
        .btn-secondary { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; }
        .btn-secondary:hover { background: #334155; }
        
        /* Control Groups */
        .gesture-buttons { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-top: 10px; margin-bottom: 16px; }

        /* Embedded Camera Section */
        .video-box { width: 100%; height: 260px; background: #000; border-radius: 10px; border: 1px solid #1e293b; overflow: hidden; display: flex; justify-content: center; align-items: center; position: relative; }
        .video-placeholder { text-align: center; color: #64748b; font-size: 13px; }
        .video-placeholder-icon { font-size: 40px; margin-bottom: 10px; opacity: 0.6; }
        img#camera-stream { width: 100%; height: 100%; object-fit: cover; display: none; }
        
        /* Embedded Voice Section */
        .voice-card-body { display: flex; flex-direction: column; gap: 12px; }
        .voice-status-box { background: #0b1120; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; display: flex; align-items: center; gap: 12px; }
        .sound-wave { display: flex; align-items: center; gap: 3px; height: 24px; }
        .sound-wave span { width: 4px; height: 6px; background: #38bdf8; border-radius: 2px; }
        .sound-wave.active span { animation: wave 1s infinite ease-in-out; }
        .sound-wave.active span:nth-child(2) { animation-delay: 0.2s; }
        .sound-wave.active span:nth-child(3) { animation-delay: 0.4s; }
        .sound-wave.active span:nth-child(4) { animation-delay: 0.1s; }
        .sound-wave.active span:nth-child(5) { animation-delay: 0.3s; }
        @keyframes wave { 0%, 100% { height: 6px; } 50% { height: 22px; } }
        .transcript-text { font-size: 13px; color: #e2e8f0; font-style: italic; }
        
        /* Console Box */
        .console-container { background: #000; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; font-family: 'Consolas', monospace; font-size: 12px; color: #4ade80; height: 130px; overflow-y: auto; line-height: 1.5; }
        .console-line { margin-bottom: 3px; word-break: break-all; }
        .console-line.GESTURE { color: #38bdf8; }
        .console-line.CAMERA { color: #facc15; }
        .console-line.VOICE { color: #c084fc; }
        .console-line.SLIDER { color: #4ade80; }
    </style>
</head>
<body>

    <header>
        <div class="logo-area">
            <span class="logo-icon">🤖</span>
            <div>
                <h1>RoboticHand Command Center</h1>
                <div style="font-size: 11px; color: var(--text-muted);">Unified Multi-Modal Control Station • Team: Albert Toj Kayyalaparambil, Vivek Viswanath, Ronith Promy, Shifa Mariyam</div>
            </div>
        </div>
        <div class="header-badges">
            <div class="badge active" id="badge-system">
                <div class="pulse-dot"></div>
                ESP8266 Simulator Active
            </div>
            <div class="badge" id="badge-uptime">Uptime: 00:00:00</div>
            <div class="badge" id="badge-cooldown" style="color: #10b981;">UDP Ready</div>
        </div>
    </header>

    <div class="dashboard-grid">
        
        <!-- Left Column: Bionic Hand Model, OLED, and Live Logs -->
        <div>
            <!-- Bionic Hand Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">🖐️ Real-Time Bionic Hand Model</div>
                    <span id="label-source" style="font-size: 12px; color: var(--text-muted); font-weight: 600;">Source: Idle</span>
                </div>
                <div class="hand-stage">
                    <svg class="hand-svg" viewBox="0 0 400 350">
                        <!-- Palm chassis base -->
                        <rect x="130" y="190" width="140" height="130" rx="25" fill="#172338" stroke="#00f0ff" stroke-width="2.5" />
                        <!-- Palm core module accent -->
                        <circle cx="200" cy="255" r="30" fill="#0b1120" stroke="#334155" stroke-width="2" />
                        <text x="200" y="252" font-size="11" fill="#38bdf8" text-anchor="middle" font-weight="bold">ESP8266</text>
                        <text x="200" y="267" font-size="9" fill="#64748b" text-anchor="middle">5-DOF</text>
                        
                        <!-- Thumb (D0 / Pin 16) -->
                        <g id="joint-thumb" transform="translate(130, 240)">
                            <rect id="seg-thumb" x="-46" y="-13" width="46" height="26" rx="10" fill="#1e293b" stroke="#00f0ff" stroke-width="2" />
                            <circle cx="0" cy="0" r="8" fill="#00f0ff" />
                            <text x="-24" y="32" font-size="10" fill="#94a3b8" text-anchor="middle">Thumb</text>
                        </g>
                        
                        <!-- Index Finger (D3 / Pin 0) -->
                        <g id="joint-index" transform="translate(155, 190)">
                            <rect id="seg-index" x="-10" y="-85" width="20" height="85" rx="9" fill="#1e293b" stroke="#00f0ff" stroke-width="2" />
                            <circle cx="0" cy="0" r="7" fill="#00f0ff" />
                            <text x="0" y="-95" font-size="10" fill="#94a3b8" text-anchor="middle">Index</text>
                        </g>

                        <!-- Middle Finger (D5 / Pin 14) -->
                        <g id="joint-middle" transform="translate(185, 190)">
                            <rect id="seg-middle" x="-10" y="-95" width="20" height="95" rx="9" fill="#1e293b" stroke="#00f0ff" stroke-width="2" />
                            <circle cx="0" cy="0" r="7" fill="#00f0ff" />
                            <text x="0" y="-105" font-size="10" fill="#94a3b8" text-anchor="middle">Middle</text>
                        </g>

                        <!-- Ring Finger (D6 / Pin 12) -->
                        <g id="joint-ring" transform="translate(215, 190)">
                            <rect id="seg-ring" x="-10" y="-85" width="20" height="85" rx="9" fill="#1e293b" stroke="#00f0ff" stroke-width="2" />
                            <circle cx="0" cy="0" r="7" fill="#00f0ff" />
                            <text x="0" y="-95" font-size="10" fill="#94a3b8" text-anchor="middle">Ring</text>
                        </g>

                        <!-- Pinky Finger (D7 / Pin 13) -->
                        <g id="joint-pinky" transform="translate(245, 190)">
                            <rect id="seg-pinky" x="-9" y="-70" width="18" height="70" rx="9" fill="#1e293b" stroke="#00f0ff" stroke-width="2" />
                            <circle cx="0" cy="0" r="7" fill="#00f0ff" />
                            <text x="0" y="-80" font-size="10" fill="#94a3b8" text-anchor="middle">Pinky</text>
                        </g>
                    </svg>
                </div>

                <!-- Live Meters -->
                <div class="meters-grid">
                    <div class="meter-card">
                        <div class="meter-label">Thumb</div>
                        <div class="meter-value" id="val-t">0°</div>
                        <div class="bar-track"><div class="bar-level" id="bar-t" style="height:0%"></div></div>
                    </div>
                    <div class="meter-card">
                        <div class="meter-label">Index</div>
                        <div class="meter-value" id="val-i">0°</div>
                        <div class="bar-track"><div class="bar-level" id="bar-i" style="height:0%"></div></div>
                    </div>
                    <div class="meter-card">
                        <div class="meter-label">Middle</div>
                        <div class="meter-value" id="val-m">0°</div>
                        <div class="bar-track"><div class="bar-level" id="bar-m" style="height:0%"></div></div>
                    </div>
                    <div class="meter-card">
                        <div class="meter-label">Ring</div>
                        <div class="meter-value" id="val-r">0°</div>
                        <div class="bar-track"><div class="bar-level" id="bar-r" style="height:0%"></div></div>
                    </div>
                    <div class="meter-card">
                        <div class="meter-label">Pinky</div>
                        <div class="meter-value" id="val-p">0°</div>
                        <div class="bar-track"><div class="bar-level" id="bar-p" style="height:0%"></div></div>
                    </div>
                </div>
            </div>

            <!-- Virtual OLED Screen & Console -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">📟 SH1106 128x64 OLED Display (Simulated)</div>
                    <span style="font-size: 11px; color: var(--text-muted);">I2C Address: 0x3C</span>
                </div>
                <div class="oled-housing">
                    <div class="oled-display" id="oled-box">
                        <div>Servo Positions:</div>
                        <div id="oled-t">Thumb:  0°</div>
                        <div id="oled-i">Index:  0°</div>
                        <div id="oled-m">Middle: 0°</div>
                        <div id="oled-r">Ring:   0°</div>
                        <div id="oled-p">Pinky:  0°</div>
                    </div>
                </div>

                <div class="card-header" style="margin-top: 18px; margin-bottom: 8px;">
                    <div class="card-title" style="font-size: 13px;">📡 Live Event Log & Telemetry</div>
                </div>
                <div class="console-container" id="console-stream">
                    <div class="console-line">[00:00:00] Unified Command Center initialized on port 5000</div>
                </div>
            </div>
        </div>

        <!-- Right Column: Integrated Sliders, Embedded Camera, Embedded Voice -->
        <div>
            
            <!-- Manual Sliders & Gestures Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">🎚️ 5-Finger Slider Controls</div>
                    <span style="font-size: 12px; color: var(--accent-cyan); font-weight: 600;">Manual Override</span>
                </div>
                
                <div class="slider-row">
                    <div class="slider-meta"><span>Thumb</span><span id="slider-val-t">0°</span></div>
                    <input type="range" id="slider-t" min="0" max="180" value="0" oninput="onSliderMove()">
                </div>
                <div class="slider-row">
                    <div class="slider-meta"><span>Index</span><span id="slider-val-i">0°</span></div>
                    <input type="range" id="slider-i" min="0" max="180" value="0" oninput="onSliderMove()">
                </div>
                <div class="slider-row">
                    <div class="slider-meta"><span>Middle</span><span id="slider-val-m">0°</span></div>
                    <input type="range" id="slider-m" min="0" max="180" value="0" oninput="onSliderMove()">
                </div>
                <div class="slider-row">
                    <div class="slider-meta"><span>Ring</span><span id="slider-val-r">0°</span></div>
                    <input type="range" id="slider-r" min="0" max="180" value="0" oninput="onSliderMove()">
                </div>
                <div class="slider-row">
                    <div class="slider-meta"><span>Pinky</span><span id="slider-val-p">0°</span></div>
                    <input type="range" id="slider-p" min="0" max="180" value="0" oninput="onSliderMove()">
                </div>

                <div style="font-size: 12px; color: var(--text-muted); font-weight: 700; margin-top: 6px; margin-bottom: 6px;">QUICK GESTURE MACROS</div>
                <div class="gesture-buttons">
                    <button class="btn btn-secondary" onclick="triggerGesture('open')">🖐️ Open</button>
                    <button class="btn btn-secondary" onclick="triggerGesture('fist')">✊ Fist</button>
                    <button class="btn btn-secondary" onclick="triggerGesture('point')">👉 Point</button>
                    <button class="btn btn-secondary" onclick="triggerGesture('yo')">🤟 Yo</button>
                    <button class="btn btn-secondary" onclick="triggerGesture('wave')">👋 Wave</button>
                </div>
            </div>

            <!-- Embedded Computer Vision Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">📷 Hand Tracking (Computer Vision)</div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-green" id="btn-camera-start" onclick="toggleCamera(true)">▶️ Start Camera</button>
                        <button class="btn btn-red" id="btn-camera-stop" onclick="toggleCamera(false)" style="display: none;">⏹️ Stop Camera</button>
                    </div>
                </div>
                
                <div class="video-box" id="video-container">
                    <div class="video-placeholder" id="video-placeholder">
                        <div class="video-placeholder-icon">📷</div>
                        <div>Camera is currently <strong>Offline</strong></div>
                        <div style="font-size: 11px; margin-top: 4px;">Click <strong>"Start Camera"</strong> to activate real-time MediaPipe hand tracking</div>
                    </div>
                    <img id="camera-stream" src="" alt="Webcam Hand Tracking Stream" />
                </div>
            </div>

            <!-- Embedded Voice Recognition Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">🎤 Voice Command Station</div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-blue" id="btn-voice-start" onclick="toggleVoice(true)">🎤 Start Voice Mode</button>
                        <button class="btn btn-red" id="btn-voice-stop" onclick="toggleVoice(false)" style="display: none;">⏹️ Stop Voice Mode</button>
                    </div>
                </div>

                <div class="voice-card-body">
                    <div class="voice-status-box">
                        <div class="sound-wave" id="voice-waves">
                            <span></span><span></span><span></span><span></span><span></span>
                        </div>
                        <div style="flex: 1;">
                            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; font-weight: 700;">Status</div>
                            <div id="voice-status-text" style="font-size: 13px; font-weight: 600; color: #38bdf8;">Voice Mode Standing By</div>
                        </div>
                    </div>

                    <div style="background: #0b1120; border: 1px solid #1e293b; border-radius: 8px; padding: 10px;">
                        <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; font-weight: 700; margin-bottom: 4px;">Last Speech Recognized</div>
                        <div class="transcript-text" id="voice-transcript">"No command spoken yet"</div>
                    </div>

                    <div style="display: flex; gap: 8px; margin-top: 2px;">
                        <input type="text" id="manual-voice-input" placeholder="Type a voice command (e.g. open, fist, point, wave)..." style="flex: 1; padding: 8px 12px; background: #0b1120; border: 1px solid #334155; border-radius: 6px; color: #fff; font-size: 13px;" onkeydown="if(event.key==='Enter') sendManualVoiceCommand()">
                        <button class="btn btn-secondary" onclick="sendManualVoiceCommand()">Send</button>
                    </div>
                </div>
            </div>

        </div>

    </div>

    <script>
        let isUserDraggingSliders = false;
        let sliderTimeout = null;

        // Fetch state loop
        async function fetchState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                
                const s = data.servos;

                // Update Hand SVG rendering
                // Thumb rotates outward/inward
                const thumbAngle = (s.thumb / 180) * 45;
                document.getElementById('joint-thumb').setAttribute('transform', `translate(130, 240) rotate(${thumbAngle})`);
                
                // Fingers compress/curl
                function fingerScale(deg) { return 1 - (deg / 180) * 0.75; }
                document.getElementById('seg-index').setAttribute('transform', `scale(1, ${fingerScale(s.index)})`);
                document.getElementById('seg-middle').setAttribute('transform', `scale(1, ${fingerScale(s.middle)})`);
                document.getElementById('seg-ring').setAttribute('transform', `scale(1, ${fingerScale(s.ring)})`);
                document.getElementById('seg-pinky').setAttribute('transform', `scale(1, ${fingerScale(s.pinky)})`);

                // Update Metrics
                document.getElementById('val-t').innerText = s.thumb + '°';
                document.getElementById('val-i').innerText = s.index + '°';
                document.getElementById('val-m').innerText = s.middle + '°';
                document.getElementById('val-r').innerText = s.ring + '°';
                document.getElementById('val-p').innerText = s.pinky + '°';

                document.getElementById('bar-t').style.height = (s.thumb / 180 * 100) + '%';
                document.getElementById('bar-i').style.height = (s.index / 180 * 100) + '%';
                document.getElementById('bar-m').style.height = (s.middle / 180 * 100) + '%';
                document.getElementById('bar-r').style.height = (s.ring / 180 * 100) + '%';
                document.getElementById('bar-p').style.height = (s.pinky / 180 * 100) + '%';

                // Update Sliders if not actively being dragged by user
                if (!isUserDraggingSliders) {
                    document.getElementById('slider-t').value = s.thumb;
                    document.getElementById('slider-i').value = s.index;
                    document.getElementById('slider-m').value = s.middle;
                    document.getElementById('slider-r').value = s.ring;
                    document.getElementById('slider-p').value = s.pinky;

                    document.getElementById('slider-val-t').innerText = s.thumb + '°';
                    document.getElementById('slider-val-i').innerText = s.index + '°';
                    document.getElementById('slider-val-m').innerText = s.middle + '°';
                    document.getElementById('slider-val-r').innerText = s.ring + '°';
                    document.getElementById('slider-val-p').innerText = s.pinky + '°';
                }

                // Update Simulated OLED
                document.getElementById('oled-t').innerText = 'Thumb:  ' + s.thumb + '°';
                document.getElementById('oled-i').innerText = 'Index:  ' + s.index + '°';
                document.getElementById('oled-m').innerText = 'Middle: ' + s.middle + '°';
                document.getElementById('oled-r').innerText = 'Ring:   ' + s.ring + '°';
                document.getElementById('oled-p').innerText = 'Pinky:  ' + s.pinky + '°';

                // Update Headers & Labels
                document.getElementById('label-source').innerText = 'Source: ' + data.last_source;
                document.getElementById('badge-uptime').innerText = 'Uptime: ' + data.uptime;
                
                const cdBadge = document.getElementById('badge-cooldown');
                if (data.cooldown_active) {
                    cdBadge.style.color = '#f59e0b';
                    cdBadge.innerText = '⏳ Cooldown (' + data.cooldown_seconds + 's)';
                } else {
                    cdBadge.style.color = '#10b981';
                    cdBadge.innerText = '● UDP Ready';
                }

                // Update Camera UI State
                const camStream = document.getElementById('camera-stream');
                const camPlaceholder = document.getElementById('video-placeholder');
                const btnCamStart = document.getElementById('btn-camera-start');
                const btnCamStop = document.getElementById('btn-camera-stop');
                
                if (data.camera_active) {
                    btnCamStart.style.display = 'none';
                    btnCamStop.style.display = 'inline-flex';
                    camPlaceholder.style.display = 'none';
                    camStream.style.display = 'block';
                    if (!camStream.src || camStream.src === window.location.href) {
                        camStream.src = '/video_feed';
                    }
                } else {
                    btnCamStart.style.display = 'inline-flex';
                    btnCamStop.style.display = 'none';
                    camPlaceholder.style.display = 'block';
                    camStream.style.display = 'none';
                    camStream.src = '';
                }

                // Update Voice UI State
                const btnVoiceStart = document.getElementById('btn-voice-start');
                const btnVoiceStop = document.getElementById('btn-voice-stop');
                const waves = document.getElementById('voice-waves');
                const voiceStatusText = document.getElementById('voice-status-text');
                const transcript = document.getElementById('voice-transcript');

                if (data.voice_active) {
                    btnVoiceStart.style.display = 'none';
                    btnVoiceStop.style.display = 'inline-flex';
                    waves.className = 'sound-wave active';
                    voiceStatusText.innerText = data.voice_status || 'Listening...';
                } else {
                    btnVoiceStart.style.display = 'inline-flex';
                    btnVoiceStop.style.display = 'none';
                    waves.className = 'sound-wave';
                    voiceStatusText.innerText = 'Voice Mode Standby';
                }

                if (data.last_voice_text) {
                    transcript.innerText = `"${data.last_voice_text}"`;
                }

                // Update Console Logs
                if (data.logs && data.logs.length > 0) {
                    const consoleEl = document.getElementById('console-stream');
                    consoleEl.innerHTML = data.logs.map(l => {
                        let cat = "INFO";
                        if (l.includes("[GESTURE]")) cat = "GESTURE";
                        else if (l.includes("[CAMERA]")) cat = "CAMERA";
                        else if (l.includes("[VOICE]")) cat = "VOICE";
                        else if (l.includes("[SLIDER]")) cat = "SLIDER";
                        return `<div class="console-line ${cat}">${l}</div>`;
                    }).join('');
                }

            } catch (e) {
                console.error("State refresh failed:", e);
            }
        }

        // Slider interaction
        function onSliderMove() {
            isUserDraggingSliders = true;
            clearTimeout(sliderTimeout);
            
            const t = parseInt(document.getElementById('slider-t').value);
            const i = parseInt(document.getElementById('slider-i').value);
            const m = parseInt(document.getElementById('slider-m').value);
            const r = parseInt(document.getElementById('slider-r').value);
            const p = parseInt(document.getElementById('slider-p').value);

            document.getElementById('slider-val-t').innerText = t + '°';
            document.getElementById('slider-val-i').innerText = i + '°';
            document.getElementById('slider-val-m').innerText = m + '°';
            document.getElementById('slider-val-r').innerText = r + '°';
            document.getElementById('slider-val-p').innerText = p + '°';

            fetch('/api/servos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ thumb: t, index: i, middle: m, ring: r, pinky: p })
            });

            sliderTimeout = setTimeout(() => {
                isUserDraggingSliders = false;
            }, 800);
        }

        // Macro Gesture trigger
        async function triggerGesture(type) {
            try {
                await fetch('/gesture?type=' + type);
            } catch(e) {
                console.error(e);
            }
        }

        // Camera Toggle
        async function toggleCamera(start) {
            try {
                const endpoint = start ? '/api/camera/start' : '/api/camera/stop';
                await fetch(endpoint, { method: 'POST' });
            } catch(e) {
                console.error(e);
            }
        }

        // Voice Toggle
        async function toggleVoice(start) {
            try {
                const endpoint = start ? '/api/voice/start' : '/api/voice/stop';
                await fetch(endpoint, { method: 'POST' });
            } catch(e) {
                console.error(e);
            }
        }

        // Manual Voice Command Input
        async function sendManualVoiceCommand() {
            const input = document.getElementById('manual-voice-input');
            const cmd = input.value.trim();
            if (!cmd) return;
            try {
                await fetch('/api/voice/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: cmd })
                });
                input.value = '';
            } catch(e) {
                console.error(e);
            }
        }

        // Polling loop
        setInterval(fetchState, 140);
        fetchState();
    </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

def run_servers():
    udp_thread = threading.Thread(target=start_udp_server, daemon=True)
    udp_thread.start()

    with socketserver.ThreadingTCPServer(("0.0.0.0", HTTP_PORT), UnifiedControlCenterHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"============================================================")
        print(f"  RoboticHand Unified Command Center Active!")
        print(f"  Dashboard: http://localhost:{HTTP_PORT}/")
        print(f"  Embedded Camera: MediaPipe + OpenCV (toggle inside GUI)")
        print(f"  Embedded Voice:  SpeechRecognition (toggle inside GUI)")
        print(f"  Simulated UDP:   Port {UDP_PORT}")
        print(f"============================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            stop_camera()
            stop_voice()
            print("\nShutting down Unified Command Center.")

if __name__ == "__main__":
    run_servers()

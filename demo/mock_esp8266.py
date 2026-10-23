"""
ESP8266 Hardware Simulator & Visualizer for RoboticHand
Simulates:
1. UDP Server on port 8888 (receives real-time vision tracking from app.py)
2. HTTP Server on port 5000:
   - /controlGUI (ESP8266 on-device web sliders & gestures)
   - /gesture?type=... (HTTP endpoint used by voice_control.py)
   - /controlAll?thumb=... (HTTP endpoint for programmatic finger control)
   - /api/state (Live JSON polling endpoint)
   - / (Interactive Real-Time Robotic Hand Visualizer & Test Console)
"""

import http.server
import socket
import socketserver
import threading
import time
import json
import urllib.parse

HTTP_PORT = 5000
UDP_PORT = 8888

# State store mirroring ESP8266 variables
state = {
    "servos": {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0},
    "last_source": "System Initialized",
    "last_activity": "Waiting for commands...",
    "udp_packets_count": 0,
    "http_requests_count": 0,
    "cooldown_until": 0,
    "start_time": time.time(),
    "recent_logs": []
}

state_lock = threading.Lock()

def add_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    with state_lock:
        state["recent_logs"].insert(0, f"[{timestamp}] {msg}")
        if len(state["recent_logs"]) > 25:
            state["recent_logs"].pop()

def set_cooldown(duration_sec=2.0):
    with state_lock:
        state["cooldown_until"] = time.time() + duration_sec

def set_gesture(gesture_name):
    set_cooldown(2.0)
    name = gesture_name.lower()
    add_log(f"HTTP Gesture Triggered: '{name}'")
    
    if name == "open":
        with state_lock:
            state["servos"] = {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0}
            state["last_source"] = "Voice / Web Gesture"
            state["last_activity"] = "Gesture: Hand Open"
    elif name in ["close", "fist"]:
        with state_lock:
            state["servos"] = {"thumb": 180, "index": 180, "middle": 180, "ring": 180, "pinky": 180}
            state["last_source"] = "Voice / Web Gesture"
            state["last_activity"] = "Gesture: Fist / Closed"
    elif name == "point":
        with state_lock:
            state["servos"] = {"thumb": 180, "index": 0, "middle": 180, "ring": 180, "pinky": 180}
            state["last_source"] = "Voice / Web Gesture"
            state["last_activity"] = "Gesture: Point"
    elif name == "yo":
        with state_lock:
            state["servos"] = {"thumb": 0, "index": 0, "middle": 180, "ring": 180, "pinky": 0}
            state["last_source"] = "Voice / Web Gesture"
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
                    state["last_activity"] = "Waving..."
                time.sleep(0.12)
            add_log("Wave animation completed")
        threading.Thread(target=run_wave_animation, daemon=True).start()

# UDP Server Worker
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
                add_log(f"UDP packet ignored (in 2s HTTP cooldown): {text}")
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
                        state["last_source"] = "Vision Tracking (UDP)"
                        state["last_activity"] = f"Tracked: [{angles[0]}°, {angles[1]}°, {angles[2]}°, {angles[3]}°, {angles[4]}°]"
                    if state["udp_packets_count"] % 10 == 0:
                        add_log(f"UDP Vision Packet: {text}")
                except ValueError:
                    pass
        except Exception as e:
            print(f"UDP Error: {e}")

# HTTP Request Handler
class MockESPHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress verbose standard output
        pass

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
                state["last_activity"] = f"Manual All: T{thumb} I{index} M{middle} R{ring} P{pinky}"
            add_log(f"/controlAll: T:{thumb} I:{index} M:{middle} R:{ring} P:{pinky}")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"NICE")
            return

        elif path == "/controlGUI":
            self.render_original_control_gui()
            return

        elif path == "/" or path == "/simulator":
            self.render_interactive_simulator()
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
        form_data = urllib.parse.parse_qs(post_data)

        if path == "/controlGUI":
            mode = form_data.get("mode", ["manual"])[0]
            if mode == "manual":
                set_cooldown(2.0)
                thumb = int(form_data.get("thumb", [0])[0])
                index = int(form_data.get("index", [0])[0])
                middle = int(form_data.get("middle", [0])[0])
                ring = int(form_data.get("ring", [0])[0])
                pinky = int(form_data.get("pinky", [0])[0])
                with state_lock:
                    state["servos"] = {
                        "thumb": max(0, min(180, thumb)),
                        "index": max(0, min(180, index)),
                        "middle": max(0, min(180, middle)),
                        "ring": max(0, min(180, ring)),
                        "pinky": max(0, min(180, pinky))
                    }
                    state["last_source"] = "Web GUI (Manual Sliders)"
                    state["last_activity"] = f"Sliders: {thumb}°, {index}°, {middle}°, {ring}°, {pinky}°"
                add_log(f"Web GUI Sliders Applied: {state['servos']}")
            else:
                set_gesture(mode)

            self.render_original_control_gui()
            return
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def render_original_control_gui(self):
        with state_lock:
            t = state["servos"]["thumb"]
            i = state["servos"]["index"]
            m = state["servos"]["middle"]
            r = state["servos"]["ring"]
            p = state["servos"]["pinky"]

        # Exact HTML reproduction of ESP8266 /controlGUI firmware code
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP8266 Responsive Form (Simulated)</title>
    <style>
        body {{font-family: Arial, sans-serif;margin: 0;padding: 20px;display: flex;flex-direction: column;justify-content: center;align-items: center;min-height: 100vh;background-color: #f0f0f0;}}
        .top-nav {{margin-bottom: 15px; font-weight: bold;}}
        .top-nav a {{color: #007bff; text-decoration: none;}}
        form {{background: #ffffff;padding: 25px;border-radius: 8px;box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);width: 100%;max-width: 420px;box-sizing: border-box;}}
        h2 {{text-align: center;margin-top: 0;margin-bottom: 20px;color: #333;}}
        label {{display: block;margin-bottom: 5px;font-weight: bold;color: #555;font-size: 14px;}}
        input[type="range"] {{width: 100%;margin-bottom: 5px;accent-color: #007BFF;}}
        output.out {{display: block; text-align: right; font-weight: bold; color: #007BFF; margin-bottom: 12px; font-size: 14px;}}
        button[type="submit"] {{width: 100%;background-color: #007BFF;color: white;padding: 12px;border: none;border-radius: 5px;cursor: pointer;font-size: 16px;font-weight: bold;transition: background-color 0.2s;}}
        button[type="submit"]:hover {{background-color: #0056b3;}}
        select {{width: 100%;padding: 10px;margin-bottom: 20px;border: 1px solid #ccc;border-radius: 5px;font-size: 1rem;background: #fff;}}
        #sliderSection {{display: block;}}
        #sliderSection.hidden {{display: none;}}
        .badge {{display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; background: #e0f2fe; color: #0369a1; margin-bottom: 15px; text-align: center; width: 100%; box-sizing: border-box;}}
    </style>
    <script>
        function toggleSliders(){{
            var mode = document.getElementById('modeSelect').value;
            document.getElementById('sliderSection').className = mode === 'manual' ? '' : 'hidden';
        }}
    </script>
</head>
<body>
    <div class="top-nav">
        <a href="/">⬅️ Open Real-Time Hand Simulator & Dashboard</a>
    </div>
    <form id="valueForm" method="post" action="/controlGUI">
        <h2>🤖 Robotic Hand Control</h2>
        <div class="badge">Simulated ESP8266 On-Device Web Server</div>
        <label for="mode">Mode:</label>
        <select id="modeSelect" name="mode" onchange="toggleSliders()">
            <option value="manual">Manual (Sliders)</option>
            <option value="open">Open Hand</option>
            <option value="close">Close Hand</option>
            <option value="fist">Make Fist</option>
            <option value="point">Point Finger</option>
            <option value="yo">Yo Sign</option>
            <option value="wave">Wave Gesture</option>
        </select>
        <div id="sliderSection">
            <label for="thumb">Thumb (0-180°):</label>
            <input type="range" id="thumb" name="thumb" min="0" max="180" value="{t}" oninput="this.nextElementSibling.value = this.value + '°'">
            <output class="out">{t}°</output>
            
            <label for="index">Index (0-180°):</label>
            <input type="range" id="index" name="index" min="0" max="180" value="{i}" oninput="this.nextElementSibling.value = this.value + '°'">
            <output class="out">{i}°</output>
            
            <label for="middle">Middle (0-180°):</label>
            <input type="range" id="middle" name="middle" min="0" max="180" value="{m}" oninput="this.nextElementSibling.value = this.value + '°'">
            <output class="out">{m}°</output>
            
            <label for="ring">Ring (0-180°):</label>
            <input type="range" id="ring" name="ring" min="0" max="180" value="{r}" oninput="this.nextElementSibling.value = this.value + '°'">
            <output class="out">{r}°</output>
            
            <label for="pinky">Pinky (0-180°):</label>
            <input type="range" id="pinky" name="pinky" min="0" max="180" value="{p}" oninput="this.nextElementSibling.value = this.value + '°'">
            <output class="out">{p}°</output>
        </div>
        <button type="submit">Apply Position</button>
    </form>
</body>
</html>"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def render_interactive_simulator(self):
        # Interactive live real-time simulation dashboard with live animated bionic hand,
        # simulated OLED display, real-time packet log, and gesture buttons!
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoboticHand - Interactive Live Simulator & Test Lab</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --accent: #38bdf8;
            --accent-glow: rgba(56, 189, 248, 0.3);
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
            --border: #334155;
            --success: #10b981;
            --warning: #f59e0b;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
        body { background: var(--bg-color); color: var(--text-main); min-height: 100vh; padding: 20px; display: flex; flex-direction: column; align-items: center; }
        header { width: 100%; max-width: 1200px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
        h1 { font-size: 24px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 10px; }
        .status-badge { background: #064e3b; color: #34d399; padding: 6px 14px; border-radius: 999px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
        .pulse { width: 8px; height: 8px; background: #34d399; border-radius: 50%; box-shadow: 0 0 10px #34d399; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 0.4; } 50% { opacity: 1; } 100% { opacity: 0.4; } }
        
        .grid-container { width: 100%; max-width: 1200px; display: grid; grid-template-columns: 1.2fr 1fr; gap: 24px; }
        @media (max-width: 900px) { .grid-container { grid-template-columns: 1fr; } }
        
        .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; flex-direction: column; box-shadow: 0 8px 24px rgba(0,0,0,0.3); }
        .card-title { font-size: 16px; font-weight: 600; color: var(--accent); margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
        
        /* Interactive 2D Bionic Hand Visualizer */
        .hand-visualizer { width: 100%; height: 360px; background: #090d16; border-radius: 8px; position: relative; border: 1px solid #1e293b; overflow: hidden; display: flex; justify-content: center; align-items: center; }
        svg.hand-svg { width: 100%; height: 100%; }

        /* Simulated OLED Screen */
        .oled-bezel { background: #111; padding: 12px; border-radius: 8px; border: 3px solid #222; box-shadow: inset 0 0 10px #000; width: 100%; max-width: 340px; margin: 0 auto 20px auto; }
        .oled-screen { background: #000; border: 1px solid #1a1a1a; border-radius: 4px; padding: 10px 14px; font-family: 'Courier New', Courier, monospace; color: #7dd3fc; font-size: 13px; line-height: 1.4; height: 110px; text-shadow: 0 0 4px #0284c7; }
        
        /* Sliders and Gauges */
        .finger-meters { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 15px; }
        .meter-box { background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 10px; text-align: center; }
        .meter-name { font-size: 12px; color: var(--text-sub); text-transform: uppercase; font-weight: 700; margin-bottom: 6px; }
        .meter-val { font-size: 18px; font-weight: 700; color: #fff; margin-bottom: 6px; }
        .meter-bar-container { background: #1e293b; height: 60px; width: 14px; border-radius: 7px; margin: 0 auto; display: flex; flex-direction: column-reverse; overflow: hidden; }
        .meter-bar-fill { width: 100%; background: linear-gradient(to top, #38bdf8, #818cf8); transition: height 0.1s ease-out; }
        
        /* Quick Controls */
        .btn-group { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 16px; }
        .btn { background: #2563eb; color: #fff; border: none; padding: 10px; border-radius: 6px; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s; text-align: center; text-decoration: none; }
        .btn:hover { background: #1d4ed8; transform: translateY(-1px); }
        .btn-secondary { background: #334155; }
        .btn-secondary:hover { background: #475569; }
        .btn-highlight { background: #0284c7; }
        .btn-highlight:hover { background: #0369a1; }
        
        /* Live Logs Console */
        .console-box { background: #000; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; color: #a3e635; height: 150px; overflow-y: auto; line-height: 1.5; }
        .console-line { margin-bottom: 4px; word-break: break-all; }
        
        .info-pill { font-size: 12px; color: var(--text-sub); margin-top: 8px; display: flex; justify-content: space-between; }
    </style>
</head>
<body>

    <header>
        <h1>🤖 RoboticHand Hardware Simulator</h1>
        <div class="status-badge">
            <div class="pulse"></div>
            Simulated NodeMCU ESP8266 Active
        </div>
    </header>

    <div class="grid-container">
        <!-- Left Column: Visual Hand & OLED -->
        <div class="card">
            <div class="card-title">🖐️ Real-Time Bionic Hand Model</div>
            <div class="hand-visualizer">
                <svg class="hand-svg" viewBox="0 0 400 350">
                    <!-- Palm base -->
                    <rect x="130" y="190" width="140" height="130" rx="25" fill="#1e293b" stroke="#38bdf8" stroke-width="3" />
                    <!-- Palm mechanical accents -->
                    <circle cx="200" cy="255" r="28" fill="#0f172a" stroke="#475569" stroke-width="2" />
                    <text x="200" y="260" font-size="11" fill="#94a3b8" text-anchor="middle" font-weight="bold">ESP8266</text>
                    
                    <!-- Thumb (D0) -->
                    <g id="thumb-joint" transform="translate(130, 240)">
                        <rect id="thumb-seg1" x="-45" y="-14" width="45" height="24" rx="10" fill="#334155" stroke="#38bdf8" stroke-width="2" />
                        <circle cx="0" cy="0" r="8" fill="#38bdf8" />
                        <text x="-25" y="32" font-size="10" fill="#94a3b8" text-anchor="middle">Thumb</text>
                    </g>
                    
                    <!-- Index Finger (D3) -->
                    <g id="index-joint" transform="translate(155, 190)">
                        <rect id="index-seg" x="-10" y="-85" width="20" height="85" rx="9" fill="#334155" stroke="#38bdf8" stroke-width="2" />
                        <circle cx="0" cy="0" r="7" fill="#38bdf8" />
                        <text x="0" y="-95" font-size="10" fill="#94a3b8" text-anchor="middle">Index</text>
                    </g>

                    <!-- Middle Finger (D5) -->
                    <g id="middle-joint" transform="translate(185, 190)">
                        <rect id="middle-seg" x="-10" y="-95" width="20" height="95" rx="9" fill="#334155" stroke="#38bdf8" stroke-width="2" />
                        <circle cx="0" cy="0" r="7" fill="#38bdf8" />
                        <text x="0" y="-105" font-size="10" fill="#94a3b8" text-anchor="middle">Middle</text>
                    </g>

                    <!-- Ring Finger (D6) -->
                    <g id="ring-joint" transform="translate(215, 190)">
                        <rect id="ring-seg" x="-10" y="-85" width="20" height="85" rx="9" fill="#334155" stroke="#38bdf8" stroke-width="2" />
                        <circle cx="0" cy="0" r="7" fill="#38bdf8" />
                        <text x="0" y="-95" font-size="10" fill="#94a3b8" text-anchor="middle">Ring</text>
                    </g>

                    <!-- Pinky Finger (D7) -->
                    <g id="pinky-joint" transform="translate(245, 190)">
                        <rect id="pinky-seg" x="-9" y="-70" width="18" height="70" rx="9" fill="#334155" stroke="#38bdf8" stroke-width="2" />
                        <circle cx="0" cy="0" r="7" fill="#38bdf8" />
                        <text x="0" y="-80" font-size="10" fill="#94a3b8" text-anchor="middle">Pinky</text>
                    </g>
                </svg>
            </div>

            <!-- Finger Metrics -->
            <div class="finger-meters">
                <div class="meter-box">
                    <div class="meter-name">Thumb</div>
                    <div class="meter-val" id="val-thumb">0°</div>
                    <div class="meter-bar-container"><div class="meter-bar-fill" id="bar-thumb" style="height:0%"></div></div>
                </div>
                <div class="meter-box">
                    <div class="meter-name">Index</div>
                    <div class="meter-val" id="val-index">0°</div>
                    <div class="meter-bar-container"><div class="meter-bar-fill" id="bar-index" style="height:0%"></div></div>
                </div>
                <div class="meter-box">
                    <div class="meter-name">Middle</div>
                    <div class="meter-val" id="val-middle">0°</div>
                    <div class="meter-bar-container"><div class="meter-bar-fill" id="bar-middle" style="height:0%"></div></div>
                </div>
                <div class="meter-box">
                    <div class="meter-name">Ring</div>
                    <div class="meter-val" id="val-ring">0°</div>
                    <div class="meter-bar-container"><div class="meter-bar-fill" id="bar-ring" style="height:0%"></div></div>
                </div>
                <div class="meter-box">
                    <div class="meter-name">Pinky</div>
                    <div class="meter-val" id="val-pinky">0°</div>
                    <div class="meter-bar-container"><div class="meter-bar-fill" id="bar-pinky" style="height:0%"></div></div>
                </div>
            </div>
            
            <div class="info-pill">
                <span id="active-source">Source: Idle</span>
                <span id="udp-counter">UDP Packets: 0</span>
            </div>
        </div>

        <!-- Right Column: Simulated OLED, Controls & Console -->
        <div class="card">
            <div class="card-title">📟 SH1106 128x64 OLED Display (Simulated)</div>
            <div class="oled-bezel">
                <div class="oled-screen" id="oled-content">
                    <div>Servo Motors:</div>
                    <div id="oled-thumb">Thumb:  0</div>
                    <div id="oled-index">Index:  0</div>
                    <div id="oled-mid">Middle: 0</div>
                    <div id="oled-ring">Ring:   0</div>
                    <div id="oled-pinky">Pinky:  0</div>
                </div>
            </div>

            <div class="card-title">⚡ Quick Gesture Presets</div>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="sendGesture('open')">🖐️ Open</button>
                <button class="btn btn-secondary" onclick="sendGesture('fist')">✊ Fist</button>
                <button class="btn btn-secondary" onclick="sendGesture('point')">👉 Point</button>
                <button class="btn btn-secondary" onclick="sendGesture('yo')">🤟 Yo Sign</button>
                <button class="btn btn-secondary" onclick="sendGesture('wave')">👋 Wave</button>
                <a class="btn btn-highlight" href="/controlGUI" target="_blank">🌐 Web GUI</a>
            </div>

            <div class="card-title">📡 Live Event Stream & Network Monitor</div>
            <div class="console-box" id="console-log">
                <div class="console-line">[00:00:00] Simulated ESP8266 ready on HTTP 5000 & UDP 8888</div>
            </div>
            
            <div class="info-pill" style="margin-top: 10px;">
                <span id="uptime-display">Uptime: 00:00:00</span>
                <span id="cooldown-badge" style="color: #10b981;">● UDP Ready</span>
            </div>
        </div>
    </div>

    <script>
        async function sendGesture(type) {
            try {
                await fetch('/gesture?type=' + type);
            } catch(e) {
                console.error(e);
            }
        }

        async function updateState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                
                const s = data.servos;
                document.getElementById('val-thumb').innerText = s.thumb + '°';
                document.getElementById('val-index').innerText = s.index + '°';
                document.getElementById('val-middle').innerText = s.middle + '°';
                document.getElementById('val-ring').innerText = s.ring + '°';
                document.getElementById('val-pinky').innerText = s.pinky + '°';

                document.getElementById('bar-thumb').style.height = (s.thumb / 180 * 100) + '%';
                document.getElementById('bar-index').style.height = (s.index / 180 * 100) + '%';
                document.getElementById('bar-middle').style.height = (s.middle / 180 * 100) + '%';
                document.getElementById('bar-ring').style.height = (s.ring / 180 * 100) + '%';
                document.getElementById('bar-pinky').style.height = (s.pinky / 180 * 100) + '%';

                // Animate SVG fingers: 0 deg = straight, 180 deg = curled
                // Thumb rotates
                const thumbAngle = (s.thumb / 180) * 45;
                document.getElementById('thumb-joint').setAttribute('transform', `translate(130, 240) rotate(${thumbAngle})`);
                
                // Fingers compress/curls
                function fingerScale(deg) { return 1 - (deg / 180) * 0.75; }
                document.getElementById('index-seg').setAttribute('transform', `scale(1, ${fingerScale(s.index)})`);
                document.getElementById('middle-seg').setAttribute('transform', `scale(1, ${fingerScale(s.middle)})`);
                document.getElementById('ring-seg').setAttribute('transform', `scale(1, ${fingerScale(s.ring)})`);
                document.getElementById('pinky-seg').setAttribute('transform', `scale(1, ${fingerScale(s.pinky)})`);

                // Update OLED screen
                document.getElementById('oled-thumb').innerText = 'Thumb:  ' + s.thumb;
                document.getElementById('oled-index').innerText = 'Index:  ' + s.index;
                document.getElementById('oled-mid').innerText   = 'Middle: ' + s.middle;
                document.getElementById('oled-ring').innerText  = 'Ring:   ' + s.ring;
                document.getElementById('oled-pinky').innerText = 'Pinky:  ' + s.pinky;

                // Update Badges & Counters
                document.getElementById('active-source').innerText = 'Source: ' + data.last_source;
                document.getElementById('udp-counter').innerText = 'UDP Packets: ' + data.udp_packets_count;
                document.getElementById('uptime-display').innerText = 'Uptime: ' + data.uptime;
                
                const cdBadge = document.getElementById('cooldown-badge');
                if (data.cooldown_active) {
                    cdBadge.style.color = '#f59e0b';
                    cdBadge.innerText = '⏳ Cooldown (' + data.cooldown_seconds + 's)';
                } else {
                    cdBadge.style.color = '#10b981';
                    cdBadge.innerText = '● UDP Active';
                }

                // Update Console Logs
                if (data.logs && data.logs.length > 0) {
                    const consoleEl = document.getElementById('console-log');
                    consoleEl.innerHTML = data.logs.map(l => `<div class="console-line">${l}</div>`).join('');
                }

            } catch(e) {
                console.error("State poll failed:", e);
            }
        }

        setInterval(updateState, 150);
        updateState();
    </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

def run_servers():
    udp_thread = threading.Thread(target=start_udp_server, daemon=True)
    udp_thread.start()

    with socketserver.ThreadingTCPServer(("0.0.0.0", HTTP_PORT), MockESPHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"[*] Simulated ESP8266 Web Server running at http://localhost:{HTTP_PORT}/")
        print(f"[*] Original Web GUI available at http://localhost:{HTTP_PORT}/controlGUI")
        print(f"[*] Real-Time Interactive Simulator at http://localhost:{HTTP_PORT}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down simulated server.")

if __name__ == "__main__":
    run_servers()

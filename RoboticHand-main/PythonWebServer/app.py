import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import math
import socket
import numpy as np
import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Resolve base paths relative to this script file
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
MODEL_PATH = BASE_DIR / "hand_landmarker.task"

# Load environment configuration using python-dotenv
load_dotenv(dotenv_path=ENV_PATH)

ESP_IP = os.environ.get("ESP_IP", "192.168.4.1")
UDP_PORT = int(os.environ.get("UDP_PORT", 8888))

print(f"[INFO] Streaming target configured to ESP8266: {ESP_IP}:{UDP_PORT}")

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"Model file not found at: {MODEL_PATH}")

BaseOptions = python.BaseOptions
HandLandmarker = vision.HandLandmarker
HandLandmarkerOptions = vision.HandLandmarkerOptions

def calculate_distance(point1, point2):
    return math.sqrt((point1.x - point2.x)**2 + (point1.y - point2.y)**2 + (point1.z - point2.z)**2)

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("[ERROR] Could not open webcam (index 0). Please check camera connections.")
    exit(1)

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
    num_hands=1,
    running_mode=vision.RunningMode.VIDEO)
hand_landmarker = HandLandmarker.create_from_options(options)

counterForTimer = 0
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

min_distances = {"thumb": float('inf'), "index": float('inf'), "middle": float('inf'), "ring": float('inf'), "pinky": float('inf')}
max_distances = {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0}

# EMA (Exponential Moving Average) smoothing for servo angles
# Lower alpha = more smoothing; higher alpha = more responsive
EMA_ALPHA = 0.35
ema_angles = {"thumb": 90, "index": 90, "middle": 90, "ring": 90, "pinky": 90}

# FPS tracking
fps_start_time = time.perf_counter()
fps_counter = 0
fps_display = 0.0

print("[INFO] Hand tracking started. Show hand to camera. Press 'q' to quit.")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("[WARNING] Failed to capture frame. Exiting.")
        break

    # FPS tracking
    fps_counter += 1
    elapsed = time.perf_counter() - fps_start_time
    if elapsed >= 1.0:
        fps_display = fps_counter / elapsed
        fps_counter = 0
        fps_start_time = time.perf_counter()

    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    # FIX: Use wall-clock timestamp (milliseconds) for reliable monotonic timestamps
    # cap.get(cv2.CAP_PROP_POS_MSEC) is unreliable for live webcam input
    timestamp_ms = int(time.perf_counter() * 1000)
    results = hand_landmarker.detect_for_video(mp_image, timestamp_ms)

    h, w = frame.shape[:2]

    if results.hand_landmarks:
        for hand_landmarks in results.hand_landmarks:
            # Draw all landmark dots
            for i in range(len(hand_landmarks)):
                landmark = hand_landmarks[i]
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                cv2.circle(frame, (x, y), 3, (0, 0, 139), -1)

            # Draw palm-to-thumb line (correct: landmarks 17 and 4)
            cv2.line(frame,
                     (int(hand_landmarks[17].x * w), int(hand_landmarks[17].y * h)),
                     (int(hand_landmarks[4].x * w),  int(hand_landmarks[4].y * h)),
                     (0, 0, 139), 2)

            # FIX: Draw wrist-to-fingertip lines using correct point format:
            # cv2.line(img, pt1=(x1,y1), pt2=(x2,y2), ...)
            # Previous code was WRONG: pt1=(x1,x2), pt2=(y1,y2)

            # Wrist (0) to Index tip (8)
            cv2.line(frame,
                     (int(hand_landmarks[0].x * w), int(hand_landmarks[0].y * h)),
                     (int(hand_landmarks[8].x * w), int(hand_landmarks[8].y * h)),
                     (0, 0, 139), 2)

            # Wrist (0) to Middle tip (12)
            cv2.line(frame,
                     (int(hand_landmarks[0].x * w), int(hand_landmarks[0].y * h)),
                     (int(hand_landmarks[12].x * w), int(hand_landmarks[12].y * h)),
                     (0, 0, 139), 2)

            # Wrist (0) to Ring tip (16)
            cv2.line(frame,
                     (int(hand_landmarks[0].x * w), int(hand_landmarks[0].y * h)),
                     (int(hand_landmarks[16].x * w), int(hand_landmarks[16].y * h)),
                     (0, 0, 139), 2)

            # Wrist (0) to Pinky tip (20)
            cv2.line(frame,
                     (int(hand_landmarks[0].x * w), int(hand_landmarks[0].y * h)),
                     (int(hand_landmarks[20].x * w), int(hand_landmarks[20].y * h)),
                     (0, 0, 139), 2)

            # Calculate raw distances for each finger
            distances = {
                "thumb":  calculate_distance(hand_landmarks[17], hand_landmarks[4]),
                "index":  calculate_distance(hand_landmarks[0],  hand_landmarks[8]),
                "middle": calculate_distance(hand_landmarks[0],  hand_landmarks[12]),
                "ring":   calculate_distance(hand_landmarks[0],  hand_landmarks[16]),
                "pinky":  calculate_distance(hand_landmarks[0],  hand_landmarks[20]),
            }

            # Update running min/max for auto-calibration
            for finger in distances:
                if distances[finger] < min_distances[finger]:
                    min_distances[finger] = distances[finger]
                if distances[finger] > max_distances[finger]:
                    max_distances[finger] = distances[finger]

            # Map distance to raw servo angle (0–180)
            raw_angles = {}
            for finger in distances:
                span = max_distances[finger] - min_distances[finger]
                if span == 0:
                    raw_angles[finger] = 0
                else:
                    raw_angles[finger] = int(
                        (max_distances[finger] - distances[finger]) / span * 180
                    )

            # Apply EMA smoothing to reduce servo jitter
            for finger in raw_angles:
                ema_angles[finger] = int(
                    EMA_ALPHA * raw_angles[finger] + (1.0 - EMA_ALPHA) * ema_angles[finger]
                )

            # Display per-finger angle overlay on screen
            labels = ["T", "I", "M", "R", "P"]
            finger_names = ["thumb", "index", "middle", "ring", "pinky"]
            for idx, (label, fname) in enumerate(zip(labels, finger_names)):
                cv2.putText(frame,
                            f"{label}:{ema_angles[fname]:3d}",
                            (10, 20 + idx * 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                            (0, 255, 0), 1, cv2.LINE_AA)

            # Send UDP packet every 4th frame (rate limiting)
            if counterForTimer > 3:
                data = (f"{ema_angles['thumb']},"
                        f"{ema_angles['index']},"
                        f"{ema_angles['middle']},"
                        f"{ema_angles['ring']},"
                        f"{ema_angles['pinky']}")
                try:
                    sock.sendto(data.encode(), (ESP_IP.split(":")[0], UDP_PORT))
                    print(f"Sent data to ESP: {data}")
                except Exception as e:
                    print(f"[ERROR] Failed sending UDP packet: {e}")
                counterForTimer = 0
            else:
                counterForTimer += 1
    else:
        # No hand detected
        cv2.putText(frame, "No hand detected",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 255), 2, cv2.LINE_AA)

    # Show FPS
    cv2.putText(frame,
                f"FPS: {fps_display:.1f}",
                (w - 110, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 0), 1, cv2.LINE_AA)

    cv2.imshow('Hand Tracking (Press Q to quit)', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
sock.close()
cv2.destroyAllWindows()

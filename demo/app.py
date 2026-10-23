import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import math
import socket
import numpy as np
import os

BaseOptions = python.BaseOptions
HandLandmarker = vision.HandLandmarker
HandLandmarkerOptions = vision.HandLandmarkerOptions

def calculate_distance(point1, point2):
    return math.sqrt((point1.x - point2.x)**2 + (point1.y - point2.y)**2 + (point1.z - point2.z)**2)

script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env")

if os.path.exists(env_path):
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
    except Exception as e:
        print(f"Warning: Error reading .env file: {e}")
else:
    print(f"Notice: .env file not found at {env_path}. Using default configuration.")

ESP_IP = os.environ.get("ESP_IP", "192.168.1.100")
UDP_TARGET_IP = ESP_IP.split(":")[0]
try:
    UDP_PORT = int(os.environ.get("UDP_PORT", 8888))
except ValueError:
    UDP_PORT = 8888

print(f"Connecting to ESP8266 UDP at {UDP_TARGET_IP}:{UDP_PORT}")

cap = cv2.VideoCapture(0)

model_path = os.path.join(script_dir, "hand_landmarker.task")
if not os.path.exists(model_path):
    model_path = "hand_landmarker.task"

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    num_hands=1,
    running_mode=vision.RunningMode.VIDEO)
hand_landmarker = HandLandmarker.create_from_options(options)

counterForTimer = 0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

min_distances = {"thumb": float('inf'), "index": float('inf'), "middle": float('inf'), "ring": float('inf'), "pinky": float('inf')}
max_distances = {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0}

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Failed to capture frame. Exiting.")
        break
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    results = hand_landmarker.detect_for_video(mp_image, int(cap.get(cv2.CAP_PROP_POS_MSEC)))
    if results.hand_landmarks:
        for hand_landmarks in results.hand_landmarks:
            for i in range(len(hand_landmarks)):
                landmark = hand_landmarks[i]
                x = int(landmark.x * frame.shape[1])
                y = int(landmark.y * frame.shape[0])
                cv2.circle(frame, (x, y), 3, (0, 0, 139), -1)

            cv2.line(frame, 
                    (int(hand_landmarks[17].x * frame.shape[1]), int(hand_landmarks[17].y * frame.shape[0])),
                    (int(hand_landmarks[4].x * frame.shape[1]), int(hand_landmarks[4].y * frame.shape[0])),
                    (0, 0, 139), 2)
            
            cv2.line(frame, 
                    (int(hand_landmarks[0].x * frame.shape[1]), int(hand_landmarks[0].y * frame.shape[0])),
                    (int(hand_landmarks[8].x * frame.shape[1]), int(hand_landmarks[8].y * frame.shape[0])),
                    (0, 0, 139), 2)
            
            cv2.line(frame, 
                    (int(hand_landmarks[0].x * frame.shape[1]), int(hand_landmarks[0].y * frame.shape[0])),
                    (int(hand_landmarks[12].x * frame.shape[1]), int(hand_landmarks[12].y * frame.shape[0])),
                    (0, 0, 139), 2)
            
            cv2.line(frame, 
                    (int(hand_landmarks[0].x * frame.shape[1]), int(hand_landmarks[0].y * frame.shape[0])),
                    (int(hand_landmarks[16].x * frame.shape[1]), int(hand_landmarks[16].y * frame.shape[0])),
                    (0, 0, 139), 2)
            
            cv2.line(frame, 
                    (int(hand_landmarks[0].x * frame.shape[1]), int(hand_landmarks[0].y * frame.shape[0])),
                    (int(hand_landmarks[20].x * frame.shape[1]), int(hand_landmarks[20].y * frame.shape[0])),
                    (0, 0, 139), 2)

            distances = {
                "thumb": calculate_distance(hand_landmarks[17], hand_landmarks[4]),
                "index": calculate_distance(hand_landmarks[0], hand_landmarks[8]),
                "middle": calculate_distance(hand_landmarks[0], hand_landmarks[12]),
                "ring": calculate_distance(hand_landmarks[0], hand_landmarks[16]),
                "pinky": calculate_distance(hand_landmarks[0], hand_landmarks[20]),
            }
            for distance in distances:
                if distances[distance] < min_distances[distance]:
                    min_distances[distance] = distances[distance]
                if distances[distance] > max_distances[distance]:
                    max_distances[distance] = distances[distance]
            fingerDegrees = {}
            for finger in distances:
                if max_distances[finger] - min_distances[finger] == 0:
                    fingerDegrees[finger] = 0
                    continue
                fingerDegrees[finger] = int((max_distances[finger] - distances[finger]) / (max_distances[finger] - min_distances[finger]) * 180)
            if counterForTimer > 3:
                data = f"{fingerDegrees['thumb']},{fingerDegrees['index']},{fingerDegrees['middle']},{fingerDegrees['ring']},{fingerDegrees['pinky']}"
                sock.sendto(data.encode(), (UDP_TARGET_IP, UDP_PORT))
                print(f"Sent data to ESP: {data}")
                counterForTimer = 0
            else:
                counterForTimer += 1

    cv2.imshow('Hand Tracking', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
sock.close()
cv2.destroyAllWindows()

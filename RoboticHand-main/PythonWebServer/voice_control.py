"""
RoboticHand Voice Control System
Developers: Albert Toj Kayyalaparambil, Vivek Viswanath, Ronith Promy, Shifa Mariyam

Speech recognition and intent parsing system that dispatches gesture commands to ESP8266
and responds with neural Edge-TTS voice feedback.
"""

import speech_recognition as sr
import requests
import edge_tts
import asyncio
import os
import platform
import time
from pathlib import Path
from dotenv import load_dotenv

# Resolve base paths relative to this script file
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# Load environment configuration using python-dotenv
load_dotenv(dotenv_path=ENV_PATH)

ESP_IP = os.environ.get("ESP_IP", "192.168.4.1")
print(f"[INFO] Voice control configured for ESP8266 at http://{ESP_IP}")

async def speak_async(text, output_path):
    """Generate TTS audio and save to output_path."""
    communicate = edge_tts.Communicate(text, "en-US-JennyNeural")
    await communicate.save(str(output_path))

def speak(text):
    """Synthesize speech and play it. Uses a timestamped temp file to avoid
    file-lock conflicts on Windows when a previous audio clip is still playing."""
    # Use a unique filename per call to avoid Windows file-lock issues
    temp_file = BASE_DIR / f"tts_{int(time.time() * 1000)}.mp3"
    try:
        asyncio.run(speak_async(text, temp_file))
        system = platform.system()
        if system == "Windows":
            os.startfile(str(temp_file))
        elif system == "Darwin":
            os.system(f"afplay \"{temp_file}\"")
        else:
            # Try common Linux players in order
            os.system(
                f"mpg123 \"{temp_file}\" 2>/dev/null || "
                f"mplayer -quiet \"{temp_file}\" >/dev/null 2>&1 || "
                f"ffplay -nodisp -autoexit \"{temp_file}\" >/dev/null 2>&1"
            )
        # Clean up old tts_*.mp3 files in the same directory (keep the last 2)
        _cleanup_tts_files(BASE_DIR)
    except Exception as e:
        print(f"TTS Error (falling back to console): {e}")

def _cleanup_tts_files(directory):
    """Remove all but the two most recent tts_*.mp3 files to avoid disk clutter."""
    tts_files = sorted(directory.glob("tts_*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old_file in tts_files[2:]:
        try:
            old_file.unlink()
        except OSError:
            pass  # File may still be in use; skip silently

recognizer = sr.Recognizer()

def listen():
    """Record ~4 seconds from the microphone and return recognized text."""
    try:
        with sr.Microphone() as source:
            print("\nListening... (speak your command)")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.record(source, duration=4)
        print("Recognizing speech...")
        text = recognizer.recognize_google(audio)
        print(f"Recognized: '{text}'")
        return text.lower()
    except sr.UnknownValueError:
        print("Could not understand audio.")
        return ""
    except sr.RequestError as e:
        print(f"Speech recognition service error: {e}")
        return ""
    except Exception as e:
        print(f"Microphone error: {e}")
        return ""

def control_hand(gesture):
    """Send a gesture command to the ESP8266 via HTTP GET."""
    url = f"http://{ESP_IP}/gesture?type={gesture}"
    try:
        resp = requests.get(url, timeout=2)
        print(f"Sent gesture: {gesture} | Response: {resp.text}")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Could not reach ESP at {url}: {e}")

def main():
    print("====================================================")
    print(" Robotic Hand Voice Control Console")
    print(" Commands: 'open', 'close' / 'fist', 'point',")
    print("           'yo sign', 'wave', 'quit' / 'exit'")
    print("====================================================")
    speak("Robotic hand voice system ready")

    while True:
        text = listen()
        if not text:
            continue

        if "open" in text:
            control_hand("open")
            speak("Hand opened")
        elif "close" in text or "fist" in text:
            control_hand("close")
            speak("Hand closed")
        elif "point" in text:
            control_hand("point")
            speak("Pointing")
        elif "yo" in text and "sign" in text:
            control_hand("yo")
            speak("Yo sign")
        elif "wave" in text:
            control_hand("wave")
            speak("Waving")
        elif "quit" in text or "exit" in text:
            speak("Goodbye")
            print("Exiting voice control...")
            break
        else:
            print(f"Unknown command: '{text}'. Try: open, close, fist, point, yo sign, wave, quit.")

if __name__ == "__main__":
    main()

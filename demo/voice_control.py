import speech_recognition as sr
import requests
import edge_tts
import asyncio
import os
import platform

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

async def speak_async(text):
    communicate = edge_tts.Communicate(text, "en-US-JennyNeural")
    await communicate.save("temp.mp3")

def speak(text):
    print(f"🤖 Robotic Hand Voice Feedback: \"{text}\"")
    try:
        asyncio.run(speak_async(text))
        system = platform.system()
        if system == "Windows":
            try:
                os.startfile("temp.mp3")
                import time
                time.sleep(1.0)
            except Exception:
                pass
        elif system == "Darwin":
            os.system("afplay temp.mp3")
        else:
            os.system("mpg123 temp.mp3 2>/dev/null || mplayer -quiet temp.mp3 >/dev/null 2>&1")
        try:
            if os.path.exists("temp.mp3"):
                os.remove("temp.mp3")
        except Exception:
            pass
    except Exception as e:
        print(f"TTS Error: {e}")

recognizer = sr.Recognizer()

def listen():
    try:
        with sr.Microphone() as source:
            print("\n🎤 Listening for voice command (5s)...")
            audio = recognizer.record(source, duration=4)
        print("Recognizing speech...")
        text = recognizer.recognize_google(audio)
        print(f"Recognized: {text}")
        return text.lower()
    except sr.UnknownValueError:
        print("Could not understand audio")
        return ""
    except Exception as e:
        print(f"Microphone notice: {e}")
        try:
            text = input("🎤 Type a voice command (open / close / fist / point / yo / wave / quit): ")
            return text.strip().lower()
        except EOFError:
            return ""

def control_hand(gesture):
    url = f"http://{ESP_IP}/gesture?type={gesture}"
    try:
        resp = requests.get(url, timeout=2)
        print(f"Sent {gesture}, Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("Voice control started. Say commands like 'hand open', 'hand close', etc.")
    while True:
        text = listen()
        if not text:
            continue
        
        if "open" in text:
            control_hand("open")
            speak("Hand opened")
        elif ("close" in text or "fist" in text):
            control_hand("close")
            speak("Hand closed")
        elif "point" in text:
            control_hand("point")
            speak("Pointing")
        elif "yo" in text and "sign" in text:
            control_hand("yo")
            speak("Yo")
        elif "wave" in text or "read" in text or "name" in text:
            control_hand("wave")
            speak("Waving")
        elif "quit" in text or "exit" in text:
            speak("Goodbye")
            break

if __name__ == "__main__":
    main()
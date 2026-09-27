"""
voice_receiver.py - Laptop Side
Receives navigation alerts and AI chatbot responses from Raspberry Pi.
Speaks via pyttsx3 and prints to terminal with clear labels.

Run FIRST on laptop:
    python3 voice_receiver.py
"""

import socket
import pyttsx3
import subprocess

HOST = "0.0.0.0"
PORT = 5005

# Check if audio device is available
try:
    result = subprocess.run(["aplay", "-l"], capture_output=True, text=True)
    AUDIO_AVAILABLE = "card" in result.stdout
except Exception:
    AUDIO_AVAILABLE = False

if AUDIO_AVAILABLE:
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)
else:
    engine = None
    print("[WARN] No audio device found. Text display only.")

def speak(text):
    if engine:
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass

def handle_message(message: str):
    if message.startswith("[AI]"):
        # Chatbot response
        clean = message[4:].strip()
        print(f"\n🤖 AI Assistant : {clean}")
    else:
        # Navigation alert
        print(f"🧭 Navigation   : {message}")
    speak(message)

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"[OK] Listening on port {PORT}...")
        print("─" * 40)

        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024)
                if data:
                    handle_message(data.decode("utf-8"))

if __name__ == "__main__":
    start_server()

"""
voice_receiver.py - Laptop Side
Receives navigation messages from Raspberry Pi via socket.
Converts text to speech using pyttsx3 (offline).

Run on Laptop FIRST:
    python3 voice_receiver.py

Then run main.py on Raspberry Pi.
"""

import socket
import pyttsx3

HOST = "0.0.0.0"  # Listen on all interfaces
PORT = 5005

engine = pyttsx3.init()
engine.setProperty('rate', 150)  # Speed of speech

def speak(text):
    print(f"[VOICE] {text}")
    engine.say(text)
    engine.runAndWait()

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"[OK] Listening on port {PORT}...")

        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024)
                if data:
                    message = data.decode("utf-8")
                    speak(message)

if __name__ == "__main__":
    start_server()

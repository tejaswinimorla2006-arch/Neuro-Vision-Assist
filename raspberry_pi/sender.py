"""
Module 5: Socket Sender
Sends navigation instruction strings from Raspberry Pi to Laptop over Wi-Fi.

Usage:
  - Laptop and Pi must be on the same Wi-Fi network
  - Set LAPTOP_IP to your laptop's IP address
  - Laptop runs voice_receiver.py first, then run this
"""

import socket

LAPTOP_IP   = "10.201.63.146"  # Laptop IP
LAPTOP_PORT = 5005

def send_message(message: str):
    """Send a single message string to the laptop."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((LAPTOP_IP, LAPTOP_PORT))
            s.sendall(message.encode("utf-8"))
    except ConnectionRefusedError:
        print("[WARN] Laptop not reachable. Is voice_receiver.py running?")
    except Exception as e:
        print(f"[ERROR] Send failed: {e}")


if __name__ == "__main__":
    send_message("Test message from Raspberry Pi")
    print("[OK] Message sent.")

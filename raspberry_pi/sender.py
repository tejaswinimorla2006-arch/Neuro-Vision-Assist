"""
sender.py - Neuro Vision Assist
Sends navigation instructions to laptop over Wi-Fi via TCP socket.
Uses a background queue so sending never blocks the main camera loop.

Usage:
    from sender import start_sender, enqueue_message
"""

import socket
import threading
import queue
from config import LAPTOP_IP, LAPTOP_PORT

_msg_queue = queue.Queue(maxsize=5)

def _sender_worker():
    """Background thread: drains the queue and sends each message."""
    while True:
        message = _msg_queue.get()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((LAPTOP_IP, LAPTOP_PORT))
                s.sendall(message.encode("utf-8"))
        except ConnectionRefusedError:
            print("[WARN] Laptop not reachable. Is voice_receiver.py running?")
        except Exception as e:
            print(f"[SENDER ERROR] {e}")
        finally:
            _msg_queue.task_done()

def start_sender():
    """Call once at startup to launch the background sender thread."""
    t = threading.Thread(target=_sender_worker, daemon=True)
    t.start()

def enqueue_message(message: str):
    """Non-blocking: drops message if queue is full (avoids backlog)."""
    try:
        _msg_queue.put_nowait(message)
    except queue.Full:
        pass

if __name__ == "__main__":
    start_sender()
    enqueue_message("Test message from Raspberry Pi")
    _msg_queue.join()
    print("[OK] Message sent.")

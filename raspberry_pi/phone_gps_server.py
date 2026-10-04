from pathlib import Path
import subprocess
import json
import os

from flask import Flask, jsonify, request, send_file

from campus_nav.gps_manager import GPSManager
from config import GPS_PHONE_FIX_FILE


app = Flask(__name__)
gps_manager = GPSManager()
_sender_page = Path(__file__).with_name("phone_gps_sender.html")
_certificate = Path(__file__).with_name("phone_gps_server.crt")
_private_key = Path(__file__).with_name("phone_gps_server.key")


def _ensure_certificate():
    if _certificate.exists() and _private_key.exists():
        return
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(_private_key), "-out", str(_certificate),
        "-days", "3650", "-subj", "/CN=neuro-vision-assist",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:192.168.152.202",
    ], check=True)


@app.get("/")
def sender_page():
    return send_file(_sender_page, mimetype="text/html")


@app.post("/gps")
def receive_gps():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(accepted=False, error="JSON object required"), 400

    required = ("latitude", "longitude", "accuracy", "speed", "heading", "timestamp")
    if any(field not in payload for field in required):
        return jsonify(accepted=False, error="Incomplete GPS payload"), 400

    accepted = gps_manager.process_phone_payload(payload)
    if not accepted:
        return jsonify(accepted=False), 400
    temporary_file = f"{GPS_PHONE_FIX_FILE}.tmp"
    with open(temporary_file, "w") as stream:
        json.dump(payload, stream)
    os.replace(temporary_file, GPS_PHONE_FIX_FILE)

    return jsonify(accepted=True)


@app.post("/nav")
def receive_navigation():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(accepted=False, error="JSON object required"), 400

    nav_type = payload.get("type")
    instruction = payload.get("instruction")

    if not nav_type:
        return jsonify(accepted=False, error="Missing message type"), 400

    print(f"[NAV RECEIVER] Event: {nav_type} | Instruction: '{instruction}' | Remaining: {payload.get('distance_remaining')}m")

    # Speak navigation instructions using existing Pi speak() function
    if instruction and isinstance(instruction, str) and instruction.strip():
        try:
            from main import speak
            speak(instruction.strip())
        except Exception as err:
            print(f"[NAV RECEIVER] Note: speak() call exception: {err}")

    # Store current navigation state for status queries
    try:
        nav_state_file = "/tmp/neuro_vision_phone_nav.json"
        temp_file = f"{nav_state_file}.tmp"
        with open(temp_file, "w") as f:
            json.dump(payload, f)
        os.replace(temp_file, nav_state_file)
    except Exception as e:
        print(f"[NAV RECEIVER] Warning: could not write nav state file: {e}")

    return jsonify(accepted=True, status="Message received", type=nav_type)


@app.get("/nav")
def get_navigation_status():
    nav_state_file = "/tmp/neuro_vision_phone_nav.json"
    if os.path.exists(nav_state_file):
        try:
            with open(nav_state_file, "r") as f:
                data = json.load(f)
            return jsonify(active=True, nav_state=data)
        except Exception:
            pass
    return jsonify(active=False, message="No active navigation state")


if __name__ == "__main__":
    _ensure_certificate()
    app.run(host="0.0.0.0", port=8765,
            ssl_context=(str(_certificate), str(_private_key)))

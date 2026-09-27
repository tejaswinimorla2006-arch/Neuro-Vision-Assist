"""
gps_reader.py - Neuro Vision Assist
Reads live GPS data from Neo-6M via UART.
Parses RMC (position/speed) and GGA (fix quality/satellites) NMEA sentences.
Supports both GPS ($GP prefix) and multi-GNSS ($GN prefix) talker IDs.

Wiring (standard UART):
  VCC -> Pin 4  (5V)
  GND -> Pin 14 (GND)
  TX  -> Pin 10 (GPIO15 / UART RX)
  RX  -> Pin 8  (GPIO14 / UART TX)

Serial Device Detection:
  Tries: /dev/serial0 (mapped UART) → /dev/ttyAMA0 (hardware) → /dev/ttyS0 (mini UART)

Usage:
    python3 gps_reader.py
"""

import serial
import pynmea2
import time
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from config import GPS_PORT, GPS_BAUD


@dataclass(frozen=True)
class GPSFix:
    latitude: float | None
    longitude: float | None
    speed_kmh: float | None
    timestamp_utc: datetime | None
    valid: bool
    received_at_monotonic: float = 0.0
    fix_quality: int | None = None
    satellites: int | None = None
    hdop: float | None = None
    accuracy_m: float | None = None
    bearing_deg: float | None = None


def _detect_gps_port(preferred_port: str) -> str | None:
    """
    Detect the correct GPS serial port.
    Tries: preferred → /dev/serial0 → /dev/ttyAMA0 → /dev/ttyS0
    Returns the first accessible port, or None if none found.
    """
    candidates = [
        preferred_port,
        "/dev/serial0",      # mapped UART (most common on Pi 4)
        "/dev/ttyAMA0",      # hardware UART (if Bluetooth disabled)
        "/dev/ttyS0",        # mini UART
    ]
    
    for port in candidates:
        if port is None:
            continue
        if os.path.exists(port):
            try:
                # Try to open briefly to check permissions
                test_ser = serial.Serial(port, baudrate=GPS_BAUD, timeout=0.1)
                test_ser.close()
                return port
            except (serial.SerialException, OSError):
                continue
    
    return None


def init_gps(gps_port: str | None = None) -> tuple[serial.Serial | None, str | None]:
    """
    Initialize GPS serial connection.
    
    Returns:
        (serial_object, actual_port) or (None, None) if initialization fails
    """
    if gps_port is None:
        gps_port = GPS_PORT
    
    detected_port = _detect_gps_port(gps_port)
    if not detected_port:
        print(f"[ERROR] No GPS serial port found.")
        print(f"  Tried: {gps_port}, /dev/serial0, /dev/ttyAMA0, /dev/ttyS0")
        print("  Verify: GPS wired to UART TX/RX and powered on (LED should blink)")
        print("  Check: sudo raspi-config → Interfaces → Serial Port (enable hardware UART)")
        print("  Check: sudo usermod -aG dialout $USER  (then reboot)")
        return None, None
    
    try:
        ser = serial.Serial(detected_port, baudrate=GPS_BAUD, timeout=1)
        print(f"[OK] GPS serial opened on {detected_port} at {GPS_BAUD} baud")
        return ser, detected_port
    except serial.SerialException as e:
        print(f"[ERROR] Cannot open GPS port {detected_port}: {e}")
        return None, None


def _parse_nmea_sentence(line: str) -> dict | None:
    """
    Parse a single NMEA sentence.
    Supports $GPRMC, $GNRMC (RMC) and $GPGGA, $GNGGA (GGA) talker IDs.
    
    Returns:
        dict with keys like 'sentence_type', 'status', 'latitude', etc.
        or None if parsing failed
    """
    line = line.strip()
    if not line:
        return None
    
    try:
        msg = pynmea2.parse(line)
        return {
            "sentence_type": msg.sentence_type,  # RMC, GGA, etc.
            "talker_id": msg.talker if hasattr(msg, 'talker') else None,
            "raw": msg,
            "line": line,
        }
    except (pynmea2.ParseError, AttributeError, ValueError, UnicodeDecodeError):
        return None


def get_gps_fix(ser) -> GPSFix:
    """
    Read up to 50 NMEA sentences and extract the latest valid GPS fix.
    
    Looks for:
      - RMC sentences (GPRMC, GNRMC) for position/speed/time
      - GGA sentences (GPGGA, GNGGA) for fix quality/satellites/HDOP
    
    Returns a GPSFix with all available data, or a fix with valid=False if no position found.
    """
    latitude = longitude = speed_kmh = None
    timestamp_utc = None
    valid = False
    fix_quality = satellites = hdop = None
    rmc_status = None
    
    fix_start_time = time.monotonic()
    
    for attempt in range(50):
        try:
            line = ser.readline().decode("ascii", errors="replace").strip()
            
            if not line:
                continue
            
            # Parse NMEA sentence
            parsed = _parse_nmea_sentence(line)
            if not parsed:
                continue
            
            msg = parsed["raw"]
            sentence_type = parsed["sentence_type"]
            
            # ── RMC sentence (position, speed, timestamp) ──
            # Both $GPRMC and $GNRMC supported
            if sentence_type == "RMC":
                try:
                    rmc_status = msg.status if hasattr(msg, 'status') else None
                    
                    # Only accept if status is "A" (active fix)
                    if rmc_status == "A":
                        if hasattr(msg, 'latitude') and hasattr(msg, 'longitude'):
                            latitude = round(float(msg.latitude), 6)
                            longitude = round(float(msg.longitude), 6)
                        
                        if hasattr(msg, 'spd_over_grnd'):
                            speed_kmh = round(float(msg.spd_over_grnd) * 1.852, 2)
                        
                        if hasattr(msg, 'datestamp') and hasattr(msg, 'timestamp'):
                            if msg.datestamp and msg.timestamp:
                                timestamp_utc = datetime.combine(
                                    msg.datestamp, msg.timestamp, tzinfo=timezone.utc
                                )
                        
                        valid = True
                    else:
                        # RMC with status != "A" means no fix
                        valid = False
                except (AttributeError, ValueError, TypeError):
                    pass
            
            # ── GGA sentence (fix quality, satellites, HDOP) ──
            # Both $GPGGA and $GNGGA supported
            elif sentence_type == "GGA":
                try:
                    if hasattr(msg, 'gps_qual'):
                        fix_quality = int(msg.gps_qual) if msg.gps_qual else None
                    
                    if hasattr(msg, 'num_sats'):
                        satellites = int(msg.num_sats) if msg.num_sats else None
                    
                    if hasattr(msg, 'horizontal_dil'):
                        hdop = float(msg.horizontal_dil) if msg.horizontal_dil else None
                    
                    # GGA fix_quality 0 means no fix
                    if fix_quality == 0:
                        valid = False
                except (AttributeError, ValueError, TypeError):
                    pass
        
        except Exception as e:
            # Suppress individual parse errors; continue reading
            pass
    
    # ── Build final GPSFix ──
    final_valid = (
        valid and 
        latitude is not None and 
        longitude is not None and 
        (fix_quality is None or fix_quality > 0)
    )
    
    return GPSFix(
        latitude=latitude,
        longitude=longitude,
        speed_kmh=speed_kmh,
        timestamp_utc=timestamp_utc,
        valid=final_valid,
        received_at_monotonic=time.monotonic(),  # ← CRITICAL: Set timestamp NOW
        fix_quality=fix_quality,
        satellites=satellites,
        hdop=hdop,
    )


def get_gps_data(ser) -> dict:
    """Backward-compatible dictionary wrapper around :func:`get_gps_fix`."""
    fix = get_gps_fix(ser)
    return {
        "lat": fix.latitude,
        "lon": fix.longitude,
        "speed_kmh": fix.speed_kmh,
        "timestamp_utc": fix.timestamp_utc,
        "valid": fix.valid,
        "fix_quality": fix.fix_quality,
        "satellites": fix.satellites,
        "hdop": fix.hdop,
    }


if __name__ == "__main__":
    ser, port = init_gps()
    if not ser:
        exit(1)
    
    print(f"[INFO] Waiting for GPS fix on {port} at {GPS_BAUD} baud...")
    print("[INFO] (may take 30-90s outdoors, Ctrl+C to stop)\n")
    
    while True:
        try:
            fix = get_gps_fix(ser)
            
            if fix.valid and fix.latitude and fix.longitude:
                print(f"[GPS FIX]")
                print(f"  Latitude:  {fix.latitude}")
                print(f"  Longitude: {fix.longitude}")
                print(f"  Satellites: {fix.satellites}")
                print(f"  HDOP: {fix.hdop}")
                print(f"  Fix Quality: {fix.fix_quality}")
                print(f"  Speed: {fix.speed_kmh} km/h")
                print()
            else:
                # Distinguish "no data" from "data but no fix"
                print(f"[GPS] Waiting for fix...")
                if fix.satellites is not None and fix.satellites < 4:
                    print(f"  Signal detected: {fix.satellites} satellites (need 4+)")
                print()
        
        except KeyboardInterrupt:
            print("\n[OK] GPS test stopped.")
            break
        except Exception as e:
            print(f"[GPS ERROR] {e}")
        
        time.sleep(2)

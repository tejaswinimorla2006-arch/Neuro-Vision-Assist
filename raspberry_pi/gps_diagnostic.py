#!/usr/bin/env python3
"""
gps_diagnostic.py - GPS Module Diagnostic Tool

Comprehensive hardware and software diagnostics for GPS connection.
Helps identify whether the issue is:
  1. Hardware (serial port not connected, wrong UART)
  2. Permissions (can't access /dev/ttyXXX)
  3. No NMEA data (GPS not sending anything)
  4. No satellite fix (data present but no position lock)
  5. Software parsing (fix exists but coordinates not extracted)

Usage:
    python3 gps_diagnostic.py

Press Ctrl+C to stop at any time.
"""

import os
import sys
import serial
import time
import stat
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from config import GPS_PORT, GPS_BAUD


def check_device_exists(device_path: str) -> bool:
    """Check if the device file exists."""
    return os.path.exists(device_path)


def check_device_readable(device_path: str) -> bool:
    """Check if the device file is readable by current user."""
    try:
        return os.access(device_path, os.R_OK)
    except:
        return False


def check_device_writable(device_path: str) -> bool:
    """Check if the device file is writable by current user."""
    try:
        return os.access(device_path, os.W_OK)
    except:
        return False


def check_device_permissions(device_path: str) -> str:
    """Get device file permissions in human-readable format."""
    try:
        st = os.stat(device_path)
        mode = st.st_mode
        return oct(stat.S_IMODE(mode))
    except:
        return "unknown"


def list_serial_devices() -> list[str]:
    """List all /dev/tty* devices."""
    devices = []
    try:
        for item in os.listdir("/dev"):
            if item.startswith("tty") or item.startswith("serial"):
                path = os.path.join("/dev", item)
                if os.path.isblk(path) or os.path.isfifo(path):
                    devices.append(path)
    except:
        pass
    return sorted(devices)


def test_serial_open(device_path: str, baud: int) -> tuple[bool, str]:
    """Try to open the serial port."""
    try:
        ser = serial.Serial(device_path, baudrate=baud, timeout=1)
        ser.close()
        return True, "OK"
    except serial.SerialException as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def listen_for_data(device_path: str, baud: int, timeout_s: float = 10.0) -> dict:
    """
    Listen for raw NMEA data on the serial port.
    
    Returns:
        {
            'connected': bool,
            'data_received': bool,
            'sentences': {sentence_type: count},
            'first_line': str,
            'sample_lines': [str],
        }
    """
    result = {
        "connected": False,
        "data_received": False,
        "sentences": {},
        "first_line": None,
        "sample_lines": [],
    }
    
    try:
        ser = serial.Serial(device_path, baudrate=baud, timeout=1)
        result["connected"] = True
    except Exception as e:
        print(f"  Cannot open {device_path}: {e}")
        return result
    
    print(f"  Listening for data (timeout: {timeout_s}s)...")
    start_time = time.time()
    
    try:
        while time.time() - start_time < timeout_s:
            try:
                line = ser.readline().decode("ascii", errors="replace").strip()
                if line:
                    result["data_received"] = True
                    if result["first_line"] is None:
                        result["first_line"] = line
                        print(f"    [Data received!] First line: {line}")
                    
                    # Extract sentence type
                    if line.startswith("$"):
                        sentence_type = line[1:6]  # e.g., "GPRMC" or "GPGGA"
                        result["sentences"][sentence_type] = result["sentences"].get(sentence_type, 0) + 1
                    
                    # Keep sample lines
                    if len(result["sample_lines"]) < 10:
                        result["sample_lines"].append(line)
            except Exception as e:
                pass
    finally:
        ser.close()
    
    return result


def parse_nmea_sample(line: str) -> dict:
    """Parse one NMEA sentence and extract key fields."""
    result = {
        "line": line,
        "sentence_type": None,
        "status": None,
        "latitude": None,
        "longitude": None,
        "fix_quality": None,
        "satellites": None,
        "error": None,
    }
    
    if not line.startswith("$"):
        result["error"] = "Not a valid NMEA sentence (missing $)"
        return result
    
    try:
        import pynmea2
        msg = pynmea2.parse(line)
        result["sentence_type"] = msg.sentence_type
        
        # RMC sentence
        if msg.sentence_type == "RMC":
            result["status"] = msg.status if hasattr(msg, 'status') else None
            result["latitude"] = msg.latitude if hasattr(msg, 'latitude') else None
            result["longitude"] = msg.longitude if hasattr(msg, 'longitude') else None
        
        # GGA sentence
        elif msg.sentence_type == "GGA":
            result["fix_quality"] = int(msg.gps_qual) if hasattr(msg, 'gps_qual') and msg.gps_qual else None
            result["satellites"] = int(msg.num_sats) if hasattr(msg, 'num_sats') and msg.num_sats else None
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


def main():
    print("=" * 70)
    print("GPS MODULE DIAGNOSTIC TOOL")
    print("=" * 70)
    print()
    
    # ─── Step 1: Check configured port ───────────────────────────────────────
    print("STEP 1: Check Configured GPS Port")
    print(f"  Configured port: {GPS_PORT}")
    print(f"  Configured baud: {GPS_BAUD}")
    print()
    
    # ─── Step 2: List available serial devices ────────────────────────────────
    print("STEP 2: Available Serial Devices")
    devices = list_serial_devices()
    relevant_devices = [d for d in devices if "tty" in d or "serial" in d]
    if relevant_devices:
        for dev in relevant_devices[:15]:  # Limit output
            exists = check_device_exists(dev)
            symbol = "✓" if exists else "✗"
            print(f"  {symbol} {dev}")
    else:
        print("  No serial devices found!")
    print()
    
    # ─── Step 3: Check specific GPS ports ──────────────────────────────────────
    print("STEP 3: Check GPS Port Status")
    gps_candidates = [
        GPS_PORT,
        "/dev/serial0",
        "/dev/ttyAMA0",
        "/dev/ttyS0",
    ]
    
    accessible_ports = []
    for port in gps_candidates:
        if port is None:
            continue
        
        exists = check_device_exists(port)
        readable = check_device_readable(port)
        writable = check_device_writable(port)
        perms = check_device_permissions(port)
        
        print(f"  {port}:")
        print(f"    Exists:    {exists}")
        if exists:
            print(f"    Readable:  {readable}")
            print(f"    Writable:  {writable}")
            print(f"    Perms:     {perms}")
            if readable and writable:
                accessible_ports.append(port)
        print()
    
    if not accessible_ports:
        print("  ERROR: No accessible GPS ports found!")
        print("  → Try: sudo usermod -aG dialout $USER")
        print("  → Then: logout and login, or use 'newgrp dialout'")
        return
    
    # ─── Step 4: Try to open port ──────────────────────────────────────────────
    print("STEP 4: Test Serial Port Open")
    best_port = None
    for port in accessible_ports:
        ok, msg = test_serial_open(port, GPS_BAUD)
        status = "OK" if ok else f"FAIL ({msg})"
        print(f"  {port}: {status}")
        if ok and best_port is None:
            best_port = port
    
    if not best_port:
        print("  ERROR: Cannot open any GPS port")
        return
    
    print(f"  → Using: {best_port}")
    print()
    
    # ─── Step 5: Listen for NMEA data ──────────────────────────────────────────
    print("STEP 5: Listen for NMEA Data")
    print(f"  Port: {best_port}")
    print(f"  Baud: {GPS_BAUD}")
    print()
    
    data_info = listen_for_data(best_port, GPS_BAUD, timeout_s=10.0)
    
    if not data_info["connected"]:
        print("  ERROR: Could not connect to port")
        return
    
    if not data_info["data_received"]:
        print("  ERROR: No data received on serial port")
        print("  → Check GPS module power (LED should blink)")
        print("  → Check TX/RX wiring")
        print("  → Check baud rate (typically 9600)")
        return
    
    print(f"  ✓ Data received!")
    print(f"  Sentence types detected:")
    for sentence_type, count in sorted(data_info["sentences"].items()):
        print(f"    {sentence_type}: {count} times")
    print()
    
    # ─── Step 6: Parse NMEA sentences ──────────────────────────────────────────
    print("STEP 6: Parse NMEA Sentences")
    print()
    
    has_rmc = False
    has_gga = False
    has_valid_position = False
    has_satellite_fix = False
    
    for i, line in enumerate(data_info["sample_lines"][:3]):
        print(f"  Sample {i + 1}: {line}")
        parsed = parse_nmea_sample(line)
        
        if parsed["sentence_type"] == "RMC":
            has_rmc = True
            status = "Active" if parsed["status"] == "A" else f"Inactive ({parsed['status']})"
            print(f"    Type: RMC (position/speed/time)")
            print(f"    Status: {status}")
            if parsed["latitude"] is not None and parsed["longitude"] is not None:
                has_valid_position = True
                print(f"    Latitude:  {parsed['latitude']}")
                print(f"    Longitude: {parsed['longitude']}")
            else:
                print(f"    Position: Not available")
        
        elif parsed["sentence_type"] == "GGA":
            has_gga = True
            print(f"    Type: GGA (fix quality/satellites)")
            print(f"    Fix Quality: {parsed['fix_quality']}")
            print(f"    Satellites: {parsed['satellites']}")
            if parsed["satellites"] is not None and parsed["satellites"] >= 4:
                has_satellite_fix = True
        
        if parsed["error"]:
            print(f"    Error: {parsed['error']}")
        
        print()
    
    # ─── Step 7: Diagnosis summary ─────────────────────────────────────────────
    print("=" * 70)
    print("DIAGNOSIS SUMMARY")
    print("=" * 70)
    print()
    
    if not has_rmc and not has_gga:
        print("❌ No NMEA sentences recognized")
        print("   This could mean:")
        print("   - GPS module is not compatible (requires u-blox NEO-6M compatible)")
        print("   - Baud rate mismatch (check GPS module documentation)")
        print("   - Corrupted serial data")
    else:
        print("✓ GPS module sending NMEA sentences")
    
    if has_rmc:
        print("✓ RMC sentences received (position available)")
    else:
        print("❌ No RMC sentences (position not available)")
    
    if has_gga:
        print("✓ GGA sentences received (fix quality available)")
    else:
        print("❌ No GGA sentences (fix quality not available)")
    
    if has_valid_position:
        print("✓ RMC sentences have valid position (active fix)")
    else:
        print("❌ RMC position not active (no satellite fix yet)")
    
    if has_satellite_fix:
        print("✓ Satellite lock detected (4+ satellites)")
    else:
        print("❌ No satellite lock (fewer than 4 satellites)")
    
    print()
    print("NEXT STEPS:")
    if not data_info["data_received"]:
        print("1. Check GPS hardware connection and power")
        print("2. Verify serial port settings in config.py")
        print("3. Use 'raspi-config' to enable serial interface")
    elif not has_satellite_fix:
        print("1. Move GPS antenna to open sky (away from buildings)")
        print("2. Wait 1-2 minutes for GPS to acquire satellites")
        print("3. Try near a window or outdoors")
    elif has_valid_position:
        print("1. GPS is working! Try running campus navigation:")
        print("   python3 run_campus_nav.py")
        print("2. Or run the simple GPS test:")
        print("   python3 gps_reader.py")
    
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[OK] Diagnostic stopped.")
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

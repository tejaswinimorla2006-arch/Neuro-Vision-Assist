"""
gps_manager.py
Monitors GPS position and detects when the user enters the campus geofence.

Outdoor phase : GPS-based navigation (walk to campus entrance).
Indoor phase  : Switches to campus graph navigation automatically.

Usage:
    from campus_nav.gps_manager import GPSManager
    gm = GPSManager(on_campus_entered=my_callback)
    gm.start()
"""

import threading
import time
import math
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, replace

from config import (
    GPS_FIX_STALE_S, GPS_PHONE_MAX_ACCURACY_M,
    GPS_PHONE_TIMESTAMP_TOLERANCE_S, GPS_PHONE_FIX_FILE,
)


def _haversine_meters(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in metres between two GPS coordinates."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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


class GPSManager:
    """
    Polls GPS in a background thread.
    Fires on_campus_entered() once when user crosses into the campus geofence.
    Fires on_position_update(lat, lon, speed_kmh) on every valid fix.
    """

    def __init__(self, on_campus_entered=None, on_position_update=None):
        from campus_nav.campus_graph import GPS_FENCE
        self._fence              = GPS_FENCE
        self._on_entered         = on_campus_entered
        self._on_update          = on_position_update
        self._inside_campus      = False
        self._entered_fired      = False
        self._thread             = None
        self._running            = False
        self._lock               = threading.Lock()
        self._latest_fix         = None
        self._last_valid_fix     = None
        self._last_phone_log     = 0.0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def process_phone_payload(self, payload):
        """Convert one phone JSON location update into the existing GPSFix."""
        try:
            latitude = float(payload["latitude"])
            longitude = float(payload["longitude"])
            accuracy = float(payload["accuracy"])
            timestamp = float(payload["timestamp"])
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0
            speed = payload.get("speed")
            speed_kmh = None if speed is None else max(0.0, float(speed) * 3.6)
            bearing = payload.get("heading")
            bearing = None if bearing is None else float(bearing)
        except (KeyError, TypeError, ValueError):
            return False

        valid = (
            -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
            and math.isfinite(latitude)
            and math.isfinite(longitude)
            and math.isfinite(accuracy)
            and 0.0 <= accuracy <= GPS_PHONE_MAX_ACCURACY_M
            and abs(time.time() - timestamp) <= GPS_PHONE_TIMESTAMP_TOLERANCE_S
        )
        if not valid:
            return False
        fix = GPSFix(
            latitude=latitude if valid else None,
            longitude=longitude if valid else None,
            speed_kmh=speed_kmh,
            timestamp_utc=datetime.fromtimestamp(timestamp, timezone.utc),
            valid=True,
            received_at_monotonic=time.monotonic(),
            fix_quality=1 if valid else 0,
            accuracy_m=accuracy,
            bearing_deg=bearing,
        )
        accepted = self.process_fix(fix)
        return accepted

    def get_latest_fix(self):
        """Return the latest immutable GPSFix, or None before the first read."""
        with self._lock:
            fix = self._latest_fix
        if fix is None:
            return None
        if fix.valid and time.monotonic() - fix.received_at_monotonic > GPS_FIX_STALE_S:
            return replace(fix, valid=False)
        return fix

    def process_fix(self, fix):
        """Publish one fix; used by the serial loop and simulated GPS tests."""
        now = time.monotonic()
        if fix.received_at_monotonic == 0.0:
            fix = replace(fix, received_at_monotonic=now)

        with self._lock:
            previous = self._last_valid_fix

        # Legacy simulated fixes do not carry phone accuracy or timestamps.
        # Keep their test guard separate from the phone-GPS validation path.
        if (fix.valid and previous and fix.latitude is not None and fix.longitude is not None
                and fix.accuracy_m is None and previous.accuracy_m is None
                and fix.timestamp_utc is None and previous.timestamp_utc is None):
            jump = _haversine_meters(
                previous.latitude, previous.longitude, fix.latitude, fix.longitude
            )
            if jump > 100.0:
                print(f"[GPS MANAGER] Ignoring legacy test outlier ({jump:.0f}m jump).")
                return False

        if (fix.valid and previous and fix.latitude is not None and fix.longitude is not None
              and fix.accuracy_m is not None and previous.accuracy_m is not None):
            jump = _haversine_meters(
                previous.latitude, previous.longitude, fix.latitude, fix.longitude
            )
            elapsed = max(0.0, fix.received_at_monotonic - previous.received_at_monotonic)
            speed_mps = max(
                (fix.speed_kmh or 0.0) / 3.6,
                (previous.speed_kmh or 0.0) / 3.6,
            )
            accuracy_allowance = (fix.accuracy_m or 0.0) + (previous.accuracy_m or 0.0)
            # Use speed/time and accuracy, with a broad sanity envelope for
            # phone fixes so ordinary GPS gaps are not treated as outliers.
            plausible_jump = speed_mps * elapsed + max(200.0, accuracy_allowance * 3.0)
            if jump > plausible_jump:
                print(f"[GPS MANAGER] Ignoring GPS outlier ({jump:.0f}m jump).")
                return False

        with self._lock:
            self._latest_fix = fix
            if fix.valid:
                self._last_valid_fix = fix

        if self._on_update:
            self._on_update(fix)

        if not fix.valid or fix.latitude is None or fix.longitude is None:
            return True

        dist = _haversine_meters(
            fix.latitude, fix.longitude,
            self._fence["lat"], self._fence["lon"]
        )
        inside = dist <= self._fence["radius_meters"]
        self._inside_campus = inside
        if inside and not self._entered_fired:
            self._entered_fired = True
            print(f"[GPS MANAGER] Campus entered (dist={dist:.0f}m).")
            if self._on_entered:
                self._on_entered()
        elif not inside:
            self._entered_fired = False
        return True

    def _loop(self):
        last_mtime_ns = 0
        print("[GPS MANAGER] Reading phone GPS updates...")
        while self._running:
            try:
                mtime_ns = os.stat(GPS_PHONE_FIX_FILE).st_mtime_ns
                if mtime_ns != last_mtime_ns:
                    with open(GPS_PHONE_FIX_FILE, "r") as stream:
                        payload = json.load(stream)
                    self.process_phone_payload(payload)
                    last_mtime_ns = mtime_ns
            except FileNotFoundError:
                pass
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
                print(f"[GPS MANAGER] Phone GPS read error: {error}")
            with self._lock:
                latest = self._latest_fix
            if (latest is not None and latest.valid
                    and time.monotonic() - latest.received_at_monotonic > GPS_FIX_STALE_S):
                self.process_fix(replace(latest, valid=False))
            time.sleep(0.2)

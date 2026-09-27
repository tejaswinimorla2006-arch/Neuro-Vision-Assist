"""
Simulated GPS acceptance test for campus navigation.

Run from raspberry_pi:
    python3 gps_simulation_test.py

This feeds GPSFix objects through GPSManager.process_fix(), so no serial GPS,
camera, IMU, or walking-speed estimate is used.
"""

import time

from campus_nav.gps_manager import GPSManager, _haversine_meters
from campus_nav.navigation_controller import NavigationController, NavState
from gps_reader import GPSFix
import campus_nav.navigation_controller as navigation_controller
from config import GPS_FIX_STALE_S


def offset(lat, lon, north_m, east_m=0.0):
    return lat + north_m / 111_320.0, lon + east_m / (111_320.0 * 0.974)


def fix(lat, lon, valid=True):
    return GPSFix(
        latitude=lat,
        longitude=lon,
        speed_kmh=1.0,
        timestamp_utc=None,
        valid=valid,
        received_at_monotonic=time.monotonic(),
        fix_quality=1 if valid else 0,
        satellites=8 if valid else 0,
        hdop=1.0 if valid else None,
    )


def main():
    original_nodes = navigation_controller.NODES.copy()
    start = (12.9716, 77.5946)
    waypoint_1 = offset(*start, 30)
    waypoint_2 = offset(*start, 60)
    destination = offset(*start, 90)
    navigation_controller.NODES.update({
        "sim_start": {"label": "Start", "type": "outdoor", "lat": start[0], "lon": start[1]},
        "sim_waypoint_1": {"label": "Waypoint 1", "type": "outdoor", "lat": waypoint_1[0], "lon": waypoint_1[1]},
        "sim_waypoint_2": {"label": "Waypoint 2", "type": "outdoor", "lat": waypoint_2[0], "lon": waypoint_2[1]},
        "sim_destination": {"label": "Destination", "type": "outdoor", "lat": destination[0], "lon": destination[1]},
    })

    try:
        nav = NavigationController(start_location="sim_start")
        messages = []
        nav._say = messages.append
        nav._path = ["sim_start", "sim_waypoint_1", "sim_waypoint_2", "sim_destination"]
        nav._steps = ["Start", "Waypoint 1", "Waypoint 2", "Destination"]
        nav._step_index = 0
        nav._state = NavState.NAVIGATING
        manager = GPSManager(on_position_update=nav.update_gps_position)

        stale_manager = GPSManager()
        stale_manager.process_fix(fix(*start))
        stale_manager.process_fix(fix(*start))
        stale = fix(*start)
        stale = GPSFix(
            latitude=stale.latitude, longitude=stale.longitude,
            speed_kmh=stale.speed_kmh, timestamp_utc=stale.timestamp_utc,
            valid=True, received_at_monotonic=time.monotonic() - GPS_FIX_STALE_S - 1,
            fix_quality=stale.fix_quality, satellites=stale.satellites, hdop=stale.hdop,
        )
        stale_manager.process_fix(stale)
        assert not stale_manager.get_latest_fix().valid, "stale fix remained valid"

        # Start -> waypoint 1: three confirmations inside the configured radius.
        for north_m in (0, 30, 30, 30):
            lat, lon = offset(*start, north_m)
            manager.process_fix(fix(lat, lon))
        assert nav._step_index == 1, "waypoint 1 did not complete at its radius"

        assert not manager.process_fix(fix(*offset(*start, 300))), "large GPS jump was accepted"

        # Jitter around waypoint 1 cannot re-trigger it after the index advances.
        for north_m in (16, 14, 16, 14):
            lat, lon = offset(*start, north_m)
            manager.process_fix(fix(lat, lon))
        assert nav._step_index == 1, "jitter repeatedly advanced waypoint 1"

        # Waypoint 2 and destination each require their own confirmations.
        for north_m in (60, 60, 60):
            lat, lon = offset(*start, north_m)
            manager.process_fix(fix(lat, lon))
        assert nav._step_index == 2, "waypoint 2 did not complete"

        for north_m in (90, 90, 90):
            lat, lon = offset(*start, north_m)
            manager.process_fix(fix(lat, lon))
        assert nav.state == NavState.ARRIVED, "destination did not complete"
        completed_index = nav._step_index
        manager.process_fix(fix(*offset(*start, 110)))
        assert nav._step_index == completed_index, "navigation continued after destination"

        # GPS loss pauses progress; a valid fix resumes it.
        nav._state = NavState.NAVIGATING
        nav._step_index = 0
        manager.process_fix(fix(*start, valid=False))
        assert nav._step_index == 0, "invalid GPS advanced navigation"
        manager.process_fix(fix(*offset(*start, 30)))
        manager.process_fix(fix(*offset(*start, 30)))
        manager.process_fix(fix(*offset(*start, 30)))
        assert nav._step_index == 1, "GPS recovery did not resume navigation"

        # Three off-route fixes trigger one recalculation request, not one per fix.
        nav._step_index = 0
        recalculations = []
        nav._recalculate_from_nearest_node = lambda lat, lon, dest: recalculations.append((lat, lon, dest))
        off_route = offset(*start, 0, 30)
        for _ in range(2):
            manager.process_fix(fix(*off_route))
        assert not recalculations, "off-route recalculated before confirmation"
        manager.process_fix(fix(*off_route))
        assert len(recalculations) == 1, "off-route confirmation did not trigger once"

        print("GPS simulation passed")
        print(f"Waypoint 1 distance: {_haversine_meters(*waypoint_1, *waypoint_1):.1f}m")
        print(f"Messages emitted: {len(messages)}")
    finally:
        navigation_controller.NODES.clear()
        navigation_controller.NODES.update(original_nodes)


if __name__ == "__main__":
    main()

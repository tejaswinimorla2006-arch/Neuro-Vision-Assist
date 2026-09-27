"""
navigation_controller.py
Central orchestrator for campus navigation.

State machine:
  IDLE -> NAVIGATING -> OBSTACLE_PAUSED -> NAVIGATING -> ARRIVED -> IDLE

Integrates:
- GPS position tracking (from GPSManager)
- Dijkstra shortest-path routing
- Turn-by-turn guidance (bearing-based directions)
- Real-time ETA calculation
- Voice announcements
"""

import threading
import time
import math
from enum import Enum, auto

from campus_nav.campus_graph          import resolve, NODES, all_location_names
from campus_nav.dijkstra              import shortest_path
from campus_nav.instruction_generator import generate_steps
from campus_nav.tts_manager           import speak
from campus_nav.gps_manager           import _haversine_meters
from campus_nav.turn_by_turn          import TurnByTurnEngine
from campus_nav.mapbox_navigation    import MapboxError, search_destination, walking_route
from config import (
    DEBUG_LEVEL,
    GPS_FIX_STALE_S, GPS_WAYPOINT_RADIUS_M, GPS_DESTINATION_RADIUS_M,
    GPS_WAYPOINT_CONFIRMATIONS, GPS_DESTINATION_CONFIRMATIONS,
    GPS_OFF_ROUTE_RADIUS_M, GPS_OFF_ROUTE_CONFIRMATIONS,
    TURN_ANNOUNCEMENT_DEADBAND_S, TURN_MIN_SPEED_SAMPLES, TURN_THRESHOLDS_M,
)


class NavState(Enum):
    IDLE            = auto()
    NAVIGATING      = auto()
    OBSTACLE_PAUSED = auto()
    ARRIVED         = auto()


_RESUME_DELAY            = 3.0
_PAUSE_REMINDER_INTERVAL = 10.0


def _distance_to_segment_m(lat, lon, start, end):
    """Approximate point-to-segment distance for the small campus map."""
    scale_x = 111_320.0 * math.cos(math.radians(lat))
    scale_y = 111_320.0
    px, py = lon * scale_x, lat * scale_y
    ax, ay = start["lon"] * scale_x, start["lat"] * scale_y
    bx, by = end["lon"] * scale_x, end["lat"] * scale_y
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return _haversine_meters(lat, lon, start["lat"], start["lon"])
    position = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    nearest_x, nearest_y = ax + position * dx, ay + position * dy
    return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5


def _compass_direction(bearing: float) -> str:
    """Convert bearing (0-360°) to compass direction."""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    index = int((bearing + 11.25) / 22.5) % 16
    return directions[index]


class NavigationController:

    def __init__(self, start_location: str = "main_gate", enqueue_fn=None,
                 on_indoor_transition=None):
        self._current_location    = start_location
        self._enqueue             = enqueue_fn
        self._state               = NavState.IDLE
        self._lock                = threading.Lock()
        self._path                = []
        self._steps               = []
        self._step_index          = 0
        self._obstacle_text       = ""
        self._last_pause_time     = 0.0
        self._last_obstacle_state = False
        self._last_gps_fix        = None
        self._waypoint_hits       = 0
        self._destination_hits    = 0
        self._off_route_hits      = 0
        self._gps_lost_announced  = False
        self._on_indoor_transition = on_indoor_transition
        self._latest_gps_fix       = None
        self._gps_provider          = None
        self._external_route        = None
        self._external_active       = False
        self._external_step_index   = 0
        self._external_off_route_hits = 0
        self._external_arrival_hits = 0
        self._external_announced    = set()
        self._external_last_display = 0.0
        self._external_last_display_state = None
        self._external_progress      = 0.0
        self._external_remaining_m   = None
        self._session_completed      = False
        self._last_phone_log         = 0.0
        
        # Turn-by-turn navigation
        self._turn_by_turn        = TurnByTurnEngine()
        self._last_nav_display    = 0.0  # rate-limit display output
        self._last_announcement   = None
        self._last_announcement_time = 0.0
        self._nav_display_interval = 5.0  # update display every 5 seconds

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        """Print welcome banner. Main thread drives all input via handle_input()."""
        print("\n" + "=" * 55)
        print("   NEURO VISION ASSIST — Campus Navigation")
        print("=" * 55)
        print(f"[NAV] Locations: {', '.join(all_location_names())}")
        print("[NAV] Commands: cancel | where | quit")
        print("=" * 55)
        self._say("Campus navigation ready. Where do you want to go?")

    def handle_input(self, raw: str) -> bool:
        """
        Called by main thread with user-typed text.
        Returns True  -> this controller handled it (don't pass to chatbot).
        Returns False -> pass to chatbot.
        """
        cmd = raw.strip().lower()

        if cmd == "cancel":
            self.cancel()
            return True

        if cmd == "start":
            if self._external_route is not None and not self._external_active:
                self._external_active = True
                with self._lock:
                    self._state = NavState.NAVIGATING
                print("[NAV] Navigation started.")
                self._say("Navigation started.")
                if self._external_route.steps:
                    self._say(self._external_route.steps[0].instruction)
            return True

        if cmd == "where":
            fix = self._current_valid_fix()
            if self._external_route is not None and fix is not None:
                self._say(f"Your current location is latitude {fix.latitude:.6f}, "
                          f"longitude {fix.longitude:.6f}.")
                return True
            with self._lock:
                loc = self._current_location
            label = NODES.get(loc, {}).get("label", loc)
            print(f"[NAV] You are at: {label}")
            self._say(f"You are currently at {label}.")
            return True

        # While navigating, let chatbot handle free-text questions
        with self._lock:
            state = self._state
        if state != NavState.IDLE:
            return False

        # Treat as destination request
        self._handle_destination(raw.strip())
        return True

    def set_current_location(self, node_id: str):
        with self._lock:
            self._current_location = node_id
        print(f"[NAV] Location updated: {NODES.get(node_id, {}).get('label', node_id)}")

    def update_gps_position(self, fix):
        """Consume a GPSManager GPSFix and progress the active outdoor route."""
        with self._lock:
            active = self._state in (NavState.NAVIGATING, NavState.OBSTACLE_PAUSED)
            if not active:
                return

        now = time.monotonic()
        valid_fix = (fix.valid and fix.latitude is not None and fix.longitude is not None
                     and now - fix.received_at_monotonic <= GPS_FIX_STALE_S)
        if not valid_fix:
            last_valid_age = (float("inf") if self._last_gps_fix is None else
                              now - self._last_gps_fix.received_at_monotonic)
            if last_valid_age <= GPS_FIX_STALE_S:
                return
            if not self._gps_lost_announced:
                self._gps_lost_announced = True
                self._say("GPS signal lost. Navigation is paused.")
            return

        self._latest_gps_fix = fix
        if self._gps_lost_announced:
            self._gps_lost_announced = False
            self._say("GPS signal restored. Resuming navigation.")

        self._last_gps_fix = fix
        if self._external_route is not None and self._external_active:
            self._update_external_progress(fix)
            return
        self._update_gps_progress(fix)

    def set_gps_provider(self, provider):
        """Set a callable returning GPSManager's latest fix."""
        self._gps_provider = provider

    def set_latest_gps_fix(self, fix):
        """Store the latest fix for external route startup."""
        self._latest_gps_fix = fix

    def _current_valid_fix(self):
        fix = self._gps_provider() if self._gps_provider else self._latest_gps_fix
        if (fix is None or not fix.valid or fix.latitude is None or fix.longitude is None
                or time.monotonic() - fix.received_at_monotonic > GPS_FIX_STALE_S):
            return None
        return fix

    def _update_external_progress(self, fix):
        route = self._external_route
        if route is None or self._session_completed:
            return
        progress, distance_from_route = self._route_progress(fix.latitude, fix.longitude, route.geometry)
        if distance_from_route > GPS_OFF_ROUTE_RADIUS_M + (fix.accuracy_m or 0.0):
            self._external_off_route_hits += 1
            if self._external_off_route_hits >= GPS_OFF_ROUTE_CONFIRMATIONS:
                self._external_off_route_hits = 0
                self._say("You are off route. Recalculating...")
                self._start_external_route(fix, announce=False)
            return
        self._external_off_route_hits = 0
        geometry_distance = self._route_geometry_distance(route.geometry)
        progress = max(self._external_progress, progress)
        progress = min(progress, geometry_distance)
        self._external_progress = progress
        destination_distance = _haversine_meters(
            fix.latitude, fix.longitude,
            route.destination.latitude, route.destination.longitude,
        )
        arrival_radius = GPS_DESTINATION_RADIUS_M + min(
            fix.accuracy_m or 0.0, GPS_DESTINATION_RADIUS_M
        )
        if destination_distance <= arrival_radius:
            self._external_arrival_hits += 1
            if self._external_arrival_hits >= GPS_DESTINATION_CONFIRMATIONS:
                self._external_remaining_m = 0.0
                self._external_route = None
                self._external_active = False
                self._external_arrival_hits = 0
                self._external_announced = set()
                with self._lock:
                    self._state = NavState.IDLE
                    self._session_completed = False
                self._say("Destination reached.")
                print("[NAV] Destination reached.")
                return
        else:
            self._external_arrival_hits = 0

        remaining = max(0.0, geometry_distance - progress)
        if self._external_remaining_m is not None:
            remaining = min(remaining, self._external_remaining_m)
        self._external_remaining_m = remaining
        previous_step_index = self._external_step_index
        while (self._external_step_index < len(route.steps)
               and self._route_point_progress(
                   route.steps[self._external_step_index].maneuver_latitude,
                   route.steps[self._external_step_index].maneuver_longitude,
                   route.geometry) <= progress + GPS_WAYPOINT_RADIUS_M
               and self._external_step_index + 1 < len(route.steps)):
            self._external_step_index += 1
        if self._external_step_index < len(route.steps):
            step = route.steps[self._external_step_index]
            step_progress = self._route_point_progress(
                step.maneuver_latitude, step.maneuver_longitude, route.geometry)
            distance_to_step = max(0.0, step_progress - progress)
            step_changed = self._external_step_index != previous_step_index
            if step_changed:
                self._external_announced = set()
            self._announce_external_step(step, distance_to_step, step_changed)
            instruction = (step.instruction or "Continue").strip()
            display_distance = distance_to_step
            display_distance_label = "Distance to next maneuver"
            if (self._external_step_index + 1 == len(route.steps)
                    and distance_to_step <= 0
                    and instruction.lower().startswith("continue")):
                instruction = "Continue to destination"
                display_distance = remaining
                display_distance_label = "Distance to destination"
        else:
            display_distance = remaining
            instruction = "Continue to destination"
            display_distance_label = "Distance to destination"
        now = time.monotonic()
        display_remaining = int(remaining)
        display_state = (instruction, round(display_distance), display_remaining)
        if ((display_state != self._external_last_display_state
             and now - self._external_last_display >= 1.0)
                or now - self._external_last_display >= 5.0):
            self._external_last_display = now
            self._external_last_display_state = display_state
            print(f"[NAV] Next: {instruction}")
            print(f"[NAV] {display_distance_label}: {display_distance:.0f} m")
            print(f"[NAV] Remaining: {display_remaining} m")
            print(f"[NAV] ETA: {max(0, int(route.duration_s * remaining / route.distance_m)) // 60} minutes")

    def _announcement_thresholds_for_step(self, distance):
        return [0, 5, 10, 20, 50, 100, 150]

    def _base_maneuver_text(self, instruction: str):
        text = (instruction or "Continue").strip()
        lowered = text.lower()
        if " onto " in text:
            return text.split(" onto ", 1)[0].strip()
        if lowered.startswith("continue"):
            return "Continue straight"
        return text

    def _format_step_guidance(self, step, distance, is_now: bool = False) -> str:
        instruction = (step.instruction or "Continue").strip()
        base = self._base_maneuver_text(instruction)
        lower = instruction.lower()
        if lower.startswith("continue"):
            if is_now:
                return "Continue straight."
            return f"Continue straight for {int(max(0.0, distance))} meters."
        street_name = (getattr(step, "street_name", "") or "").strip()
        if not street_name:
            onto_index = lower.find(" onto ")
            if onto_index >= 0:
                street_name = instruction[onto_index + len(" onto "):].strip().rstrip(".")
        if is_now:
            if street_name and " onto " not in instruction.lower():
                return f"{base} onto {street_name}."
            if street_name:
                return f"{base} onto {street_name}."
            return f"{base} now."
        return f"{base} in {int(max(0.0, distance))} meters."

    def _announce_external_step(self, step, distance, is_new_step=False):
        if step is None or not getattr(step, "instruction", None):
            return
        instruction = step.instruction.strip()
        if instruction.lower().startswith("arrive"):
            return
        thresholds = self._announcement_thresholds_for_step(distance)
        threshold = next((value for value in thresholds if distance <= value), None)
        if threshold is None:
            if is_new_step:
                self._say(self._format_step_guidance(step, distance))
            return
        if threshold in self._external_announced:
            return
        self._external_announced.add(threshold)
        if distance <= 5:
            self._say(self._format_step_guidance(step, distance, is_now=True))
        else:
            self._say(self._format_step_guidance(step, distance, is_now=False))

    def _route_progress(self, latitude, longitude, geometry):
        if len(geometry) < 2:
            return 0.0, float("inf")
        scale_x = 111320.0 * math.cos(math.radians(latitude))
        scale_y = 111320.0
        px, py = longitude * scale_x, latitude * scale_y
        best_distance = float("inf")
        best_progress = 0.0
        progress = 0.0
        for first, second in zip(geometry, geometry[1:]):
            ax, ay = first[0] * scale_x, first[1] * scale_y
            bx, by = second[0] * scale_x, second[1] * scale_y
            dx, dy = bx - ax, by - ay
            projected_length = math.hypot(dx, dy)
            segment_length = _haversine_meters(first[1], first[0], second[1], second[0])
            if projected_length and segment_length:
                factor = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy)
                                   / (projected_length * projected_length)))
                distance = math.hypot(px - (ax + factor * dx), py - (ay + factor * dy))
                if distance < best_distance:
                    best_distance = distance
                    best_progress = progress + factor * segment_length
                progress += segment_length
        return best_progress, best_distance

    def _route_geometry_distance(self, geometry):
        return sum(
            _haversine_meters(first[1], first[0], second[1], second[0])
            for first, second in zip(geometry, geometry[1:])
        )

    def _route_point_progress(self, latitude, longitude, geometry):
        progress, _ = self._route_progress(latitude, longitude, geometry)
        return progress

    def _distance_to_route_point(self, latitude, longitude, target_latitude,
                                 target_longitude, geometry):
        current_progress, distance_from_route = self._route_progress(
            latitude, longitude, geometry
        )
        target_progress, _ = self._route_progress(
            target_latitude, target_longitude, geometry
        )
        if distance_from_route == float("inf"):
            return float("inf")
        return max(0.0, target_progress - current_progress)

    def _update_gps_progress(self, fix):
        """Update navigation based on GPS fix. Enhanced with turn-by-turn guidance."""
        with self._lock:
            if self._state != NavState.NAVIGATING:
                return
            path = list(self._path)
            index = self._step_index
        
        # Update turn-by-turn engine with current position
        nav_state = self._turn_by_turn.update_position(
            latitude=fix.latitude,
            longitude=fix.longitude,
            speed_mps=fix.speed_kmh / 3.6 if fix.speed_kmh else 0.0,  # convert km/h to m/s
            fix_satellites=fix.satellites or 0,
            fix_hdop=fix.hdop or 0.0,
            fix_valid=fix.valid,
            nodes_dict=NODES
        )

        if index >= len(path) - 1:
            return

        next_node = NODES.get(path[index + 1], {})
        next_lat = next_node.get("lat")
        next_lon = next_node.get("lon")
        if next_lat is None or next_lon is None:
            return

        distance = _haversine_meters(fix.latitude, fix.longitude, next_lat, next_lon)
        is_destination = index + 1 == len(path) - 1
        radius = GPS_DESTINATION_RADIUS_M if is_destination else GPS_WAYPOINT_RADIUS_M
        needed = (GPS_DESTINATION_CONFIRMATIONS if is_destination
                  else GPS_WAYPOINT_CONFIRMATIONS)

        if distance <= radius:
            self._off_route_hits = 0
            if is_destination:
                self._destination_hits += 1
                if self._destination_hits >= needed:
                    self._complete_destination(path[-1], fix)
            else:
                self._waypoint_hits += 1
                if self._waypoint_hits >= needed:
                    self._advance_waypoint(index + 1, fix)
            return

        self._waypoint_hits = 0
        self._destination_hits = 0
        
        # Generate turn-by-turn announcements
        self._process_turn_by_turn_announcements(nav_state, distance)
        
        # Display navigation status
        self._display_navigation_status(nav_state, distance)
        
        # Check off-route
        self._check_off_route(fix.latitude, fix.longitude, path, index)

    def _process_turn_by_turn_announcements(self, nav_state, distance_to_waypoint):
        """Generate turn-by-turn announcements based on current navigation state."""
        # Get next turn info from turn-by-turn engine
        instruction = nav_state.next_instruction
        dist_to_turn = nav_state.distance_to_turn_m
        
        # Announce based on distance thresholds
        announcement_thresholds = [100, 50, 25, 10, 5]
        for threshold in announcement_thresholds:
            if dist_to_turn <= threshold:
                if instruction.startswith("Turn") or instruction.startswith("U-turn") or instruction.startswith("Bear"):
                    if self._last_announcement != instruction or \
                       time.monotonic() - self._last_announcement_time > TURN_ANNOUNCEMENT_DEADBAND_S:
                        
                        if dist_to_turn > 0:
                            announcement = f"{instruction} in {int(dist_to_turn)} meters."
                        else:
                            announcement = f"{instruction} now."
                        
                        if DEBUG_LEVEL in ("BASIC", "VERBOSE"):
                            print(f"[NAV TURN] {announcement}")
                        
                        self._say(announcement)
                        self._last_announcement = instruction
                        self._last_announcement_time = time.monotonic()
                break

    def _display_navigation_status(self, nav_state, distance_to_waypoint):
        """Display compact navigation status to console."""
        now = time.monotonic()
        if now - self._last_nav_display < self._nav_display_interval:
            return
        
        self._last_nav_display = now
        
        if DEBUG_LEVEL in ("BASIC", "VERBOSE"):
            print("\n" + "=" * 60)
            print("CAMPUS NAVIGATION STATUS")
            print("=" * 60)
            print(f"Position:        {nav_state.current_latitude:.6f}, {nav_state.current_longitude:.6f}")
            print(f"Direction:       {nav_state.current_bearing:.1f}° ({_compass_direction(nav_state.current_bearing)})")
            print(f"Speed:           {nav_state.current_speed_mps * 3.6:.1f} km/h")
            print(f"Next Action:     {nav_state.next_instruction}")
            print(f"Distance to:     {nav_state.distance_to_turn_m:.1f} m")
            print(f"Total Remaining: {nav_state.remaining_distance_m:.1f} m")
            if nav_state.eta_seconds:
                eta_min = nav_state.eta_seconds // 60
                eta_sec = nav_state.eta_seconds % 60
                print(f"ETA:             {eta_min}m {eta_sec}s")
            print(f"Satellites:      {nav_state.gps_satellites}")
            print(f"HDOP:            {nav_state.gps_hdop:.2f}")
            print("=" * 60 + "\n")

    def _advance_waypoint(self, new_index: int, fix):
        """Advance to the next waypoint."""
        with self._lock:
            self._step_index = new_index
            self._current_location = self._path[new_index]
            self._waypoint_hits = 0
            self._turn_by_turn.advance_segment()
            text = self._steps[new_index] if new_index < len(self._steps) else "Continue."
        
        if DEBUG_LEVEL in ("BASIC", "VERBOSE"):
            print(f"[NAV] Waypoint reached at GPS ({fix.latitude:.6f}, {fix.longitude:.6f})")
        
        self._say(f"Waypoint reached. {text}")

    def _confirm_arrival(self, destination_name: str | None = None, arrived: bool = False):
        """Finalize the navigation session once the current GPS fix confirms arrival."""
        with self._lock:
            if self._session_completed:
                return
            self._session_completed = True
            self._external_active = False
            self._external_announced = set()
            self._state = NavState.ARRIVED
        message = "You have reached your destination."
        if destination_name:
            verb = "arrived at" if arrived else "reached"
            message = f"You have {verb} {destination_name}."
        self._say(message)

    def _complete_destination(self, destination: str, fix):
        """Complete navigation at destination."""
        with self._lock:
            if self._state != NavState.NAVIGATING:
                return
            self._current_location = destination
            self._destination_hits = 0
            label = NODES[destination]["label"]
        if DEBUG_LEVEL in ("BASIC", "VERBOSE"):
            print(f"[NAV] Destination reached at GPS ({fix.latitude:.6f}, {fix.longitude:.6f})")
        self._confirm_arrival(label)

    def _return_to_idle(self):
        time.sleep(2)
        with self._lock:
            if self._state == NavState.ARRIVED:
                self._state = NavState.IDLE
        print("\n[NAV] Arrived. Type a new destination whenever ready.")

    def _check_off_route(self, latitude, longitude, path, index):
        current = NODES.get(path[index], {})
        next_node = NODES.get(path[index + 1], {})
        if (current.get("lat") is None or current.get("lon") is None
                or next_node.get("lat") is None or next_node.get("lon") is None):
            return
        distance = _distance_to_segment_m(
            latitude, longitude, current, next_node
        )
        if distance <= GPS_OFF_ROUTE_RADIUS_M:
            self._off_route_hits = 0
            return
        self._off_route_hits += 1
        if self._off_route_hits < GPS_OFF_ROUTE_CONFIRMATIONS:
            return
        self._off_route_hits = 0
        
        if DEBUG_LEVEL in ("BASIC", "VERBOSE"):
            print(f"[NAV] Off-route detected: {distance:.1f}m from planned route")
        
        self._recalculate_from_nearest_node(latitude, longitude, path[-1])

    def _recalculate_from_nearest_node(self, latitude, longitude, destination):
        candidates = [
            (node_id, meta) for node_id, meta in NODES.items()
            if meta.get("lat") is not None and meta.get("lon") is not None
        ]
        if not candidates:
            return
        start = min(
            candidates,
            key=lambda item: _haversine_meters(
                latitude, longitude, item[1]["lat"], item[1]["lon"]
            )
        )[0]
        path, total_dist = shortest_path(start, destination)
        if not path:
            self._say("You are off route and no alternate route is available.")
            return
        with self._lock:
            self._path = path
            self._steps = generate_steps(path)
            self._step_index = 0
            self._current_location = start
            self._turn_by_turn.set_route(path)
        self._say(f"Route recalculated. {total_dist} meters. {self._steps[0]}")

    def _handle_campus_destination(self, destination_text: str):
        """Handle user's destination request."""
        if self._session_completed:
            self._session_completed = False
        dest_node = resolve(destination_text)
        if not dest_node:
            self._say(f"I don't recognize '{destination_text}'. Try: {', '.join(all_location_names()[:3])}, etc.")
            return

        with self._lock:
            current_node = self._current_location

        path, total_distance = shortest_path(current_node, dest_node)
        if not path:
            self._say("No route found to that destination.")
            return

        with self._lock:
            self._path = path
            self._steps = generate_steps(path)
            self._step_index = 0
            self._state = NavState.NAVIGATING
            self._waypoint_hits = 0
            self._destination_hits = 0
            self._off_route_hits = 0
            self._external_active = False
            self._gps_lost_announced = False
            self._session_completed = False
            self._turn_by_turn.set_route(path)

        dest_label = NODES[dest_node]["label"]
        print(f"\n[NAV] Route to {dest_label} ({total_distance}m) starting...")
        self._say(f"Your current location has been detected. Route to {dest_label} found. {self._steps[0]}")

    def cancel(self):
        """Cancel active navigation."""
        with self._lock:
            self._state = NavState.IDLE
            self._path = []
            self._steps = []
            self._waypoint_hits = 0
            self._destination_hits = 0
            self._session_completed = False
            self._external_route = None
            self._external_active = False
            self._external_announced = set()
        self._say("Navigation cancelled.")

    def _say(self, text: str):
        """Speak and print a navigation message."""
        print(f"\n[NAV VOICE] {text}\n")
        speak(text)

    def obstacle_update(self, has_obstacle: bool, warning_text: str = ""):
        """
        Called from camera thread every frame.
        Edge-triggered so pause/resume fires only on state change.
        """
        with self._lock:
            prev                      = self._last_obstacle_state
            self._last_obstacle_state = has_obstacle
            self._obstacle_text       = warning_text
            state                     = self._state

        # Periodic reminder while already paused
        if has_obstacle and has_obstacle == prev and state == NavState.OBSTACLE_PAUSED:
            if time.time() - self._last_pause_time >= _PAUSE_REMINDER_INTERVAL:
                self._say(f"Still blocked. {warning_text}")
                with self._lock:
                    self._last_pause_time = time.time()
            return

        if has_obstacle == prev:
            return   # no change, nothing to do

        if has_obstacle and state == NavState.NAVIGATING:
            with self._lock:
                self._state           = NavState.OBSTACLE_PAUSED
                self._last_pause_time = time.time()
            self._say(f"Navigation paused. {warning_text}")

        elif not has_obstacle and state == NavState.OBSTACLE_PAUSED:
            with self._lock:
                self._state = NavState.NAVIGATING
            threading.Thread(target=self._resume_after_delay, daemon=True).start()

    def cancel(self):
        with self._lock:
            self._state      = NavState.IDLE
            self._path       = []
            self._steps      = []
            self._step_index = 0
            self._external_route = None
            self._external_active = False
            self._external_announced = set()
            self._session_completed = False
        self._say("Navigation cancelled.")

    @property
    def is_navigating(self) -> bool:
        return self._state in (NavState.NAVIGATING, NavState.OBSTACLE_PAUSED)

    @property
    def state(self) -> NavState:
        with self._lock:
            return self._state

    # ── Internal ───────────────────────────────────────────────────────────────

    def _say(self, text: str):
        speak(text)
        if self._enqueue:
            self._enqueue(text)

    def _resume_after_delay(self):
        time.sleep(_RESUME_DELAY)
        self._say("Obstacle cleared. Resuming navigation.")
        self._speak_current_step()

    def _handle_destination(self, raw_input: str):
        destination_text = raw_input.strip()
        lowered = destination_text.lower()
        for prefix in ("take me to ", "navigate to ", "go to "):
            if lowered.startswith(prefix):
                destination_text = destination_text[len(prefix):].strip()
                break
        if resolve(destination_text):
            self._handle_campus_destination(destination_text)
            return
        self._start_external_destination(destination_text)

    def _start_external_destination(self, query):
        lowered = query.strip().lower()
        for prefix in ("take me to ", "navigate to ", "go to "):
            if lowered.startswith(prefix):
                query = query.strip()[len(prefix):].strip()
                break
        if not query:
            self._say("Destination not found.")
            return
        self._say(f"Searching for {query}.")
        deadline = time.monotonic() + 15.0
        fix = None
        while time.monotonic() < deadline:
            fix = self._current_valid_fix()
            if fix is not None:
                now = time.monotonic()
                if now - self._last_phone_log >= 2.0:
                    print(f"[NAV] Using phone GPS: lat={fix.latitude:.6f}, "
                          f"lon={fix.longitude:.6f}")
                    self._last_phone_log = now
                break
            time.sleep(0.2)
        if fix is None:
            self._say("Phone GPS unavailable. Please open the Neuro Vision GPS page on your phone and allow location access.")
            return
        try:
            destination = search_destination(query, fix.latitude, fix.longitude)
            if destination is None:
                print("[NAV] Destination not found.")
                return
            print(f"[NAV] Destination found:\n{destination.name}\nAddress: {destination.address}")
            self._say(f"{destination.name} found.")
            self._start_external_route(fix, destination=destination)
        except MapboxError as error:
            print(f"[MAPBOX] {error}")

    def _start_external_route(self, fix, destination=None, announce=True):
        if destination is None and self._external_route is not None:
            destination = self._external_route.destination
        if destination is None:
            return
        try:
            route = walking_route(fix.latitude, fix.longitude, destination)
        except MapboxError as error:
            print(f"[MAPBOX] {error}")
            return
        self._last_gps_fix = fix
        self._latest_gps_fix = fix
        with self._lock:
            self._external_route = route
            self._external_active = not announce
            self._external_step_index = 0
            self._external_off_route_hits = 0
            self._external_arrival_hits = 0
            self._external_announced = set()
            self._external_last_display_state = None
            self._external_progress = 0.0
            self._external_remaining_m = self._route_geometry_distance(route.geometry)
            self._state = NavState.NAVIGATING if not announce else NavState.IDLE
        print(f"[NAV] Route found:\nDistance: {route.distance_m / 1000:.1f} kilometers\n"
              f"ETA: {int(route.duration_s // 60)} minutes")
        if announce:
            self._say(f"Route found. Distance {route.distance_m / 1000:.1f} kilometers. "
                      f"Estimated time {int(route.duration_s // 60)} minutes. "
                      "Say start when you are ready.")

    def _speak_current_step(self):
        with self._lock:
            idx   = self._step_index
            steps = self._steps
        if idx < len(steps):
            self._say(steps[idx])

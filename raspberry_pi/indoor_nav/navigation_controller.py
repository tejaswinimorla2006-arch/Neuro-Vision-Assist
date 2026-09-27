"""
navigation_controller.py  –  Indoor Navigation, Neuro Vision Assist
Central orchestrator for ISE 2nd Floor indoor navigation.

NavigationMonitor runs in its own thread and calls _advance() automatically
when the IMU/step-counter detects the segment distance has been covered.
Voice commands (next, continue, repeat) are handled here and NEVER fall
through to Gemini.
"""

import threading
import time
import re

from indoor_nav              import floor_map as _default_map
from indoor_nav.path_planner import plan, resolve
from indoor_nav.instruction_generator import generate_steps, segment_distance, route_preview
from indoor_nav.navigation_state      import NavigationState, NavState
from indoor_nav.navigation_monitor    import NavigationMonitor


_OBSTACLE_REMINDER_S = 10.0
_RESUME_DELAY_S      = 2.0

# Voice commands that must ALWAYS be handled by nav, never by chat
_NAV_COMMANDS = re.compile(
    r"^(next|continue|go|proceed|keep going|where do i go|which way"
    r"|what.?s next|next instruction|continue navigation|go now"
    r"|where now|guide me|repeat|say again|what was that"
    r"|pause|pause navigation|resume|resume navigation"
    r"|cancel|cancel navigation|stop navigation"
    r"|where am i|current location|my location|where)$"
)


class IndoorNavController:

    def __init__(self, speak_fn, imu_read_fn=None, floor_map=None):
        """
        speak_fn    : callable(str)
        imu_read_fn : callable() → (ax, ay, az, gz)  — raw IMU values
                      Pass None to use time-based fallback.
        floor_map   : floor map module; defaults to ISE 2nd floor
        """
        self._speak      = speak_fn
        self._map        = floor_map or _default_map
        self._state      = NavigationState()
        self._lock       = threading.Lock()
        self._last_obs_t = 0.0
        self._paused     = False   # manual pause (not obstacle)

        # Navigation monitor — drives automatic waypoint advancement
        self._monitor = NavigationMonitor(
            imu_read_fn = imu_read_fn or self._dummy_imu,
            state       = self._state,
            advance_fn  = self._advance,
            speak_fn    = speak_fn,
        )

    @staticmethod
    def _dummy_imu():
        """Fallback when no IMU read function provided."""
        raise RuntimeError("IMU not available")

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def is_navigating(self) -> bool:
        return self._state.is_navigating

    def set_imu_reader(self, fn):
        """Inject IMU reader after construction (called from main once IMU is ready)."""
        self._monitor._imu_read = fn

    def handle_input(self, text: str) -> bool:
        """
        Feed user text.
        Returns True  → handled by navigation (NEVER falls through to chat).
        Returns False → not a navigation command.

        When navigation is active, nav-specific commands are always True.
        """
        t = text.strip().lower()

        # ── Hard nav commands — always handled when nav active ─────────────────
        if _NAV_COMMANDS.match(t) and (
            self._state.is_navigating
            or self._state.state in (NavState.AWAITING_START, NavState.AWAITING_DEST)
        ):
            return self._handle_nav_command(t)

        # ── Cancel (works even when idle) ──────────────────────────────────────
        if re.search(r"(cancel|stop)\s+navigation", t):
            self._state.cancel()
            self._monitor.stop()
            self._speak("Navigation cancelled.")
            return True

        # ── Awaiting start location ────────────────────────────────────────────
        if self._state.state == NavState.AWAITING_START:
            cleaned = re.sub(
                r"^(i am (at|in|near)|i.?m (at|in|near)|at|in|near)\s+", "", t
            )
            node = resolve(self._map, cleaned) or resolve(self._map, t)
            if node is None:
                self._speak(
                    f"I don't recognise '{text}' as a location. "
                    "Please say a room number like L-210 or LH-202."
                )
                return True
            _, dest = self._state.get_pending()
            self._state.clear_pending()
            self._begin_navigation(node, dest)
            return True

        # ── Awaiting destination ───────────────────────────────────────────────
        if self._state.state == NavState.AWAITING_DEST:
            node = resolve(self._map, t)
            if node is None:
                self._speak(
                    f"I don't recognise '{text}' as a destination. "
                    "Please say a room number like LH-202 or Staff Room."
                )
                return True
            start, _ = self._state.get_pending()
            self._state.clear_pending()
            self._begin_navigation(start, node)
            return True

        # ── Destination request ────────────────────────────────────────────────
        dest_node = self._extract_destination(text)
        if dest_node is not None:
            current = self._state.current_node
            if current is None:
                self._state.set_awaiting_start(dest_node)
                dest_label = self._map.NODES[dest_node]["label"]
                self._speak(
                    f"I'll navigate you to {dest_label}. "
                    "Where are you currently? Please say your room or location."
                )
            else:
                self._begin_navigation(current, dest_node)
            return True

        return False

    def _handle_nav_command(self, t: str) -> bool:
        """Handle in-session navigation voice commands."""

        if re.search(r"(cancel|stop)\s*navigation|^cancel$", t):
            self._state.cancel()
            self._monitor.stop()
            self._speak("Navigation cancelled.")
            return True

        if re.search(r"pause", t):
            if self._state.state == NavState.NAVIGATING:
                self._paused = True
                self._state.set_state(NavState.OBSTACLE_PAUSED)
                self._speak("Navigation paused. Say resume when ready.")
            return True

        if re.search(r"resume", t):
            if self._state.state == NavState.OBSTACLE_PAUSED:
                self._paused = False
                self._state.set_state(NavState.NAVIGATING)
                self._speak("Resuming navigation. Keep walking.")
            return True

        if re.search(r"where am i|current location|my location|^where$", t):
            node = self._state.current_node
            if node:
                label = self._map.NODES.get(node, {}).get("label", node)
                self._speak(f"You are currently near {label}.")
            else:
                self._speak("I don't know your current location yet.")
            return True

        if re.search(r"repeat|say again|what was that", t):
            instr = self._state.current_instruction
            if instr:
                self._speak(instr)
            return True

        # next / continue / guide me / where do I go — repeat current instruction
        # and also reset monitor so it re-measures from here
        if self._state.is_navigating:
            instr = self._state.current_instruction
            if instr:
                self._monitor.reset_segment()
                self._speak(instr)
        return True

    def obstacle_update(self, has_obstacle: bool, warning_text: str = ""):
        """Called from camera thread. Edge-triggered pause/resume."""
        if self._paused:
            return   # manual pause takes precedence

        changed = self._state.set_obstacle(has_obstacle)

        if not changed:
            if has_obstacle and self._state.state == NavState.OBSTACLE_PAUSED:
                if time.time() - self._last_obs_t >= _OBSTACLE_REMINDER_S:
                    self._speak(f"Still blocked. {warning_text}")
                    self._last_obs_t = time.time()
            return

        if has_obstacle and self._state.state == NavState.OBSTACLE_PAUSED:
            self._last_obs_t = time.time()
            self._speak(f"{warning_text} Navigation paused. Stand by.")
        elif not has_obstacle and self._state.is_navigating:
            threading.Thread(target=self._resume_obstacle, daemon=True).start()

    def set_current_location(self, node_id: str):
        self._state._current_node = node_id

    # ── Internal ───────────────────────────────────────────────────────────────

    def _extract_destination(self, text: str) -> str | None:
        t = text.strip().lower()
        t = re.sub(r"\bti\b",    "to",   t)
        t = re.sub(r"\btakje\b", "take", t)
        t = re.sub(r"\btak\b",   "take", t)

        pat = (
            r"(?:take me to|navigate to|go to|guide me to|"
            r"i want to go to|i need to go to|directions? to|"
            r"route to|how (?:do i|to) get to)\s+(.+)"
        )
        m = re.search(pat, t)
        if m:
            candidate = m.group(1).strip()
            node = resolve(self._map, candidate)
            if node:
                return node
            node = resolve(self._map, re.sub(r"[-\s]", "", candidate))
            if node:
                return node

        return resolve(self._map, t)

    def _begin_navigation(self, start: str, dest: str):
        if start == dest:
            label = self._map.NODES.get(dest, {}).get("label", dest)
            self._speak(f"You are already at {label}.")
            return

        path, total_dist = plan(self._map, start, dest)

        if not path:
            dest_label = self._map.NODES.get(dest, {}).get("label", dest)
            self._speak(f"Sorry, I could not find a route to {dest_label}.")
            return

        steps       = generate_steps(self._map, path)
        seg_dist    = segment_distance(self._map, path, 0)
        dest_label  = self._map.NODES[dest]["label"]
        start_label = self._map.NODES[start]["label"]

        self._state.start_navigation(self._map, path, steps, start, dest, seg_dist)

        # Print full route preview
        print("\n" + route_preview(self._map, path) + "\n")

        self._speak(
            f"Route from {start_label} to {dest_label} found. "
            f"Total distance approximately {total_dist:.1f} metres."
        )

        # Start monitor and speak first instruction after short delay
        self._monitor.reset_segment()
        self._monitor.start()
        threading.Thread(target=self._speak_first, daemon=True).start()

    def _speak_first(self):
        time.sleep(1.2)
        instr = self._state.current_instruction
        if instr:
            self._speak(instr)

    def _advance(self):
        """Called by NavigationMonitor when segment distance is reached."""
        arrived = self._state.advance_step()
        self._monitor.reset_segment()

        if arrived:
            dest_label = self._map.NODES.get(
                self._state.destination, {}
            ).get("label", "destination")
            self._speak(
                f"You have arrived at {dest_label}. "
                "Navigation complete."
            )
            self._monitor.stop()
            self._state.set_state(NavState.IDLE)
        else:
            instr = self._state.current_instruction
            if instr:
                self._speak(f"Waypoint reached. {instr}")

    def _resume_obstacle(self):
        time.sleep(_RESUME_DELAY_S)
        if self._state.state == NavState.NAVIGATING:
            self._speak("Obstacle cleared. Continue walking.")

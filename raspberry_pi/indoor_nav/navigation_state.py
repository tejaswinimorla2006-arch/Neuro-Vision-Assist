"""
navigation_state.py  –  Indoor Navigation, Neuro Vision Assist
Thread-safe navigation state machine.

State machine
-------------
IDLE → AWAITING_START/AWAITING_DEST → NAVIGATING → OBSTACLE_PAUSED → ARRIVED → IDLE

Distance tracking and step detection are handled entirely by NavigationMonitor
+ StepDetector (imu_reader.py).  This class holds only the logical state.
"""

import threading
from enum import Enum, auto


class NavState(Enum):
    IDLE            = auto()
    AWAITING_START  = auto()
    AWAITING_DEST   = auto()
    NAVIGATING      = auto()
    OBSTACLE_PAUSED = auto()
    ARRIVED         = auto()


class NavigationState:

    def __init__(self):
        self._lock          = threading.Lock()
        self._state         = NavState.IDLE
        self._floor_map     = None
        self._path          = []
        self._steps         = []
        self._step_index    = 0
        self._current_node  = None
        self._destination   = None
        self._segment_dist  = 0.0
        self._walked_dist   = 0.0
        self._obstacle_on   = False
        self._pending_start = None
        self._pending_dest  = None

    # ── Getters ────────────────────────────────────────────────────────────────

    @property
    def state(self) -> NavState:
        with self._lock:
            return self._state

    @property
    def is_navigating(self) -> bool:
        with self._lock:
            return self._state in (NavState.NAVIGATING, NavState.OBSTACLE_PAUSED)

    @property
    def current_instruction(self) -> str:
        with self._lock:
            if self._step_index < len(self._steps):
                return self._steps[self._step_index]
            return ""

    @property
    def remaining_in_segment(self) -> float:
        """Metres remaining in the current walking segment."""
        with self._lock:
            return max(0.0, round(self._segment_dist - self._walked_dist, 2))

    @property
    def current_node(self) -> str | None:
        with self._lock:
            return self._current_node

    @property
    def destination(self) -> str | None:
        with self._lock:
            return self._destination

    @property
    def path(self) -> list:
        with self._lock:
            return list(self._path)

    @property
    def step_index(self) -> int:
        with self._lock:
            return self._step_index

    @property
    def steps(self) -> list:
        with self._lock:
            return list(self._steps)

    @property
    def obstacle_on(self) -> bool:
        with self._lock:
            return self._obstacle_on

    # ── Setters / mutators ─────────────────────────────────────────────────────

    def start_navigation(self, floor_map, path: list, steps: list,
                         start_node: str, dest_node: str, segment_dist: float):
        with self._lock:
            self._floor_map    = floor_map
            self._path         = path
            self._steps        = steps
            self._step_index   = 0
            self._current_node = start_node
            self._destination  = dest_node
            self._segment_dist = segment_dist
            self._walked_dist  = 0.0
            self._state        = NavState.NAVIGATING

    def advance_step(self) -> bool:
        """Move to next instruction. Returns True if arrived."""
        with self._lock:
            self._step_index  += 1
            self._walked_dist  = 0.0
            # Update current node
            if self._step_index < len(self._path):
                self._current_node = self._path[self._step_index]
            # Update segment distance for new step
            if self._step_index < len(self._path) - 1:
                from indoor_nav.path_planner import get_edge
                edge = get_edge(
                    self._floor_map,
                    self._path[self._step_index],
                    self._path[self._step_index + 1]
                )
                self._segment_dist = edge["distance"] if edge else 0.0
            else:
                self._segment_dist = 0.0
            # Check arrival
            if self._step_index >= len(self._steps) - 1:
                self._state = NavState.ARRIVED
                return True
            return False

    def set_walked_dist(self, dist: float) -> None:
        """Called by NavigationMonitor every tick to keep walked distance in sync."""
        with self._lock:
            self._walked_dist = dist

    def set_obstacle(self, on: bool):
        with self._lock:
            prev             = self._obstacle_on
            self._obstacle_on = on
            if on and self._state == NavState.NAVIGATING:
                self._state = NavState.OBSTACLE_PAUSED
            elif not on and self._state == NavState.OBSTACLE_PAUSED:
                self._state = NavState.NAVIGATING
        return prev != on   # True = state changed

    def cancel(self):
        with self._lock:
            self._state        = NavState.IDLE
            self._path         = []
            self._steps        = []
            self._step_index   = 0
            self._walked_dist  = 0.0
            self._segment_dist = 0.0

    def set_state(self, s: NavState):
        with self._lock:
            self._state = s

    def set_awaiting_dest(self, start_node: str):
        with self._lock:
            self._pending_start = start_node
            self._state         = NavState.AWAITING_DEST

    def set_awaiting_start(self, dest_node: str):
        with self._lock:
            self._pending_dest = dest_node
            self._state        = NavState.AWAITING_START

    def get_pending(self) -> tuple:
        with self._lock:
            return self._pending_start, self._pending_dest

    def clear_pending(self):
        with self._lock:
            self._pending_start = None
            self._pending_dest  = None

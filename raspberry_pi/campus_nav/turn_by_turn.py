"""
turn_by_turn.py - Real-time turn-by-turn navigation engine

Handles:
- Bearing calculations between GPS coordinates
- Turn direction determination (left/right/straight/u-turn)
- Distance-to-next-turn tracking
- Total remaining distance calculation
- ETA calculation from real GPS movement speed
- Navigation announcements at key distances

This is the core of Google-Maps-style turn-by-turn navigation.
"""

import math
import time
from dataclasses import dataclass, replace
from typing import Optional
from collections import deque

from campus_nav.gps_manager import _haversine_meters
from config import (
    DEBUG_LEVEL,
    GPS_FIX_STALE_S,
)


@dataclass(frozen=True)
class NavigationState:
    """Complete snapshot of current navigation state."""
    current_latitude: float
    current_longitude: float
    current_speed_mps: float  # meters per second from GPS
    current_bearing: float  # degrees (0-360) - direction of movement
    
    # Next instruction details
    next_instruction: str  # e.g., "Turn right" or "Continue straight"
    distance_to_instruction_m: float  # distance to next turn
    distance_to_turn_m: float  # alias for above
    
    # Route progress
    current_segment_index: int  # which edge we're on (0 = first edge)
    total_segments: int  # total number of edges in route
    
    # Remaining distance
    remaining_distance_m: float  # distance from current position to destination
    remaining_along_route_m: float  # distance along planned route
    
    # ETA
    eta_seconds: Optional[int]  # None if insufficient speed data
    
    # Fix quality
    gps_satellites: int
    gps_hdop: float
    gps_is_valid: bool


def _bearing_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate bearing (initial compass direction) from point 1 to point 2.
    
    Returns:
        Bearing in degrees (0-360), where:
        0° = North
        90° = East
        180° = South
        270° = West
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    lon_delta = math.radians(lon2 - lon1)
    
    y = math.sin(lon_delta) * math.cos(lat2_rad)
    x = (math.cos(lat1_rad) * math.sin(lat2_rad) -
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(lon_delta))
    
    bearing_rad = math.atan2(y, x)
    bearing_deg = math.degrees(bearing_rad)
    
    # Normalize to 0-360
    return (bearing_deg + 360) % 360


def _angle_difference(angle1: float, angle2: float) -> float:
    """
    Calculate signed angle difference from angle1 to angle2.
    
    Returns:
        Angle in degrees:
        Positive = turn clockwise (right)
        Negative = turn counter-clockwise (left)
        Range: -180 to +180
    """
    diff = angle2 - angle1
    # Normalize to -180 to +180
    while diff > 180:
        diff -= 360
    while diff < -180:
        diff += 360
    return diff


def _classify_turn(incoming_bearing: float, outgoing_bearing: float) -> str:
    """
    Classify turn direction based on bearing change.
    
    Args:
        incoming_bearing: bearing of current segment (where we came from)
        outgoing_bearing: bearing of next segment (where we're going)
    
    Returns:
        Descriptive string: "Continue straight", "Turn right", "Turn left", "U-turn", "Bear left", "Bear right"
    """
    angle_change = _angle_difference(incoming_bearing, outgoing_bearing)
    
    # Thresholds (degrees)
    if abs(angle_change) <= 15:
        return "Continue straight"
    elif 15 < angle_change <= 45:
        return "Bear right"
    elif 45 < angle_change <= 135:
        return "Turn right"
    elif angle_change > 135:
        return "U-turn"
    elif -15 >= angle_change >= -45:
        return "Bear left"
    elif -45 >= angle_change >= -135:
        return "Turn left"
    else:  # angle_change <= -135
        return "U-turn"


class TurnByTurnEngine:
    """
    Tracks real-time turn-by-turn navigation.
    
    Updates on each GPS fix to determine:
    - Current instruction
    - Distance to next turn
    - Total remaining distance
    - Estimated time remaining
    - When to announce turns
    """
    
    def __init__(self):
        """Initialize turn-by-turn engine."""
        self._lock = threading.Lock()
        
        # Current route info
        self._route_nodes: list[str] = []  # node IDs
        self._route_edges: list[tuple[str, str]] = []  # (from_id, to_id) pairs
        self._current_segment_index: int = -1  # which edge (-1 = not navigating)
        
        # GPS tracking
        self._gps_history: deque = deque(maxlen=10)  # recent GPS speeds for ETA
        self._last_gps_lat: float | None = None
        self._last_gps_lon: float | None = None
        self._last_gps_time: float = 0.0
        
        # Announcement tracking
        self._last_announcement: str | None = None
        self._last_announcement_time: float = 0.0
        self._announced_distances: set[int] = set()  # distances where we've announced
        
        # Config
        self._min_speed_samples = 5  # need at least 5 speed samples for ETA
        self._announcement_deadband_s = 1.0  # don't announce same thing within 1s
        
    def set_route(self, route_nodes: list[str]):
        """
        Initialize route. Should be called when a new navigation route starts.
        
        Args:
            route_nodes: list of node IDs from start to destination
        """
        with self._lock:
            self._route_nodes = route_nodes
            self._route_edges = [(route_nodes[i], route_nodes[i+1]) 
                                for i in range(len(route_nodes) - 1)]
            self._current_segment_index = 0
            self._gps_history.clear()
            self._announced_distances.clear()
            self._last_gps_lat = None
            self._last_gps_lon = None
    
    def advance_segment(self):
        """Move to the next segment in the route."""
        with self._lock:
            if self._current_segment_index < len(self._route_edges) - 1:
                self._current_segment_index += 1
                self._announced_distances.clear()
    
    def update_position(self, latitude: float, longitude: float, 
                       speed_mps: float, fix_satellites: int, fix_hdop: float,
                       fix_valid: bool, nodes_dict: dict) -> NavigationState:
        """
        Update navigation with new GPS position.
        
        Args:
            latitude, longitude: current GPS position
            speed_mps: speed from GPS (meters per second)
            fix_satellites: number of satellites
            fix_hdop: horizontal dilution of precision
            fix_valid: whether fix is valid
            nodes_dict: NODES dict from campus_graph (for coordinates)
        
        Returns:
            NavigationState with complete navigation information
        """
        with self._lock:
            # Update GPS speed history
            if fix_valid and speed_mps >= 0:
                self._gps_history.append(speed_mps)
            
            if self._current_segment_index < 0 or self._current_segment_index >= len(self._route_edges):
                # Not navigating or at end
                return NavigationState(
                    current_latitude=latitude,
                    current_longitude=longitude,
                    current_speed_mps=speed_mps,
                    current_bearing=0.0,
                    next_instruction="Navigation not active",
                    distance_to_instruction_m=0.0,
                    distance_to_turn_m=0.0,
                    current_segment_index=self._current_segment_index,
                    total_segments=len(self._route_edges),
                    remaining_distance_m=0.0,
                    remaining_along_route_m=0.0,
                    eta_seconds=None,
                    gps_satellites=fix_satellites,
                    gps_hdop=fix_hdop,
                    gps_is_valid=fix_valid,
                )
            
            # Get current and next segment info
            from_node_id, to_node_id = self._route_edges[self._current_segment_index]
            from_meta = nodes_dict.get(from_node_id, {})
            to_meta = nodes_dict.get(to_node_id, {})
            
            # If either node lacks coordinates, we can't do turn-by-turn
            if (from_meta.get("lat") is None or to_meta.get("lat") is None):
                return NavigationState(
                    current_latitude=latitude,
                    current_longitude=longitude,
                    current_speed_mps=speed_mps,
                    current_bearing=0.0,
                    next_instruction="Continue to destination",
                    distance_to_instruction_m=0.0,
                    distance_to_turn_m=0.0,
                    current_segment_index=self._current_segment_index,
                    total_segments=len(self._route_edges),
                    remaining_distance_m=0.0,
                    remaining_along_route_m=0.0,
                    eta_seconds=None,
                    gps_satellites=fix_satellites,
                    gps_hdop=fix_hdop,
                    gps_is_valid=fix_valid,
                )
            
            # Calculate bearing for current segment
            from_lat, from_lon = from_meta["lat"], from_meta["lon"]
            to_lat, to_lon = to_meta["lat"], to_meta["lon"]
            current_segment_bearing = _bearing_between(from_lat, from_lon, to_lat, to_lon)
            
            # Distance from current position to end of current segment
            distance_to_next_node = _haversine_meters(latitude, longitude, to_lat, to_lon)
            
            # Determine next instruction
            next_instruction = "Continue"
            if self._current_segment_index + 1 < len(self._route_edges):
                # Look ahead to the next segment for turn prediction
                next_from_id, next_to_id = self._route_edges[self._current_segment_index + 1]
                next_from_meta = nodes_dict.get(next_from_id, {})
                next_to_meta = nodes_dict.get(next_to_id, {})
                
                if next_from_meta.get("lat") is not None and next_to_meta.get("lat") is not None:
                    next_segment_bearing = _bearing_between(
                        next_from_meta["lat"], next_from_meta["lon"],
                        next_to_meta["lat"], next_to_meta["lon"]
                    )
                    next_instruction = _classify_turn(current_segment_bearing, next_segment_bearing)
            
            # Calculate total remaining distance
            remaining_distance = distance_to_next_node
            for i in range(self._current_segment_index + 1, len(self._route_edges)):
                edge_from_id, edge_to_id = self._route_edges[i]
                edge_from_meta = nodes_dict.get(edge_from_id, {})
                edge_to_meta = nodes_dict.get(edge_to_id, {})
                
                if edge_from_meta.get("lat") is not None and edge_to_meta.get("lat") is not None:
                    remaining_distance += _haversine_meters(
                        edge_from_meta["lat"], edge_from_meta["lon"],
                        edge_to_meta["lat"], edge_to_meta["lon"]
                    )
            
            # Calculate ETA
            eta_seconds = None
            if len(self._gps_history) >= self._min_speed_samples:
                # Use median of recent speeds to avoid outliers
                speeds = sorted(self._gps_history)
                median_speed = speeds[len(speeds) // 2]
                
                if median_speed > 0.1:  # at least 0.1 m/s
                    eta_seconds = int(remaining_distance / median_speed)
            
            # Get current bearing (if we have history)
            current_bearing = 0.0
            if self._last_gps_lat is not None and self._last_gps_lon is not None:
                current_bearing = _bearing_between(
                    self._last_gps_lat, self._last_gps_lon,
                    latitude, longitude
                )
            
            # Update history for next call
            self._last_gps_lat = latitude
            self._last_gps_lon = longitude
            self._last_gps_time = time.monotonic()
            
        return NavigationState(
            current_latitude=latitude,
            current_longitude=longitude,
            current_speed_mps=speed_mps,
            current_bearing=current_bearing,
            next_instruction=next_instruction,
            distance_to_instruction_m=distance_to_next_node,
            distance_to_turn_m=distance_to_next_node,
            current_segment_index=self._current_segment_index,
            total_segments=len(self._route_edges),
            remaining_distance_m=remaining_distance,
            remaining_along_route_m=remaining_distance,
            eta_seconds=eta_seconds,
            gps_satellites=fix_satellites,
            gps_hdop=fix_hdop,
            gps_is_valid=fix_valid,
        )
    
    def should_announce(self, current_instruction: str, distance_to_turn_m: float) -> bool:
        """
        Determine if we should announce the current instruction.
        
        Uses hysteresis to avoid announcing repeatedly.
        
        Args:
            current_instruction: the instruction to potentially announce
            distance_to_turn_m: distance to the turn
        
        Returns:
            True if we should announce now
        """
        with self._lock:
            now = time.monotonic()
            
            # Don't repeat same message too frequently
            if (self._last_announcement == current_instruction and 
                now - self._last_announcement_time < self._announcement_deadband_s):
                return False
            
            # Define announcement distances (meters)
            announcement_thresholds = [400, 200, 100, 50, 25, 10, 5, 0]
            
            # Check if we're crossing a threshold
            for threshold in announcement_thresholds:
                if (distance_to_turn_m <= threshold and 
                    threshold not in self._announced_distances):
                    self._announced_distances.add(threshold)
                    self._last_announcement = current_instruction
                    self._last_announcement_time = now
                    return True
            
            return False


# Need to import threading here to avoid circular imports
import threading

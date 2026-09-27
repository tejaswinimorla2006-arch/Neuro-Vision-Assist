# Turn-by-Turn Navigation System — Implementation Guide

## Overview

The Neuro-Vision-Assist campus navigation system now includes **Google Maps-style turn-by-turn navigation** for outdoor routes. The system provides:

✅ Real-time GPS position tracking
✅ Route calculation via Dijkstra algorithm
✅ Live bearing and direction calculations (N, NE, E, SE, S, SW, W, NW, etc.)
✅ Next-turn instruction classification (straight, left, right, U-turn, bear left, bear right)
✅ Distance-to-turn countdown (meters remaining until next instruction)
✅ Live ETA calculation from GPS speed (rolling median, minimum 5 samples)
✅ Automatic turn-by-turn announcements at distance thresholds [100m, 50m, 25m, 10m, 5m]
✅ GPS jitter filtering to prevent false announcements
✅ Route recalculation when user goes off-route
✅ Destination arrival detection with confirmations

## Architecture

### Component: `TurnByTurnEngine`
**File:** `campus_nav/turn_by_turn.py`

Core navigation engine that tracks:
- Current position (latitude, longitude)
- Current bearing (0-360°)
- Current speed (m/s from GPS)
- Route (list of node IDs)
- Next instruction and distance-to-turn
- ETA calculation from rolling speed median

**Key Methods:**
```python
engine.set_route(path)  # Initialize with list of node IDs
nav_state = engine.update_position(
    latitude, longitude, speed_mps, satellites, hdop, valid, nodes_dict
)  # Called per GPS fix, returns NavigationState dataclass
```

**Output: `NavigationState` dataclass:**
```
current_latitude         # GPS position (float)
current_longitude        # GPS position (float)
current_bearing          # Compass bearing 0-360° (float)
current_speed_mps        # Speed in m/s (float)
next_instruction         # "Turn left", "Continue straight", etc. (str)
distance_to_instruction_m # Meters to next turn (float)
distance_to_turn_m       # Alias for above (float)
total_segments           # Total segments in route (int)
current_segment_index    # Current segment number (int)
remaining_distance_m     # Total distance to destination (float)
remaining_along_route_m  # Distance along current segment (float)
eta_seconds              # Estimated time to destination (int or None)
gps_satellites           # Satellite count (int)
gps_hdop                 # Horizontal dilution (float)
gps_is_valid             # Fix validity (bool)
```

### Component: `NavigationController` (Enhanced)
**File:** `campus_nav/navigation_controller.py`

State machine orchestrator that now includes:
- Turn-by-turn engine instance
- Turn-by-turn announcement logic
- Navigation status display

**Key Enhancements:**
1. **Route initialization**: `_handle_destination()` now calls `self._turn_by_turn.set_route(path)`
2. **Position updates**: `update_gps_position(fix)` calls `_update_gps_progress(fix)` which:
   - Passes full GPS fix to turn-by-turn engine
   - Generates announcements via `_process_turn_by_turn_announcements()`
   - Displays status via `_display_navigation_status()` (rate-limited to 5s)
3. **Waypoint advancement**: `_advance_waypoint()` now calls `_turn_by_turn.advance_segment()`
4. **Display**: `_compass_direction(bearing)` converts bearing to compass direction string

## Configuration

**File:** `config.py`

New configuration parameters for turn-by-turn:
```python
TURN_ANNOUNCEMENT_DEADBAND_S = 1.0        # Avoid repeating same announcement
TURN_MIN_SPEED_SAMPLES = 5                # Minimum samples for ETA (at 3-5 fixes/sec)
TURN_THRESHOLDS_M = [400, 200, 100, 50, 25, 10, 5]  # Distance thresholds
TURN_STRAIGHT_DEG = 15                    # Angle tolerance for "straight"
TURN_SLIGHT_DEG = 45                      # Angle for "bear left/right"
TURN_NORMAL_DEG = 135                     # Angle for "turn left/right"
TURN_UTURN_DEG = 135                      # Threshold for U-turn
```

## Data Flow

### GPS → Navigation → Announcements

```
GPS Module (/dev/ttyS0)
    ↓
GPSReader (NMEA parsing, auto-detect port)
    ↓
GPSManager (background polling thread)
    ↓
NavigationController.update_gps_position(fix)
    ↓
TurnByTurnEngine.update_position(latitude, longitude, speed_mps, ...)
    ↓
NavigationState (current bearing, instruction, distance, ETA)
    ↓
NavigationController._process_turn_by_turn_announcements()
    ↓
TTS Speaker: "Turn left in 50 meters"
```

### Bearing Calculations

**Formula:** Initial bearing from point A to point B

```
Δlon = lon_B - lon_A
y = sin(Δlon) × cos(lat_B)
x = cos(lat_A) × sin(lat_B) - sin(lat_A) × cos(lat_B) × cos(Δlon)
bearing = atan2(y, x)  [converted to 0-360°]
```

Uses Haversine distance (haversine_meters) for intermediate waypoint distances.

### Turn Classification

Based on bearing change (incoming vs. outgoing):

```
Angle difference (in degrees, -180 to +180):
  [-15, +15]           → Continue straight
  [+15, +45]           → Bear right
  [+45, +135]          → Turn right
  [+135, +180]         → U-turn
  [+180]               → U-turn (opposite direction)
  [-180, -135]         → U-turn (opposite direction)
  [-135, -45]          → Turn left
  [-45, -15]           → Bear left
```

### Distance-to-Turn Calculation

Combines:
1. **Distance along current segment** (from current position to next waypoint)
2. **Remaining distances** (sum of distances for all subsequent segments)

Total: `distance_to_turn = distance_to_next_waypoint + sum(remaining_segments)`

### ETA Calculation

1. **Collect GPS speed samples** (rolling deque, max 10 samples, ~1 sample per 0.3s)
2. **Calculate rolling median** of speed (once 5+ samples available)
3. **Estimate time**: `ETA = remaining_distance / median_speed`
4. **Display**: "12m 34s" format

## GPS Node Coordinates

Outdoor and outdoor-facing nodes with GPS coordinates:

| Node | Type | Latitude | Longitude | Description |
|------|------|----------|-----------|-------------|
| main_gate | outdoor | 12.9716 | 77.5946 | Campus entrance |
| reception | indoor (outdoor-facing) | 12.97175 | 77.5946 | Building entry |
| parking | outdoor | 12.9716 | 77.59478 | Parking area |
| sports_ground | outdoor | 12.97205 | 77.5946 | Sports field |

**Note:** Other indoor locations (Block A, B, C, Library, Cafeteria, etc.) do NOT have GPS coordinates. Routes including these nodes will:
- Calculate distances using static graph distances
- Generate turn-by-turn guidance only for outdoor segments
- Skip bearing calculations for indoor-only transitions

## Testing

### Unit Tests
**File:** `turn_by_turn_test.py`

Run: `python3 turn_by_turn_test.py`

Tests:
- ✓ Bearing calculations (cardinal directions)
- ✓ Turn classification (straight, left, right, U-turn, bear, etc.)
- ✓ Route initialization and position tracking
- ✓ ETA calculation from rolling speed median
- ✓ GPS jitter filtering (±3m)
- ✓ Announcement timing and hysteresis

### GPS Simulation
**File:** `gps_simulation_test.py` (existing, still passes)

Run: `python3 gps_simulation_test.py`

Verifies:
- Backward compatibility with existing system
- Waypoint detection
- Destination arrival
- Off-route detection
- Route recalculation

### Live GPS Testing

1. **Start navigation:**
   ```bash
   python3 run_campus_nav.py
   ```

2. **Type destination:**
   ```
   > Library
   [NAV] Route to Library (85 meters) starting...
   [NAV VOICE] Route to Library found. Turn left. Walk 40 meters to Library.
   ```

3. **Monitor turn-by-turn output:**
   ```
   [NAV TURN] Turn left in 100 meters.
   [NAV TURN] Turn left in 50 meters.
   [NAV TURN] Turn left in 25 meters.
   [NAV TURN] Turn left now.
   ```

4. **View navigation status** (DEBUG_LEVEL="BASIC"):
   ```
   ============================================================
   CAMPUS NAVIGATION STATUS
   ============================================================
   Position:        12.971600, 77.594690
   Direction:       270.0° (W)
   Speed:           3.6 km/h
   Next Action:     Turn left
   Distance to:     45.2 m
   Total Remaining: 85.0 m
   ETA:             1m 24s
   Satellites:      8
   HDOP:            0.95
   ============================================================
   ```

## Usage Examples

### Example 1: Navigate from Main Gate to Parking

```python
from campus_nav.navigation_controller import NavigationController

nav = NavigationController(start_location="main_gate")
nav.start()  # Print banner

# User enters destination
nav.handle_input("Parking")
# Output: Route to Parking (22 meters) starting...
#         Route to Parking found. Turn right. Walk 22 meters to Parking.

# Simulate GPS updates (normally from GPSManager)
fix = GPSFix(latitude=12.9716, longitude=77.5946, ...)
nav.update_gps_position(fix)

fix = GPSFix(latitude=12.97161, longitude=77.59470, ...)
nav.update_gps_position(fix)  # Announces "Turn right in 10 meters"

fix = GPSFix(latitude=12.97162, longitude=77.59475, ...)
nav.update_gps_position(fix)  # Announces "Turn right now"
```

### Example 2: Multi-Leg Indoor/Outdoor Route

```
main_gate (outdoor) → reception (outdoor-facing) → block_a (indoor)
```

- Turn-by-turn guidance: main_gate → reception (bearing-based)
- Static guidance: reception → block_a (no GPS)
- Announcements: Only for main_gate → reception segment

### Example 3: Handling Route Changes

If user goes off-route:
1. System detects GPS position > OFF_ROUTE_RADIUS_M from planned path
2. Confirms off-route with GPS_OFF_ROUTE_CONFIRMATIONS consecutive fixes
3. Finds nearest GPS-enabled node
4. Recalculates route
5. Announces new route and initial instruction

```
[NAV] Off-route detected: 30.0m from planned route
[NAV VOICE] Route recalculated. 110 meters. Turn left. Walk 40 meters to...
```

## Limitations & Design Notes

### GPS Node Limitations
- Only 4 nodes have GPS coordinates (outdoor or outdoor-facing)
- More outdoor nodes require real GPS coordinates (user must provide, NOT invented)
- Indoor-only routes don't use turn-by-turn guidance

### Speed & ETA Limitations
- ETA shows "None" until 5 valid speed samples collected (~1.5 seconds at 3-5 fixes/sec)
- Requires GPS in motion mode (speed > 0) for accurate ETA
- Stationary users (speed = 0) won't update ETA

### Bearing Accuracy
- Bearing becomes unreliable at very low speeds (< 0.1 m/s)
- Bearing fluctuates when stationary due to GPS noise
- Actual direction is best determined by IMU compass (not yet integrated)

### Announcement Timing
- Distance thresholds: [400m, 200m, 100m, 50m, 25m, 10m, 5m]
- Once announcement made at threshold, won't repeat until passing next threshold
- Deadband period: 1 second (prevents stutter from GPS jitter)

## Files Modified

| File | Changes |
|------|---------|
| `campus_nav/turn_by_turn.py` | NEW - Core engine (350+ lines) |
| `campus_nav/navigation_controller.py` | Enhanced - Added turn-by-turn integration, announcements, display |
| `config.py` | Added 7 new turn-by-turn configuration parameters |
| `campus_nav/campus_graph.json` | Added GPS coordinate for "reception" node |
| `turn_by_turn_test.py` | NEW - Comprehensive test suite (280+ lines) |

## Files Preserved (No Changes)

- `campus_nav/dijkstra.py` — Routing algorithm unchanged
- `campus_nav/instruction_generator.py` — Static instructions unchanged
- `campus_nav/gps_manager.py` — GPS polling unchanged (signature compatible)
- `campus_nav/tts_manager.py` — TTS interface unchanged
- All camera, IMU, chatbot modules — Untouched

## Next Steps

### Immediate (Ready to Deploy)
1. Run `python3 turn_by_turn_test.py` to verify logic
2. Test with `python3 run_campus_nav.py` and real GPS
3. Walk around campus and verify announcements match reality

### Future Enhancements
1. **Integrate magnetometer compass** for heading when stationary
2. **Add more GPS nodes** if user provides real coordinates
3. **Enhance instruction_generator** to include bearing information
4. **Add pre-turn preview** ("In 500m, turn left at the blue building")
5. **Implement lane guidance** for multi-lane roads
6. **Add alternate route suggestions** for off-route events

## Troubleshooting

### Problem: "No announcements received"
**Check:**
1. GPS is valid and updating (`gps_diagnostic.py`)
2. Route has GPS-enabled nodes (check campus_graph.json)
3. DEBUG_LEVEL is set to "BASIC" or "VERBOSE"
4. Turn-by-turn thresholds are reasonable (default: 5-400m)

### Problem: "Announcements repeated too frequently"
**Cause:** GPS jitter causing fluctuating distances
**Solution:** Increase TURN_ANNOUNCEMENT_DEADBAND_S in config.py (default: 1.0s)

### Problem: "ETA always shows None"
**Cause:** Insufficient speed samples
**Check:**
1. GPS is providing valid speed data (check gps_diagnostic.py)
2. User is moving (speed > 0)
3. Waiting for 5 samples (~1-2 seconds at 3-5 fixes/second)

### Problem: "Bearing seems wrong (pointing opposite direction)"
**Cause:** IMU compass integration not yet implemented
**Note:** GPS bearing is inherently unreliable when stationary or moving slowly
**Workaround:** System uses speed-weighted bearing updates (low speed = low confidence)

## References

- **Haversine Formula:** https://en.wikipedia.org/wiki/Haversine_formula
- **Bearing Calculation:** https://www.movable-type.co.uk/scripts/latlong.html
- **NMEA GPS Protocol:** https://en.wikipedia.org/wiki/NMEA_0183
- **Dijkstra Algorithm:** https://en.wikipedia.org/wiki/Dijkstra%27s_algorithm

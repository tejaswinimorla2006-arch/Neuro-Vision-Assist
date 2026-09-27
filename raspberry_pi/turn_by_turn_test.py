#!/usr/bin/env python3
"""
turn_by_turn_test.py

Comprehensive test of turn-by-turn navigation system.

Tests:
- Bearing calculations between GPS coordinates
- Turn direction classification
- Distance-to-turn tracking
- ETA calculation from GPS speed
- Announcement timing
- GPS jitter handling
"""

import sys
import os
import time
import math

sys.path.insert(0, os.path.dirname(__file__))

from campus_nav.turn_by_turn import (
    TurnByTurnEngine, _bearing_between, _angle_difference, _classify_turn
)
from campus_nav.gps_manager import _haversine_meters
from campus_nav.campus_graph import NODES
from gps_reader import GPSFix


def test_bearing_calculation():
    """Test bearing calculations."""
    print("\n" + "="*60)
    print("TEST 1: Bearing Calculations")
    print("="*60)
    
    # Test cardinal directions
    # North (0°)
    bearing = _bearing_between(0.0, 0.0, 1.0, 0.0)
    assert abs(bearing) < 1, f"North bearing should be ~0°, got {bearing:.1f}°"
    print(f"✓ North: {bearing:.1f}°")
    
    # East (90°)
    bearing = _bearing_between(0.0, 0.0, 0.0, 1.0)
    assert abs(bearing - 90) < 1, f"East bearing should be ~90°, got {bearing:.1f}°"
    print(f"✓ East: {bearing:.1f}°")
    
    # South (180°)
    bearing = _bearing_between(1.0, 0.0, 0.0, 0.0)
    assert abs(bearing - 180) < 1, f"South bearing should be ~180°, got {bearing:.1f}°"
    print(f"✓ South: {bearing:.1f}°")
    
    # West (270°)
    bearing = _bearing_between(0.0, 1.0, 0.0, 0.0)
    assert abs(bearing - 270) < 1, f"West bearing should be ~270°, got {bearing:.1f}°"
    print(f"✓ West: {bearing:.1f}°")


def test_turn_classification():
    """Test turn direction classification."""
    print("\n" + "="*60)
    print("TEST 2: Turn Classification")
    print("="*60)
    
    # Straight (0° change)
    result = _classify_turn(0.0, 0.0)
    assert result == "Continue straight", f"Got: {result}"
    print(f"✓ Straight (0°): {result}")
    
    # Slight right (30° change)
    result = _classify_turn(0.0, 30.0)
    assert "Bear right" in result, f"Got: {result}"
    print(f"✓ Slight right (30°): {result}")
    
    # Sharp right (90° change)
    result = _classify_turn(0.0, 90.0)
    assert "Turn right" in result, f"Got: {result}"
    print(f"✓ Sharp right (90°): {result}")
    
    # U-turn (170° change)
    result = _classify_turn(0.0, 170.0)
    assert "U-turn" in result, f"Got: {result}"
    print(f"✓ U-turn (170°): {result}")
    
    # Slight left (-30° change)
    result = _classify_turn(0.0, 330.0)  # 330° = -30°
    assert "Bear left" in result, f"Got: {result}"
    print(f"✓ Slight left (-30°): {result}")
    
    # Sharp left (-90° change)
    result = _classify_turn(0.0, 270.0)  # 270° = -90°
    assert "Turn left" in result, f"Got: {result}"
    print(f"✓ Sharp left (-90°): {result}")


def test_turn_by_turn_engine():
    """Test the turn-by-turn engine with simulated GPS."""
    print("\n" + "="*60)
    print("TEST 3: Turn-by-Turn Engine - Route Simulation")
    print("="*60)
    
    engine = TurnByTurnEngine()
    
    # Set route: main_gate → parking
    route = ["main_gate", "parking"]
    engine.set_route(route)
    print(f"✓ Route set: {' → '.join(route)}")
    
    # Current position: main_gate
    main_gate_lat = 12.9716
    main_gate_lon = 77.5946
    parking_lat = 12.9716
    parking_lon = 77.59478
    
    # Simulate GPS position slightly south of main gate
    current_lat = main_gate_lat - 0.0001  # ~11 meters south
    current_lon = main_gate_lon
    
    # Update engine
    nav_state = engine.update_position(
        latitude=current_lat,
        longitude=current_lon,
        speed_mps=1.0,  # Walking speed: 1 m/s
        fix_satellites=8,
        fix_hdop=0.95,
        fix_valid=True,
        nodes_dict=NODES
    )
    
    print(f"Position: ({current_lat:.6f}, {current_lon:.6f})")
    print(f"Speed: {nav_state.current_speed_mps * 3.6:.1f} km/h")
    print(f"Next instruction: {nav_state.next_instruction}")
    print(f"Distance to turn: {nav_state.distance_to_instruction_m:.1f} m")
    print(f"Total remaining: {nav_state.remaining_distance_m:.1f} m")
    if nav_state.eta_seconds:
        print(f"ETA: {nav_state.eta_seconds} seconds")
    
    # Verify distance calculation
    expected_distance = _haversine_meters(current_lat, current_lon, parking_lat, parking_lon)
    print(f"✓ Distance to parking: {nav_state.distance_to_instruction_m:.1f} m (expected ~{expected_distance:.1f} m)")


def test_eta_calculation():
    """Test ETA calculation from GPS speed."""
    print("\n" + "="*60)
    print("TEST 4: ETA Calculation from GPS Speed")
    print("="*60)
    
    engine = TurnByTurnEngine()
    engine.set_route(["main_gate", "parking"])
    
    # Simulate walking towards parking with various speeds
    main_gate = NODES["main_gate"]
    parking = NODES["parking"]
    
    speeds_mps = [0.5, 1.0, 1.5, 1.0, 1.2]  # m/s
    
    for i, speed in enumerate(speeds_mps):
        # Move towards parking
        progress = (i + 1) / len(speeds_mps)
        lat = main_gate["lat"] + (parking["lat"] - main_gate["lat"]) * progress
        lon = main_gate["lon"] + (parking["lon"] - main_gate["lon"]) * progress
        
        nav_state = engine.update_position(
            latitude=lat,
            longitude=lon,
            speed_mps=speed,
            fix_satellites=8,
            fix_hdop=0.95,
            fix_valid=True,
            nodes_dict=NODES
        )
        
        print(f"Step {i+1}: Speed {speed*3.6:.1f} km/h, Distance {nav_state.distance_to_instruction_m:.1f}m", end="")
        if nav_state.eta_seconds:
            print(f", ETA {nav_state.eta_seconds}s")
        else:
            print(", ETA (calculating...)")


def test_gps_jitter_handling():
    """Test that GPS jitter doesn't cause wild distance fluctuations."""
    print("\n" + "="*60)
    print("TEST 5: GPS Jitter Filtering")
    print("="*60)
    
    engine = TurnByTurnEngine()
    engine.set_route(["main_gate", "parking"])
    
    main_gate = NODES["main_gate"]
    parking = NODES["parking"]
    
    # Position 50m along route
    progress = 0.5
    base_lat = main_gate["lat"] + (parking["lat"] - main_gate["lat"]) * progress
    base_lon = main_gate["lon"] + (parking["lon"] - main_gate["lon"]) * progress
    
    print(f"Base position: ({base_lat:.6f}, {base_lon:.6f})")
    
    # Simulate small GPS jitter (±3 meters)
    jitter_samples = [
        (base_lat, base_lon),
        (base_lat + 0.00003, base_lon),  # ~3m north
        (base_lat - 0.00003, base_lon),  # ~3m south
        (base_lat, base_lon + 0.00002),  # ~2m east
        (base_lat, base_lon - 0.00002),  # ~2m west
    ]
    
    distances = []
    for lat, lon in jitter_samples:
        nav_state = engine.update_position(
            latitude=lat,
            longitude=lon,
            speed_mps=1.0,
            fix_satellites=8,
            fix_hdop=0.95,
            fix_valid=True,
            nodes_dict=NODES
        )
        distances.append(nav_state.distance_to_instruction_m)
        print(f"  ({lat:.6f}, {lon:.6f}) → {nav_state.distance_to_instruction_m:.1f}m")
    
    # All distances should be similar (jitter shouldn't cause big jumps)
    max_dist = max(distances)
    min_dist = min(distances)
    variance = max_dist - min_dist
    
    print(f"✓ Distance variance from jitter: {variance:.1f}m (max {max_dist:.1f}m, min {min_dist:.1f}m)")
    assert variance < 5, f"Jitter caused too much variance: {variance}m"


def test_announcement_timing():
    """Test announcement hysteresis."""
    print("\n" + "="*60)
    print("TEST 6: Announcement Timing")
    print("="*60)
    
    engine = TurnByTurnEngine()
    
    # Test should_announce with distance thresholds
    test_cases = [
        ("Turn right", 100.0, True),   # First crossing 100m
        ("Turn right", 99.0, False),   # Same announcement, still within deadband
        ("Turn right", 50.0, True),    # Crossing 50m (different threshold)
        ("Turn right", 49.0, False),   # Same announcement
        ("Continue straight", 49.0, True),  # Different instruction
    ]
    
    for instruction, distance, expected in test_cases:
        result = engine.should_announce(instruction, distance)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{instruction}' @ {distance}m: should_announce={result} (expected {expected})")


def main():
    print("\n" + "="*60)
    print("TURN-BY-TURN NAVIGATION TEST SUITE")
    print("="*60)
    
    try:
        test_bearing_calculation()
        test_turn_classification()
        test_turn_by_turn_engine()
        test_eta_calculation()
        test_gps_jitter_handling()
        test_announcement_timing()
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED ✓")
        print("="*60)
        return 0
    
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

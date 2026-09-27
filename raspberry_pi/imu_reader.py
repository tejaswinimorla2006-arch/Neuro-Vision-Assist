"""
imu_reader.py - Neuro Vision Assist
MPU9250 hardware driver.

Public API
----------
init_mpu()        : wake sensor + calibrate offsets (call once at startup)
read_raw_imu()    : returns (ax, ay, az, gz) calibrated in g-units and °/s
get_orientation() : returns (pitch, roll, yaw_rate, tilt_alert)

Step detection has moved to step_detector.py (StepDetector class).
Sensor fusion has moved to sensor_fusion.py (SensorFusion class).

Startup calibration
-------------------
init_mpu() collects 200 samples at rest and computes mean offsets for
ax, ay, az, gz.  These are subtracted from every subsequent reading.
This removes sensor bias without requiring a calibration file.

Wiring:
  VCC -> Pin 1  (3.3V)
  GND -> Pin 6  (GND)
  SDA -> Pin 3  (GPIO2)
  SCL -> Pin 5  (GPIO3)
  AD0 -> Pin 9  (GND)  → I2C address = 0x68
"""

import math
import time

import smbus2

from config import (
    MPU_ADDR, PWR_MGMT_1,
    ACCEL_XOUT_H, GYRO_XOUT_H,
    ACCEL_SCALE, GYRO_SCALE,
    TILT_ALERT_ANGLE,
    MAG_ADDR, MAG_XOUT_L, MAG_SCALE,
    HEADING_ALPHA,
)

bus = smbus2.SMBus(1)

# ── Calibration offsets (populated by init_mpu) ───────────────────────────────
_offset_ax: float = 0.0
_offset_ay: float = 0.0
_offset_az: float = 0.0
_offset_gz: float = 0.0
_mag_available: bool = False


# ── Hardware access ────────────────────────────────────────────────────────────

def init_mpu() -> None:
    """
    Wake the MPU9250, enable magnetometer bypass, calibrate offsets.
    Call once at startup before any other function.
    Keep the device still during the ~2 s calibration window.
    """
    global _offset_ax, _offset_ay, _offset_az, _offset_gz, _mag_available

    bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)
    time.sleep(0.1)

    # Enable I2C bypass so AK8963 is directly accessible on the bus
    try:
        bus.write_byte_data(MPU_ADDR, 0x37, 0x02)   # INT_PIN_CFG
        time.sleep(0.05)
        bus.write_byte_data(MAG_ADDR, 0x0A, 0x16)   # AK8963 continuous 100 Hz 16-bit
        time.sleep(0.05)
        _mag_available = True
        print("[IMU] Magnetometer (AK8963) enabled.")
    except Exception as e:
        _mag_available = False
        print(f"[IMU] Magnetometer unavailable: {e}. Heading from gyro only.")

    # Collect 200 still samples for offset calibration
    print("[IMU] Calibrating offsets — keep device still for 2 seconds...")
    n = 200
    sax = say = saz = sgz = 0.0
    for _ in range(n):
        ax, ay, az, gz = _read_raw_uncalibrated()
        sax += ax; say += ay; saz += az; sgz += gz
        time.sleep(0.01)

    # Subtract the full 3-axis mean vector so the calibrated output is
    # zero-mean at rest in whatever orientation the device is mounted.
    # Do NOT add 1g back on any axis: step_detector.py has its own
    # orientation-independent LP-filter gravity removal that handles
    # any mounting angle correctly.
    _offset_ax = sax / n
    _offset_ay = say / n
    _offset_az = saz / n   # no +1g correction: step_detector removes gravity
    _offset_gz = sgz / n

    print(
        f"[IMU] Offsets: ax={_offset_ax:.4f}g  ay={_offset_ay:.4f}g  "
        f"az={_offset_az:.4f}g  gz={_offset_gz:.2f}°/s"
    )


def _read_reg16(addr: int) -> int:
    """Read a signed 16-bit value from two consecutive registers."""
    high  = bus.read_byte_data(MPU_ADDR, addr)
    low   = bus.read_byte_data(MPU_ADDR, addr + 1)
    value = (high << 8) | low
    return value - 65536 if value > 32768 else value


def _read_raw_uncalibrated() -> tuple[float, float, float, float]:
    ax = _read_reg16(ACCEL_XOUT_H)     / ACCEL_SCALE
    ay = _read_reg16(ACCEL_XOUT_H + 2) / ACCEL_SCALE
    az = _read_reg16(ACCEL_XOUT_H + 4) / ACCEL_SCALE
    gz = _read_reg16(GYRO_XOUT_H  + 4) / GYRO_SCALE
    return ax, ay, az, gz


def read_raw_imu() -> tuple[float, float, float, float]:
    """
    Returns calibrated (ax, ay, az, gz).
    ax/ay/az in g-units, gz in °/s.
    """
    ax, ay, az, gz = _read_raw_uncalibrated()
    return (
        ax - _offset_ax,
        ay - _offset_ay,
        az - _offset_az,
        gz - _offset_gz,
    )


def read_magnetometer() -> tuple[float, float, float] | None:
    """Returns (mx, my, mz) in µT, or None if magnetometer unavailable."""
    if not _mag_available:
        return None
    try:
        data = bus.read_i2c_block_data(MAG_ADDR, MAG_XOUT_L, 6)
        mx = (data[1] << 8 | data[0])
        my = (data[3] << 8 | data[2])
        mz = (data[5] << 8 | data[4])
        if mx > 32767: mx -= 65536
        if my > 32767: my -= 65536
        if mz > 32767: mz -= 65536
        return mx * MAG_SCALE, my * MAG_SCALE, mz * MAG_SCALE
    except Exception:
        return None


def get_orientation() -> tuple[float, float, float, bool]:
    """
    Returns (pitch, roll, yaw_rate, tilt_alert).
    pitch/roll in degrees, yaw_rate in °/s.
    """
    ax, ay, az, gz = read_raw_imu()
    pitch      = math.atan2(ay, math.sqrt(ax**2 + az**2)) * (180 / math.pi)
    roll       = math.atan2(-ax, az) * (180 / math.pi)
    tilt_alert = abs(pitch) > TILT_ALERT_ANGLE or abs(roll) > TILT_ALERT_ANGLE
    return round(pitch, 2), round(roll, 2), round(gz, 2), tilt_alert


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from step_detector import StepDetector
    init_mpu()
    print("[OK] IMU initialized. Reading data... (Ctrl+C to stop)")
    detector = StepDetector()
    while True:
        try:
            pitch, roll, yaw, alert = get_orientation()
            ax, ay, az, gz = read_raw_imu()
            detector.update(ax, ay, az, gz)
            status = " ⚠ TILT" if alert else ""
            print(
                f"Pitch:{pitch:7.2f}°  Roll:{roll:7.2f}°  "
                f"Steps:{detector.step_count}  Dist:{detector.distance_m:.2f}m  "
                f"Motion:{detector.motion_state}{status}"
            )
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(0.02)

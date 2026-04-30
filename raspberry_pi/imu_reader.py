"""
Module 2: MPU9250 IMU Reader
Reads accelerometer and gyroscope data via I2C.
Calculates Pitch, Roll, Yaw (yaw is gyro-integrated, not magnetometer-based).

Wiring:
  VCC  -> Pin 1  (3.3V)
  GND  -> Pin 6  (GND)
  SDA  -> Pin 3  (GPIO2)
  SCL  -> Pin 5  (GPIO3)
  AD0  -> Pin 9  (GND) -> I2C address = 0x68
"""

import smbus2
import time
import math

MPU_ADDR = 0x68
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H  = 0x43

ACCEL_SCALE = 16384.0   # ±2g
GYRO_SCALE  = 131.0     # ±250°/s

bus = smbus2.SMBus(1)

def init_mpu():
    bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)  # Wake up MPU9250

def read_raw_data(addr):
    high = bus.read_byte_data(MPU_ADDR, addr)
    low  = bus.read_byte_data(MPU_ADDR, addr + 1)
    value = (high << 8) | low
    if value > 32768:
        value -= 65536
    return value

def get_orientation():
    ax = read_raw_data(ACCEL_XOUT_H)     / ACCEL_SCALE
    ay = read_raw_data(ACCEL_XOUT_H + 2) / ACCEL_SCALE
    az = read_raw_data(ACCEL_XOUT_H + 4) / ACCEL_SCALE

    gx = read_raw_data(GYRO_XOUT_H)     / GYRO_SCALE
    gy = read_raw_data(GYRO_XOUT_H + 2) / GYRO_SCALE
    gz = read_raw_data(GYRO_XOUT_H + 4) / GYRO_SCALE

    pitch = math.atan2(ay, math.sqrt(ax**2 + az**2)) * (180 / math.pi)
    roll  = math.atan2(-ax, az) * (180 / math.pi)
    yaw   = gz  # Gyro Z = yaw rate (not absolute yaw without magnetometer)

    return round(pitch, 2), round(roll, 2), round(yaw, 2)

if __name__ == "__main__":
    init_mpu()
    print("[OK] MPU9250 initialized. Reading data... (Ctrl+C to stop)")
    while True:
        pitch, roll, yaw = get_orientation()
        print(f"Pitch: {pitch}°  Roll: {roll}°  Yaw Rate: {yaw}°/s")
        time.sleep(0.5)

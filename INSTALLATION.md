"""
INSTALLATION.md - Neuro Vision Assist
Complete software setup guide for Raspberry Pi 4
"""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: RASPBERRY PI OS SETUP
# ═══════════════════════════════════════════════════════════════════════════════

1. Flash Raspberry Pi OS (64-bit, Lite or Desktop) to microSD
   - Use Raspberry Pi Imager: https://www.raspberrypi.com/software/
   - Enable SSH in advanced settings if headless

2. Boot Pi and update system:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: ENABLE HARDWARE INTERFACES
# ═══════════════════════════════════════════════════════════════════════════════

Enable Camera, I2C, and Serial:
```bash
sudo raspi-config
```
Navigate:
  - Interface Options → Camera → Enable
  - Interface Options → I2C → Enable
  - Interface Options → Serial Port:
      * Login shell over serial? → No
      * Serial hardware enabled?  → Yes

Reboot:
```bash
sudo reboot
```

Verify after reboot:
```bash
vcgencmd get_camera          # Should show: supported=1 detected=1
sudo i2cdetect -y 1          # Should show 0x68 (IMU address)
ls /dev/ttyS0                # Should exist (GPS serial port)
```

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: INSTALL SYSTEM DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════════

```bash
sudo apt install -y \
    python3-pip \
    python3-opencv \
    i2c-tools \
    python3-smbus \
    libatlas-base-dev \
    libopenblas-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev
```

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: INSTALL PYTHON LIBRARIES
# ═══════════════════════════════════════════════════════════════════════════════

Create requirements.txt:
```
opencv-python==4.8.1.78
ultralytics==8.0.196
smbus2==0.4.3
pyserial==3.5
pynmea2==1.19.0
```

Install:
```bash
pip3 install -r requirements.txt
```

Note: YOLOv8 will auto-download yolov8n.pt (~6MB) on first run.

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: PERFORMANCE OPTIMIZATIONS (OPTIONAL BUT RECOMMENDED)
# ═══════════════════════════════════════════════════════════════════════════════

1. Increase GPU memory for camera:
   ```bash
   sudo nano /boot/config.txt
   ```
   Add:
   ```
   gpu_mem=256
   ```

2. Disable Bluetooth to free up better UART for GPS:
   ```bash
   sudo nano /boot/config.txt
   ```
   Add:
   ```
   dtoverlay=disable-bt
   ```
   Then:
   ```bash
   sudo systemctl disable hciuart
   ```
   Change GPS_PORT in config.py to "/dev/ttyAMA0"

3. Overclock (optional, requires active cooling):
   ```bash
   sudo nano /boot/config.txt
   ```
   Add:
   ```
   over_voltage=6
   arm_freq=2000
   ```

Reboot after changes:
```bash
sudo reboot
```

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: VERIFY INSTALLATION
# ═══════════════════════════════════════════════════════════════════════════════

Test each module individually:

1. Camera:
   ```bash
   python3 camera_test.py
   ```
   Expected: Live video feed, FPS counter

2. IMU:
   ```bash
   python3 imu_reader.py
   ```
   Expected: Pitch/Roll/Yaw readings updating every 0.5s

3. GPS (go outdoors or near window):
   ```bash
   python3 gps_reader.py
   ```
   Expected: Lat/Lon coordinates after 30-90s

4. Object Detection:
   ```bash
   python3 object_detector.py
   ```
   Expected: Bounding boxes on detected objects

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: RUN FULL SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

1. Edit config.py:
   - Set LAPTOP_IP to your laptop's IP address
   - Adjust FRAME_WIDTH/FRAME_HEIGHT if needed (lower = faster)

2. On laptop, start voice receiver:
   ```bash
   python3 voice_receiver.py
   ```

3. On Raspberry Pi:
   ```bash
   python3 main.py
   ```

# ═══════════════════════════════════════════════════════════════════════════════
# TROUBLESHOOTING
# ═══════════════════════════════════════════════════════════════════════════════

Camera not found:
  - Check CSI ribbon cable is fully seated (blue side toward HDMI)
  - Run: vcgencmd get_camera
  - Try: sudo modprobe bcm2835-v4l2

IMU not detected:
  - Run: sudo i2cdetect -y 1
  - If empty, check wiring (SDA/SCL often swapped)
  - If shows 0x69 instead of 0x68, AD0 pin is floating (connect to GND)

GPS no data:
  - Run: cat /dev/ttyS0  (should see NMEA sentences)
  - If permission denied: sudo usermod -aG dialout $USER, then reboot
  - If garbage: wrong baud rate, run: stty -F /dev/ttyS0 9600 raw

Low FPS (<5):
  - Lower FRAME_WIDTH/FRAME_HEIGHT in config.py
  - Set SHOW_PREVIEW = False if running headless
  - Increase gpu_mem in /boot/config.txt

Socket connection refused:
  - Verify laptop and Pi are on same Wi-Fi network
  - Check LAPTOP_IP in config.py matches: ip addr show (Linux) or ipconfig (Windows)
  - Ensure voice_receiver.py is running first

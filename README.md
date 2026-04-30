# Neuro Vision Assist – AI Navigation System for Visually Impaired

## Project Structure

```
Final_year_Prj/
├── raspberry_pi/
│   ├── camera_test.py       # Module 1: Verify camera works
│   ├── imu_reader.py        # Module 2: MPU9250 IMU data
│   ├── object_detector.py   # Module 3: YOLOv8n detection
│   ├── navigation_logic.py  # Module 4: Navigation decisions
│   ├── sender.py            # Module 5: Send message to laptop
│   └── main.py              # Full integrated system
├── laptop/
│   └── voice_receiver.py    # Receive message + speak
├── requirements_pi.txt
├── requirements_laptop.txt
└── README.md
```

---

## Hardware Wiring

### Camera Module (Ribbon Cable)

1. Locate the **CSI port** on the Raspberry Pi 4 — it is the narrow black connector between the HDMI and audio jack.
2. Gently pull up the plastic latch on the CSI port.
3. Insert the ribbon cable with the **blue side facing the HDMI ports**.
4. Push the latch back down firmly.
5. The other end of the ribbon connects to the camera module — blue side faces away from the lens.

> Note: If using Raspberry Pi 5, use the **CAM0 or CAM1** port with the smaller 22-pin connector. An adapter cable may be needed for older camera modules.

---

### MPU9250 IMU (I2C)

| MPU9250 Pin | Raspberry Pi Pin | GPIO    |
|-------------|-----------------|---------|
| VCC         | Pin 1           | 3.3V    |
| GND         | Pin 6           | GND     |
| SDA         | Pin 3           | GPIO2   |
| SCL         | Pin 5           | GPIO3   |
| AD0         | Pin 9           | GND (sets I2C address to 0x68) |

---

### Power Setup (Battery → Pi)

```
3× Li-ion 3.7V Batteries (in parallel for capacity)
        ↓
   TP4056 Module
   IN+  ← Battery positive
   IN-  ← Battery negative
   OUT+ → Boost Converter IN+
   OUT- → Boost Converter IN-
        ↓
   DC-DC Boost Converter
   Set output to 5.1V
   OUT+ → USB-C cable positive (red wire)
   OUT- → USB-C cable negative (black wire)
        ↓
   Raspberry Pi 4 USB-C Power Port
```

> Important: Use a USB-C cable that supports power delivery. Set boost converter output to exactly 5.1V before connecting to Pi.

---

## Setup Instructions

### Step 1: Flash Raspberry Pi OS

1. Download **Raspberry Pi Imager** from https://www.raspberrypi.com/software/
2. Flash **Raspberry Pi OS (64-bit)** to the 64GB microSD card
3. In Imager settings, enable SSH and set Wi-Fi credentials before flashing

### Step 2: Enable Camera and I2C

```bash
sudo raspi-config
```

- Interface Options → Camera → Enable
- Interface Options → I2C → Enable
- Reboot: `sudo reboot`

Verify camera:
```bash
libcamera-hello
```

Verify I2C (MPU9250 should show address 0x68):
```bash
sudo apt install i2c-tools
i2cdetect -y 1
```

### Step 3: Install Dependencies on Raspberry Pi

```bash
sudo apt update
sudo apt install python3-pip python3-opencv -y
pip3 install -r requirements_pi.txt
```

> YOLOv8n model (~6MB) downloads automatically on first run of object_detector.py

### Step 4: Install Dependencies on Laptop

```bash
pip install -r requirements_laptop.txt
```

---

## How to Run

### Step 1: Find Laptop IP Address

On laptop (macOS/Linux):
```bash
ifconfig | grep "inet "
```
On Windows:
```bash
ipconfig
```
Note the IP address (e.g., `10.201.63.146`)

### Step 2: Set Laptop IP in sender.py

Laptop IP is already set in `raspberry_pi/sender.py`:
```python
LAPTOP_IP = "10.201.63.146"
```

### Step 3: Start Laptop Listener FIRST

```bash
cd laptop
python3 voice_receiver.py
```
You should see: `[OK] Listening on port 5005...`

### Step 4: Test Each Module Independently (Recommended)

```bash
# On Raspberry Pi — test camera
python3 camera_test.py

# On Raspberry Pi — test IMU
python3 imu_reader.py

# On Raspberry Pi — test detection
python3 object_detector.py

# On Raspberry Pi — test navigation logic
python3 navigation_logic.py

# On Raspberry Pi — test sending
python3 sender.py
```

### Step 5: Run Full System

```bash
# On Raspberry Pi
cd raspberry_pi
python3 main.py
```

---

## Navigation Logic

| Object Position | Instruction              |
|----------------|--------------------------|
| Center (33–66%)| `<object> detected ahead, STOP` |
| Left (0–33%)   | `<object> on left, MOVE RIGHT`  |
| Right (66–100%)| `<object> on right, MOVE LEFT`  |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Camera not found | Check ribbon cable orientation and CSI port latch |
| I2C device not detected | Check wiring, confirm I2C enabled via raspi-config |
| Connection refused on send | Start voice_receiver.py on laptop first |
| YOLO slow on Pi | Ensure 64-bit OS, use `SHOW_PREVIEW = False` in main.py |
| pyttsx3 no sound | Check laptop volume and default audio output device |

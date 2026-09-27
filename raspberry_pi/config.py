"""
config.py - Neuro Vision Assist
Central configuration for all modules.
Edit this file to tune the system without touching module code.
"""

# ─── DEBUG LOGGING ───────────────────────────────────────────────────────────
# NONE    : only critical errors
# BASIC   : step accept/reject, waypoint events, heading corrections
# VERBOSE : full EKF, optical flow, pose, and distance logs
DEBUG_LEVEL = "BASIC"   # "NONE" | "BASIC" | "VERBOSE"

# ─── NETWORK ──────────────────────────────────────────────────────────────────
LAPTOP_IP   = "127.0.0.1"   # Change to your laptop's IP
LAPTOP_PORT = 5005

# ─── CAMERA ───────────────────────────────────────────────────────────────────
FRAME_WIDTH  = 640   # Higher resolution = better detection
FRAME_HEIGHT = 480
SHOW_PREVIEW = True  # Set False on headless Pi to save CPU

# ─── MODEL FILES (SSD MobileNet V3) ──────────────────────────────────────────
import os
_MODEL_DIR       = os.path.join(os.path.dirname(__file__), "..", "Required files", "Python code and lib")
MODEL_WEIGHTS    = os.path.join(_MODEL_DIR, "frozen_inference_graph.pb")
MODEL_CONFIG     = os.path.join(_MODEL_DIR, "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt")
CLASS_NAMES_FILE = os.path.join(_MODEL_DIR, "coco.names")

# ─── DETECTION ────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.30   # Lower = detects more objects
TARGET_CLASSES = {
    # People
    "person",
    # Vehicles
    "bicycle", "car", "motorcycle", "bus", "truck",
    # Outdoor
    "traffic light", "stop sign", "bench",
    # Animals
    "bird", "cat", "dog", "horse", "cow",
    # Indoor obstacles
    "chair", "couch", "dining table", "desk", "bed",
    "door", "window", "toilet", "sink", "refrigerator",
    "tv", "laptop", "keyboard", "microwave", "oven",
    "potted plant", "mirror",
    # Small objects
    "bottle", "cup", "bowl", "vase", "book",
    "cell phone", "remote", "scissors", "clock",
    "backpack", "handbag", "suitcase", "umbrella",
    # Food
    "banana", "apple", "orange", "sandwich",
    "pizza", "cake", "carrot", "broccoli",
}

# ─── NAVIGATION ───────────────────────────────────────────────────────────────
SEND_INTERVAL      = 2.0    # Minimum seconds between voice alerts (different message)
NAV_REPEAT_INTERVAL = 15.0  # Re-speak same message after this many seconds if obstacle persists
PROXIMITY_STOP    = 0.35   # Bounding box height ratio → STOP (very close)
PROXIMITY_SLOW    = 0.15   # Bounding box height ratio → SLOW DOWN (medium)
TILT_ALERT_ANGLE  = 45.0   # Degrees of pitch/roll before tilt warning

# ─── PHONE GPS ────────────────────────────────────────────────────────────────
# GPS is supplied exclusively by the phone browser over HTTPS.
# Retained only so legacy gps_reader imports remain loadable; no navigation
# code initializes or reads a serial GPS device.
GPS_PORT = None
GPS_BAUD = 9600
GPS_RECEIVER_HOST = "0.0.0.0"
GPS_RECEIVER_PORT = 8765
GPS_PHONE_FIX_FILE = "/tmp/neuro_vision_phone_gps.json"
GPS_FIX_STALE_S       = 10.0
GPS_PHONE_TIMESTAMP_TOLERANCE_S = 30.0
GPS_PHONE_MAX_ACCURACY_M = 100.0
GPS_WAYPOINT_RADIUS_M = 15.0
GPS_DESTINATION_RADIUS_M = 12.0
GPS_WAYPOINT_CONFIRMATIONS = 3
GPS_DESTINATION_CONFIRMATIONS = 3
GPS_OFF_ROUTE_RADIUS_M = 25.0
GPS_OFF_ROUTE_CONFIRMATIONS = 3

# ─── TURN-BY-TURN NAVIGATION ──────────────────────────────────────────────────
TURN_ANNOUNCEMENT_DEADBAND_S = 1.0  # Don't announce same thing within 1s
TURN_MIN_SPEED_SAMPLES = 5          # Need N GPS samples before calculating ETA
TURN_THRESHOLDS_M = [400, 200, 100, 50, 25, 10, 5]  # Announcement distances (meters)

# Turn classification thresholds (degrees)
TURN_STRAIGHT_DEG = 15              # ±15°  → "Continue straight"
TURN_SLIGHT_DEG = 45                # ±15-45° → "Bear left/right"
TURN_NORMAL_DEG = 135               # ±45-135° → "Turn left/right"
TURN_UTURN_DEG = 135                # >135° → "U-turn"

# ─── IMU hardware registers ──────────────────────────────────────────────────
MPU_ADDR     = 0x68
PWR_MGMT_1   = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H  = 0x43
ACCEL_SCALE  = 16384.0   # ±2g full-scale
GYRO_SCALE   = 131.0     # ±250 °/s full-scale

# ─── Pedestrian Dead Reckoning (PDR) ─────────────────────────────────────────
# IMU poll rate for navigation monitor
NAV_POLL_S           = 0.02    # 50 Hz

# Gravity (g).  Used to remove static component from accel magnitude.
GRAVITY_G            = 1.0

# Bandpass filter for walking signal (Hz).  Human gait = 1.4–3.0 Hz.
# Samples below LOW_HZ are slow tilts; above HIGH_HZ are vibration/shakes.
STEP_BP_LOW_HZ       = 0.5    # high-pass cut-off
STEP_BP_HIGH_HZ      = 3.5    # low-pass cut-off

# Moving-average window for smoothing the bandpassed signal (samples at 50 Hz).
STEP_FILTER_WINDOW   = 7

# Peak detection: minimum prominence above the local baseline.
# Prominence = peak_value - mean_of_surrounding_valley.
# Walking peaks are typically 0.15–0.50 g above baseline.
STEP_PROMINENCE_G    = 0.12

# Absolute threshold on the smoothed, gravity-removed magnitude.
# Set conservatively low — prominence filter does the real work.
STEP_THRESHOLD_G     = 0.08

# Debounce: minimum seconds between two consecutive steps.
# Human cadence max ~3 steps/s → 0.25 s is safe.
STEP_DEBOUNCE_S      = 0.25

# Cadence validation window: collect this many inter-step intervals
# before deciding the user is walking (not shaking).
CADENCE_WINDOW       = 4      # steps

# Valid walking cadence range (steps per second).
CADENCE_MIN_HZ       = 0.8    # very slow walk
CADENCE_MAX_HZ       = 2.8    # fast walk / slow jog

# Gyroscope magnitude threshold (deg/s) above which the device is
# considered rotating/shaking rather than walking.
GYRO_SHAKE_THRESH    = 80.0

# If no step is detected for this many seconds, user is considered still.
# 1.0 s: fast enough to stop distance accumulation promptly when walking stops,
# but long enough to bridge the gap between steps at slow cadence (0.8 Hz = 1.25 s).
# The motion classifier is the primary stillness signal; this is a fallback.
STILL_TIMEOUT_S      = 1.5

# Waypoint tolerance: advance waypoint this many metres before exact target.
# (Defined in the Distance progress cues section below.)

# Progress cue every N confirmed walking steps (legacy — superseded by distance cues).
PROGRESS_EVERY_STEPS = 10

# ─── Adaptive step length (Weinberg model) ────────────────────────────────────
# L = K * (a_max - a_min)^0.25  on the gravity-removed signal.
STEP_LENGTH_K        = 0.50
STEP_LENGTH_MIN      = 0.35
STEP_LENGTH_MAX      = 0.90

# ─── Motion classifier ──────────────────────────────────────────────────────────
# RMS accel (gravity-removed) thresholds for motion state classification.
MOTION_STILL_RMS     = 0.04   # below this → STILL
MOTION_WALK_RMS_MAX  = 0.80   # above this → RUNNING  (was 0.55 — too low, rejected vigorous walking)
# Gyro RMS threshold for SHAKING / ROTATING classification.
# Lowered from 60.0: camera rotation/shake during normal handling produces
# gyro RMS of 20-50 deg/s.  30 deg/s reliably catches device movement
# while not triggering on normal walking body sway (~5-10 deg/s).
MOTION_GYRO_RMS      = 30.0
# Classification window in samples (50 Hz → 10 samples = 0.2 s).
# Reduced from 25: faster startup means classifier reaches 'walking' sooner,
# reducing the window where only camera contributes to distance.
MOTION_WINDOW        = 10

# ─── Heading / magnetometer ───────────────────────────────────────────────────
MAG_ADDR             = 0x0C
MAG_XOUT_L           = 0x03
MAG_SCALE            = 0.15
HEADING_ALPHA        = 0.98
TURN_THRESHOLD_DEG   = 25.0

# ─── Visual motion (optical flow) ───────────────────────────────────────────────
OF_SCALE             = 0.25    # downscale factor before flow computation
# Minimum mean VERTICAL flow magnitude (px at scaled res) to count as real motion.
# Forward-facing chest-mounted camera: floor features flow DOWNWARD during forward
# walking (radial expansion has a strong vertical component).  0.6 px is reliable
# for walking at ≥0.5 m/s at 30 fps; stationary jitter is typically < 0.3 px.
OF_MOTION_THRESH     = 0.6
# Metres-per-pixel at the scaled resolution.
# Pi Camera v2, 62° FOV, 640px → scaled 0.25x = 160px wide.
# At 1.5 m average corridor distance: 2*tan(31°)/160 ≈ 0.0075 m/px
# Empirically corrected upward to account for radial expansion underestimation.
# Calibrate with OF_CALIBRATION_FACTOR after walking a known distance.
OF_M_PER_PX          = 0.011  # was 0.008 — underestimated distance by ~27%
# Scale correction factor from calibration walk (1.0 = no correction).
# Run calibrate_flow.py, walk exactly 10 m, update this value.
OF_CALIBRATION_FACTOR = 1.0
# Maximum plausible per-frame displacement (m).  Rejects scene cuts / blur.
OF_MAX_DISP_M        = 0.12
# Consecutive still-flow frames before declaring visual stillness (STILL hysteresis).
# At 30 fps: 15 frames = 500 ms.  Prevents brief low-flow moments from gating the EKF.
OF_STILL_FRAMES      = 15
# Consecutive moving-flow frames required before exiting STILL (MOVING hysteresis).
# Prevents a single noisy frame from prematurely releasing the gate.
OF_MOVING_FRAMES     = 4
# Maximum gyro rate (deg/s) at which optical flow is trusted.
# Above this the camera is rotating too fast and flow is unreliable.
OF_GYRO_GATE_DEG_S   = 45.0
# Minimum tracked corners before flow is considered valid.
OF_MIN_CORNERS       = 8

# ─── Extended Kalman Filter (EKF) ───────────────────────────────────────────────
# State: velocity_m_s  (scalar speed along heading direction)
# Process noise: velocity random-walk variance per second ((m/s)²/s)
EKF_Q_VEL            = 0.050   # increased from 0.010 — allows faster velocity changes
# Measurement noise in (m/s)² — expressed directly as speed noise, NOT scaled by 1/dt².
# Camera: optical flow speed error ~12% of 1.2 m/s → std=0.14 m/s → R=0.015
EKF_R_CAMERA         = 0.015   # (m/s)²  — was 0.020 m² (wrong units, wrong scaling)
# IMU step: Weinberg step-length error ~18% → speed std=0.22 m/s → R=0.040
EKF_R_IMU            = 0.040   # (m/s)²  — was 0.060 m² (wrong units, wrong scaling)
# Initial velocity uncertainty
EKF_P0_VEL           = 0.25
# Legacy — kept so old imports do not break
EKF_Q_POS            = 0.001

# ─── Heading guidance ───────────────────────────────────────────────────────────────
# Heading error (degrees) below which the user is considered on-track.
HEADING_ON_TRACK_DEG = 15.0
# Heading error above which a correction cue is spoken.
HEADING_CORRECT_DEG  = 30.0
# Minimum seconds between heading correction announcements.
HEADING_CUE_INTERVAL = 8.0
# Heading hysteresis: once a correction is spoken, error must drop below
# ON_TRACK before another correction of the same type is allowed.
HEADING_HYSTERESIS_DEG = 10.0

# ─── Distance progress cues ──────────────────────────────────────────────────────
# Speak a remaining-distance cue every time remaining drops by this many metres.
PROGRESS_CUE_INTERVAL_M = 1.0
# Speak "approaching waypoint" when this many metres remain.
APPROACHING_M            = 2.5
# Advance waypoint when remaining distance drops to or below this value.
WAYPOINT_TOLERANCE       = 0.60

# ─── Distance Tracker ───────────────────────────────────────────────────────────────────────────────────
# Minimum Euclidean step (metres) that must be exceeded before the pose
# increment is added to travelled_distance.  Rejects sensor jitter while still.
#
# CRITICAL: must be BELOW delta_per_tick at normal walking speed.
# At 50 Hz, 1.2 m/s walking: delta = 1.2 * 0.02 = 0.024 m per tick.
# Threshold of 0.03 m would reject EVERY tick → distance never advances.
# Corrected to 0.008 m (8 mm): rejects jitter (1-3 mm) but accepts walking (24 mm+).
MIN_POSE_DISPLACEMENT = 0.008  # 8 mm  — was 0.03 (too high, rejected all walking)

# ─── Sensor fusion (legacy weight — kept for fallback path) ─────────────────────
FUSION_IMU_WEIGHT     = 0.30   # camera is primary (70%), IMU is secondary (30%)
FUSION_DISAGREE_RATIO = 0.40

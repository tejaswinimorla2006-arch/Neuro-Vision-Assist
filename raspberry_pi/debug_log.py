"""
debug_log.py - Neuro Vision Assist
====================================
Rate-limited, level-aware debug logging.

Levels (set DEBUG_LEVEL in config.py)
--------------------------------------
  NONE    : silent — only critical errors printed elsewhere
  BASIC   : step accept/reject, waypoint events, heading corrections
  VERBOSE : full EKF, optical flow, pose, and distance logs

Rate limiting
-------------
  ekf_summary()   — at most once per EKF_LOG_INTERVAL seconds
  dist_progress() — only when travelled increases by DIST_LOG_STEP metres
  of_state()      — only on MOVING↔STILL transitions or feature-count drops
  heading_cue()   — only when instruction or error changes significantly
  step_ok/rej()   — always printed at BASIC level (low frequency by nature)
"""

import time
from config import DEBUG_LEVEL

# ── Rate-limit intervals ───────────────────────────────────────────────────────
EKF_LOG_INTERVAL  = 0.75   # seconds between EKF summary prints
DIST_LOG_STEP     = 0.5    # metres between distance progress prints
OF_LOW_FEAT_THRESH = 20    # feature count below which a drop warning is printed
HDG_CHANGE_DEG    = 5.0    # minimum heading-error change to re-print heading log

_NONE    = "NONE"
_BASIC   = "BASIC"
_VERBOSE = "VERBOSE"

_level = DEBUG_LEVEL.upper() if DEBUG_LEVEL else _BASIC


def _is(level: str) -> bool:
    if _level == _NONE:
        return False
    if _level == _BASIC:
        return level == _BASIC
    return True   # VERBOSE: print everything


# ── Module-level rate-limit state ─────────────────────────────────────────────
_ekf_last_t:       float = 0.0
_dist_last_logged: float = 0.0
_of_last_state:    str   = ""
_of_last_feat:     int   = 9999
_hdg_last_err:     float = 0.0
_hdg_last_cue:     str   = ""


# ── EKF summary (VERBOSE, rate-limited) ───────────────────────────────────────

def ekf_pred(v_before: float, v_after: float, P: float, dt: float) -> None:
    if not _is(_VERBOSE):
        return
    global _ekf_last_t
    now = time.monotonic()
    if now - _ekf_last_t < EKF_LOG_INTERVAL:
        return
    _ekf_last_t = now
    print(f"[EKF-PRED]  v_before={v_before:.4f}  v_after={v_after:.4f}"
          f"  P={P:.4f}  dt={dt:.4f}s")


def ekf_update(source: str, z: float, K: float, v_before: float,
               v_after: float, P: float) -> None:
    if not _is(_VERBOSE):
        return
    # Share the same rate-limit bucket as ekf_pred
    global _ekf_last_t
    now = time.monotonic()
    if now - _ekf_last_t < EKF_LOG_INTERVAL:
        return
    _ekf_last_t = now
    print(f"[EKF-{source}]  z_speed={z:.4f}  K={K:.4f}"
          f"  v_before={v_before:.4f}  v_after={v_after:.4f}  P={P:.6f}")


def ekf_pose(delta_m: float, heading: float, dx: float, dy: float,
             pose: tuple) -> None:
    if not _is(_VERBOSE):
        return
    global _ekf_last_t
    now = time.monotonic()
    if now - _ekf_last_t < EKF_LOG_INTERVAL:
        return
    _ekf_last_t = now
    print(f"[EKF-POSE]  delta={delta_m:.4f}m  heading={heading:.1f}°"
          f"  dx={dx:.4f}  dy={dy:.4f}"
          f"  pose=({pose[0]:.3f},{pose[1]:.3f},{pose[2]:.3f})")


# ── Distance progress (VERBOSE, threshold-gated) ──────────────────────────────

def dist_progress(cx: float, cy: float, cz: float,
                  increment: float, travelled: float) -> None:
    if not _is(_VERBOSE):
        return
    global _dist_last_logged
    if travelled - _dist_last_logged < DIST_LOG_STEP:
        return
    _dist_last_logged = travelled
    print(f"[DIST] Pose=({cx:.3f}, {cy:.3f}, {cz:.3f})  "
          f"Increment={increment:.3f}m  Travelled={travelled:.3f}m")


def dist_reset() -> None:
    global _dist_last_logged
    _dist_last_logged = 0.0


# ── Optical flow (VERBOSE, state-change / feature-drop gated) ─────────────────

def of_state_change(new_state: str, pts_good: int, pts_total: int,
                    mean_px: float, corrected_px: float,
                    disp_m: float, accum_m: float, gz: float) -> None:
    """Print only when MOVING↔STILL state changes."""
    if not _is(_VERBOSE):
        return
    global _of_last_state
    if new_state == _of_last_state:
        return
    _of_last_state = new_state
    if new_state == "STILL":
        print(f"[OF]  → STILL  pts={pts_good}/{pts_total}"
              f"  mean={mean_px:.2f}px  corrected={corrected_px:.2f}px"
              f"  gz={gz:.1f}°/s")
    else:
        print(f"[OF]  → MOVING  pts={pts_good}/{pts_total}"
              f"  mean={mean_px:.2f}px  corrected={corrected_px:.2f}px"
              f"  disp={disp_m:.4f}m  accum={accum_m:.4f}m  gz={gz:.1f}°/s")


def of_low_features(n_good: int, n_total: int, label: str = "") -> None:
    """Print when feature count drops below threshold."""
    if not _is(_VERBOSE):
        return
    global _of_last_feat
    if n_good < OF_LOW_FEAT_THRESH and _of_last_feat >= OF_LOW_FEAT_THRESH:
        print(f"[OF]  LOW-FEAT  good={n_good}/{n_total}  {label}")
    _of_last_feat = n_good


def of_init(label: str, n: int = 0) -> None:
    """Print init/redetect/failure events unconditionally at VERBOSE."""
    if not _is(_VERBOSE):
        return
    print(f"[OF]  {label}  n={n}")


def of_reset() -> None:
    global _of_last_state, _of_last_feat
    _of_last_state = ""
    _of_last_feat  = 9999


# ── Camera motion gate (BASIC, state-change only) ─────────────────────────────────

_gate_last_msg: str = ""


def of_gate(msg: str, v_before: float, v_after: float) -> None:
    """Print only when the gate decision changes."""
    if not _is(_BASIC):
        return
    global _gate_last_msg
    if msg == _gate_last_msg:
        return
    _gate_last_msg = msg
    print(f"[OF-GATE]  {msg}  v_before={v_before:.3f}  v_after={v_after:.3f}")


# ── Heading guidance (BASIC, change-gated) ────────────────────────────────────

def heading_log(expected: float, actual: float, err: float, cue: str) -> None:
    """Print only when the cue text or heading error changes significantly."""
    if not _is(_BASIC):
        return
    global _hdg_last_err, _hdg_last_cue
    if cue == _hdg_last_cue and abs(err - _hdg_last_err) < HDG_CHANGE_DEG:
        return
    _hdg_last_err = err
    _hdg_last_cue = cue
    print(f"[HDG] Expected={expected:.0f}° Actual={actual:.1f}°"
          f" Error={err:+.1f}° → {cue}")


def heading_reset() -> None:
    global _hdg_last_err, _hdg_last_cue
    _hdg_last_err = 0.0
    _hdg_last_cue = ""


# ── Step detection (BASIC, always printed — low frequency) ────────────────────

def step_ok(count: int, peak: float, prominence: float, length: float,
            total: float, cadence: float, motion: str, gyro: float) -> None:
    if not _is(_BASIC):
        return
    print(f"[STEP-OK]  #{count}  peak={peak:.4f}g"
          f"  prominence={prominence:.4f}g  L={length:.3f}m"
          f"  total={total:.3f}m  cadence={cadence:.2f}Hz"
          f"  motion={motion}  gyro={gyro:.1f}°/s")


def step_rej(peak: float, reason: str, detail: str = "") -> None:
    if not _is(_BASIC):
        return
    print(f"[STEP-REJ]  peak={peak:.4f}g  {detail}  REASON={reason}")


# ── Navigation events (BASIC) ─────────────────────────────────────────────────

def nav_event(msg: str) -> None:
    if not _is(_BASIC):
        return
    print(f"[NAV] {msg}")


def pose_log(x: float, y: float, z: float,
             increment: float, travelled: float, remaining: float) -> None:
    """Structured diagnostic block — VERBOSE only, rate-limited."""
    if not _is(_VERBOSE):
        return
    global _ekf_last_t
    now = time.monotonic()
    if now - _ekf_last_t < EKF_LOG_INTERVAL:
        return
    _ekf_last_t = now
    print(
        f"[POSE]     x={x:.3f}  y={y:.3f}  z={z:.3f}\n"
        f"[DIST]     increment={increment:.3f}m  "
        f"travelled={travelled:.3f}m  remaining={remaining:.3f}m"
    )


def edge_log(label: str, target: float) -> None:
    if not _is(_VERBOSE):
        return
    print(f"[EDGE]  {label}  target={target:.2f}m")

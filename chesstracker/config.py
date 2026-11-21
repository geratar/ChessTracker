"""Settings: defaults merged with an optional config.json in the project root."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "camera_index": 0,
    "camera_backend": "auto",      # auto | avfoundation | dshow | msmf | v4l2 | any
    "frame_width": 1280,
    "frame_height": 720,
    "max_cameras_to_scan": 5,
    "reconnect_interval_s": 2.0,
    "warp_size_px": 640,            # size of the top-down board image
    "calibration_path": "data/calibration.json",
    "recordings_dir": "data/recordings",
}


def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULTS)
    path = Path(path)
    if path.exists():
        try:
            user = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise SystemExit(f"config.json is not valid JSON: {e}")
        from .tracker import TRACKER_DEFAULTS
        unknown = set(user) - set(DEFAULTS) - set(TRACKER_DEFAULTS)
        if unknown:
            print(f"Warning: unknown settings in config.json ignored: {sorted(unknown)}")
        cfg.update(user)
    return cfg


def resolve(rel_path):
    """Paths in config are relative to the project root."""
    p = Path(rel_path)
    return p if p.is_absolute() else ROOT / p

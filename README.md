# Chess Tracker

Tracks a physical chess game through a webcam and mirrors it on a digital board.
Current stage: **Phase 1, camera and calibration.**

## Install (once)

1. Install Python 3.10 or newer from https://www.python.org/downloads/
   (Windows: tick "Add python.exe to PATH" in the installer.)
2. Open a terminal in this folder (macOS: Terminal; Windows: PowerShell) and run:

   macOS:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   Windows:
   ```
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. macOS only: the first run asks for camera access. If it doesn't, enable your
   terminal app in System Settings > Privacy & Security > Camera, then restart the terminal.

## Run

Activate the environment first in every new terminal (`source .venv/bin/activate`
on macOS, `.venv\Scripts\activate` on Windows).

```
python calibrate.py --list        # which cameras exist
python calibrate.py               # camera 0 (or camera_index from config.json)
python calibrate.py --camera 1    # a specific camera
python calibrate.py --source data/recordings/rec_xxx.mp4   # replay a recording
python -m pytest                  # run the tests
```

## Calibrate

1. Click the 4 corners of the **playing area** (the outer corners of the 64 squares,
   not the wooden frame). Any order. Drag a red circle to fine-tune it.
2. The "Board (top-down)" window shows the straightened board. Press **R** until the
   label `a1` sits on White's left-hand corner square (a dark square).
   The bottom text warns when a1 looks light.
3. Press **S** to save. Next start loads it automatically.

Keys: R rotate, U or right-click undo, C clear, S save, L load, G snapshot (PNG),
V start/stop video recording, N/P next/previous camera, Q quit.
Snapshots and recordings go to `data/recordings/` and can be replayed with `--source`.

## Settings

Create `config.json` to override any default in `chesstracker/config.py`, e.g.
```json
{"camera_index": 1, "frame_width": 1920, "frame_height": 1080}
```

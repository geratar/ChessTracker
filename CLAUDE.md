# Chess Tracker: working notes

## Goal
Webcam tracks a physical wooden chess game; moves appear on a digital board within 2-3 s.
User is a beginner programmer. Develops on Windows; camera runs on a macOS laptop.
Code must stay cross-platform.

## Stack
Python, OpenCV, numpy, python-chess, pytest. Stockfish later (Phase 5).
No neural nets, paid APIs, databases or frameworks unless simpler methods demonstrably fail.

## Architecture
- `chesstracker/config.py`: defaults + optional root `config.json` (all thresholds go here)
- `chesstracker/camera.py`: `FrameSource` (camera index, video file or image; auto-reconnect; video loops)
- `chesstracker/calibration.py`: 4 corners -> homography -> top-down image, square geometry, JSON save/load
- `chesstracker/overlay.py`: debug drawing
- `calibrate.py`: Phase 1 OpenCV-window app
- `tests/`: pytest, synthetic frames (no camera needed)

## Conventions
- Warped board: white at bottom, a1 bottom-left. `rotation` (0-3 quarter turns) picks a1's physical corner.
- Clicked corners are reordered clockwise automatically; click order doesn't matter.
- Previous confirmed python-chess position is the source of truth; never apply an uncertain move.
- Prefer pausing/asking over guessing. Thresholds and stability windows are config, not constants.
- Recordings in `data/recordings/` are the basis for repeatable detection tests.
- One phase at a time; don't start a phase until the previous one is validated with the real camera.

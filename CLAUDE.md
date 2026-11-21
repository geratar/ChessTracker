# Chess Tracker: working notes

## Goal
Webcam tracks a physical wooden chess game; moves appear on a digital board within 2-3 s.
User is a beginner programmer. Camera runs on a macOS laptop (also used a Windows PC). User does not want
to install dev tools; Claude develops in the GitHub repo geratar/ChessTracker and tests on uploaded recordings.
Code must stay cross-platform.

## Stack
Python, OpenCV, numpy, python-chess, pytest. Stockfish later (Phase 5).
No neural nets, paid APIs, databases or frameworks unless simpler methods demonstrably fail.

## Architecture
- `chesstracker/config.py`: defaults + optional root `config.json` (all thresholds go here)
- `chesstracker/camera.py`: `FrameSource` (camera index, video file or image; auto-reconnect; video loops)
- `chesstracker/calibration.py`: 4 corners -> homography -> top-down image, square geometry, JSON save/load
- `chesstracker/overlay.py`: debug drawing
- `chesstracker/moves.py`: legal-move matching from a set of changed squares (accept / ambiguous / no_move / promotion)
- `chesstracker/detector.py`: frame alignment (phase correlation), motion gate, per-square change scores (L + edges)
- `chesstracker/tracker.py`: state machine: still -> consistent changes -> match_move -> apply / ask / report; undo
- `chesstracker/board_view.py`: 2D board drawing
- `calibrate.py`: Phase 1 app; `track.py`: Phase 2 live app; `replay.py`: run tracker on a video
- `tests/fixtures/game1`: real frames from the user's board (e4 d5 exd5 c6 + hands) for regression tests
- `tests/`: pytest, synthetic frames (no camera needed)

## Conventions
- Warped board: white at bottom, a1 bottom-left. `rotation` (0-3 quarter turns) picks a1's physical corner.
- Clicked corners are reordered clockwise automatically; click order doesn't matter.
- Previous confirmed python-chess position is the source of truth; never apply an uncertain move.
- Prefer pausing/asking over guessing. Thresholds and stability windows are config, not constants.
- Recordings in `data/recordings/` are the basis for repeatable detection tests.
- One phase at a time; don't start a phase until the previous one is validated with the real camera.

# Chess Tracker

Tracks a physical chess game through a webcam and mirrors it on a digital board.

## Start (Mac)

1. Install Python once from https://www.python.org/downloads/ (the macOS installer).
2. Double-click **ChessTracker.command**. The first start sets things up (about a minute).
   If macOS blocks it: right-click > Open > Open. Allow camera access when asked.
3. The app opens in your browser. Keep the small black window open; closing it quits the app.

Windows: double-click **ChessTracker.bat** instead.

## Using the app

- **Setup**: 1) pick the camera, 2) click the 4 corners of the 64 squares and press
  "Rotate a1" until a1 is White's bottom-left square, 3) set up the pieces, hands off, Start tracking.
- **Play**: moves appear about 1 second after your hand leaves the board.
  - If it asks "Which move?" or "Missed a move?", click the right option.
  - **Fix last move**: the last move was detected wrong: click the from-square and to-square
    of the real move on the digital board.
  - **Enter a move**: the camera missed a move: click it on the board.
  - **Undo** takes back the last move (put the pieces back too). **Flip board** puts Black at the bottom.
  - **Finish game**: choose who won, then "Finish & save" or "Save & analyze" (opens it in the Library).
  - The game is saved to the Library (name, result, date) through Finish game; **New game** appears after that.
    If you leave the game or start a new one with unsaved moves, the app asks whether to save first.
- **Library**: open a saved game, step through it with the arrows (or keyboard left/right), Auto-play, copy the PGN.
  **Analyze with Stockfish** evaluates every position: evaluation bar, evaluation graph (click to jump),
  ?! / ? / ?? marks on inaccuracies, mistakes and blunders, and an arrow for the best move.
  The first time, Stockfish (free, GPL-3) is downloaded automatically from its official GitHub releases
  into `data/engine/`; nothing to install.
- **Settings**: board style (brown, blue, green) and orientation.

Tips: mount the camera high and steady, ideally not on the same table as the board, let the
board fill most of the picture, and avoid direct sunlight on the board.

Piece images: "cburnett" set by Colin M.L. Burnett, CC BY-SA 3.0 (bundled with python-chess).

## For developers

### Manual install

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

### Command-line tools

Activate the environment first in every new terminal (`source .venv/bin/activate`
on macOS, `.venv\Scripts\activate` on Windows).

```
python calibrate.py --list        # which cameras exist
python calibrate.py               # camera 0 (or camera_index from config.json)
python calibrate.py --camera 1    # a specific camera
python calibrate.py --source data/recordings/rec_xxx.mp4   # replay a recording
python -m pytest                  # run the tests
```

### calibrate.py

1. Click the 4 corners of the **playing area** (the outer corners of the 64 squares,
   not the wooden frame). Any order. Drag a red circle to fine-tune it.
2. The "Board (top-down)" window shows the straightened board. Press **R** until the
   label `a1` sits on White's left-hand corner square (a dark square).
   The bottom text warns when a1 looks light.
3. Press **S** to save. Next start loads it automatically.

Keys: R rotate, U or right-click undo, C clear, S save, L load, G snapshot (PNG),
V start/stop video recording, N/P next/previous camera, Q quit.
Snapshots and recordings go to `data/recordings/` and can be replayed with `--source`.

### track.py (OpenCV window version)

1. Calibrate first (above). Set up the starting position.
2. Run `python track.py`.
3. Keep hands off the board until it says "Ready". Then play normally: a move is
   registered about 1 second after your hand leaves the board.
4. If it asks "Which move?", press 1, 2 or 3, or X if nothing happened.

Keys: U undo (put the pieces back too), N new game, S save PGN to `data/games/`,
V record video, Q quit.

Test detection on a recording without a camera:
```
python replay.py data/recordings/rec_xxx.mp4
python track.py --source data/recordings/rec_xxx.mp4
```

Tips: mount the camera high and steady, away from the table the board is on, so
pieces don't hide each other and touching the board doesn't shake the picture.

### Settings

Create `config.json` to override any default in `chesstracker/config.py`, e.g.
```json
{"camera_index": 1, "frame_width": 1920, "frame_height": 1080, "stable_seconds": 0.8}
```
Tracking thresholds (`motion_threshold`, `stable_seconds`, `confirm_seconds`,
`max_changed_squares`, ...) are listed in `chesstracker/tracker.py` and can be set here too.

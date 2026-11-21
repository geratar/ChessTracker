"""The user's blitz clip (one person, a move every ~1.5 s, camera from the side and above).
Between moves the board is clear for only ~0.3 s; every move must still be read, and
never a wrong one."""
from pathlib import Path

import chess
import cv2

from chesstracker.calibration import Calibration
from chesstracker.tracker import Tracker

FIX = Path(__file__).parent / "fixtures" / "blitz"
MOVES = "1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 c6 5. Bd2"


def test_blitz_game_is_followed():
    tr = Tracker(Calibration.load(FIX / "calibration.json"))
    cap = cv2.VideoCapture(str(FIX / "clip.mp4"))
    events, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        events += tr.process(frame, i / 15)
        i += 1
    assert not tr.waiting_for_user, [e.text for e in events]
    assert chess.Board().variation_san(tr.board.move_stack) == MOVES

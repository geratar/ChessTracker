"""The user's normal-paced game (recording 6). Every move must be followed; at most one
question, and its first suggestion must be the right one."""
from pathlib import Path

import chess
import cv2

from chesstracker.calibration import Calibration
from chesstracker.tracker import Tracker

FIX = Path(__file__).parent / "fixtures" / "normal_pace"
MOVES = "1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 c6 5. Bd2 Qc7"


def test_normal_pace_game_is_followed():
    tr = Tracker(Calibration.load(FIX / "calibration.json"))
    cap = cv2.VideoCapture(str(FIX / "clip.mp4"))
    i, asks = 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        tr.process(frame, i / 15)
        if tr.pending is not None:
            asks += 1
            tr.confirm(tr.pending.candidates[0])     # the player taps the first suggestion
        i += 1
    assert chess.Board().variation_san(tr.board.move_stack) == MOVES
    assert asks <= 1

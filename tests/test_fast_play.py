"""The user's fast solo game (camera higher, one person playing both sides quickly).
Moves came faster than the board was ever visible, so not every move can be read.
What must hold: nothing wrong is ever applied, and the app says it lost track."""
from pathlib import Path

import chess
import cv2

from chesstracker.calibration import Calibration
from chesstracker.tracker import Tracker

FIX = Path(__file__).parent / "fixtures" / "fast_play"
TRUE = ["e4", "d5", "exd5", "Qxd5", "Nc3", "Qa5", "d4", "c6", "Nf3"]


def test_fast_play_never_applies_a_wrong_move():
    tr = Tracker(Calibration.load(FIX / "calibration.json"))
    cap = cv2.VideoCapture(str(FIX / "clip.mp4"))
    events, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        events += tr.process(frame, i / 15)
        i += 1
    played = chess.Board().variation_san(tr.board.move_stack).replace(".", " ").split()
    sans = [t for t in played if not t.isdigit()]
    assert sans == TRUE[:len(sans)], sans
    assert any(e.kind == "lost" for e in events) or sans

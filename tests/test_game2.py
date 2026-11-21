"""Regression test on the user's second (Mac) setup: camera at the side, pieces
lean onto the neighbouring file. Every move must be found without asking.
The hand frames here look "still" to the motion gate, so this also checks that
frame averaging never blends a hand into the picture used to decide."""
from pathlib import Path

import cv2

from chesstracker.calibration import Calibration
from chesstracker.tracker import Tracker

FIX = Path(__file__).parent / "fixtures" / "game2"
FPS = 15
MOVES = ["e4", "e5", "Nf3", "d5", "exd5", "Qxd5", "d4", "exd4"]


def img(name):
    f = cv2.imread(str(FIX / f"{name}.jpg"))
    assert f is not None, name
    return f


def test_game2_all_moves_without_questions():
    tr = Tracker(Calibration.load(FIX / "calibration.json"))
    t = 0.0
    events = []

    def feed(frame, seconds):
        nonlocal t
        for _ in range(int(seconds * FPS)):
            events.extend(tr.process(frame, t))
            t += 1 / FPS

    def hand(a, b, seconds=1.0):
        nonlocal t
        for i in range(int(seconds * FPS)):
            events.extend(tr.process(a if i % 2 else b, t))
            t += 1 / FPS

    feed(img("start"), 1.5)
    for k, san in enumerate(MOVES):
        hand(img(f"{k:02d}_hand_a"), img(f"{k:02d}_hand_b"))
        feed(img(f"{k:02d}_still"), 2.0)
    asks = [(e.kind, e.text) for e in events if e.kind not in ("move", "ready")]
    assert [e.text for e in events if e.kind == "move"] == MOVES, asks
    assert asks == []

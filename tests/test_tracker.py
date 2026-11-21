"""Tracker tests on real frames from the user's board (tests/fixtures/game1).

Still positions are repeated for ~1.5 s of simulated time; hand frames alternate
to create motion, like a real hand moving over the board.
"""
from pathlib import Path

import chess
import cv2
import numpy as np
import pytest

from chesstracker.calibration import Calibration
from chesstracker.tracker import Tracker

FIX = Path(__file__).parent / "fixtures" / "game1"
FPS = 15


def img(name):
    f = cv2.imread(str(FIX / f"{name}.jpg"))
    assert f is not None, name
    return f


class Clock:
    def __init__(self):
        self.t = 0.0

    def feed(self, tracker, frame, seconds):
        events = []
        for _ in range(int(seconds * FPS)):
            events += tracker.process(frame, self.t)
            self.t += 1 / FPS
        return events

    def hand(self, tracker, a, b, seconds=1.0):
        events = []
        for i in range(int(seconds * FPS)):
            events += tracker.process(a if i % 2 else b, self.t)
            self.t += 1 / FPS
        return events


@pytest.fixture
def tracker():
    return Tracker(Calibration.load(FIX / "calibration.json"))


def kinds(events):
    return [e.kind for e in events]


def test_real_game_sequence(tracker):
    c = Clock()
    ev = c.feed(tracker, img("00_start"), 1.5)
    assert kinds(ev) == ["ready"]
    seq = [("01", "02_after_e4", "e4"), ("03", "04_after_d5", "d5"),
           ("05", "06_after_exd5", "exd5"), (None, "07_after_c6", "c6")]
    for hand, still, san in seq:
        ev = []
        if hand:
            ev += c.hand(tracker, img(f"{hand}_hand_a"), img(f"{hand}_hand_b"))
        else:
            ev += c.hand(tracker, img("05_hand_a"), img("05_hand_b"))
        ev += c.feed(tracker, img(still), 2.0)
        moves = [e.text for e in ev if e.kind == "move"]
        assert moves == [san], (still, [(e.kind, e.text) for e in ev])
    assert tracker.board.fen().startswith("rnbqkbnr/pp2pppp/2p5/3P4/8/8/PPPP1PPP/RNBQKBNR w")


def test_detection_latency_under_2s(tracker):
    c = Clock()
    c.feed(tracker, img("00_start"), 1.5)
    c.hand(tracker, img("01_hand_a"), img("01_hand_b"))
    t_done = c.t
    for _ in range(int(3 * FPS)):
        ev = tracker.process(img("02_after_e4"), c.t)
        if any(e.kind == "move" for e in ev):
            break
        c.t += 1 / FPS
    assert c.t - t_done < 2.0


def test_hand_without_move_changes_nothing(tracker):
    c = Clock()
    c.feed(tracker, img("00_start"), 1.5)
    ev = c.hand(tracker, img("01_hand_a"), img("01_hand_b"), 2.0)
    ev += c.feed(tracker, img("00_start"), 2.0)
    assert "move" not in kinds(ev)
    assert tracker.board.fen() == chess.Board().fen()


def test_hand_resting_still_is_not_a_move(tracker):
    c = Clock()
    c.feed(tracker, img("00_start"), 1.5)
    ev = c.feed(tracker, img("01_hand_a"), 3.0)   # hand frozen over the board
    assert "move" not in kinds(ev)


def test_no_duplicate_moves(tracker):
    c = Clock()
    c.feed(tracker, img("00_start"), 1.5)
    c.hand(tracker, img("01_hand_a"), img("01_hand_b"))
    ev = c.feed(tracker, img("02_after_e4"), 5.0)
    ev += c.hand(tracker, img("01_hand_a"), img("01_hand_b"))   # hand passes, nothing moved
    ev += c.feed(tracker, img("02_after_e4"), 3.0)
    assert [e.text for e in ev if e.kind == "move"] == ["e4"]


def test_lighting_change_is_not_a_move(tracker):
    c = Clock()
    start = img("00_start")
    c.feed(tracker, start, 1.5)
    brighter = cv2.convertScaleAbs(start, alpha=1.08, beta=4)
    ev = c.feed(tracker, brighter, 3.0)
    assert "move" not in kinds(ev)


def test_small_board_shift_is_not_a_move(tracker):
    c = Clock()
    start = img("00_start")
    c.feed(tracker, start, 1.5)
    shifted = cv2.warpAffine(start, np.float32([[1, 0, -1.5], [0, 1, 4]]), start.shape[1::-1],
                             borderMode=cv2.BORDER_REPLICATE)
    c.hand(tracker, img("01_hand_a"), img("01_hand_b"))
    ev = c.feed(tracker, shifted, 3.0)
    assert "move" not in kinds(ev), [(e.kind, e.text) for e in ev]


def test_confirm_and_reject():
    t = Tracker(Calibration.load(FIX / "calibration.json"))
    c = Clock()
    c.feed(t, img("00_start"), 1.5)
    with pytest.raises(ValueError):
        t.confirm(chess.Move.from_uci("e2e5"))
    ev = t.confirm(chess.Move.from_uci("g1f3"))
    assert ev.kind == "move" and ev.text == "Nf3"
    t.reject()
    assert not t.waiting_for_user


def test_undo_restores_reference(tracker):
    c = Clock()
    c.feed(tracker, img("00_start"), 1.5)
    c.hand(tracker, img("01_hand_a"), img("01_hand_b"))
    c.feed(tracker, img("02_after_e4"), 2.0)
    assert tracker.undo() == chess.Move.from_uci("e2e4")
    # pieces put back: no move should be detected, then replaying e4 is detected again
    ev = c.hand(tracker, img("01_hand_a"), img("01_hand_b"))
    ev += c.feed(tracker, img("00_start"), 2.0)
    assert "move" not in kinds(ev)
    c.hand(tracker, img("01_hand_a"), img("01_hand_b"))
    ev = c.feed(tracker, img("02_after_e4"), 2.0)
    assert [e.text for e in ev if e.kind == "move"] == ["e4"]

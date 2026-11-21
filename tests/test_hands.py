"""Hands over part of the board: moves elsewhere are still read, quickly and safely."""
import chess
import cv2
import numpy as np

from chesstracker.calibration import Calibration
from test_tracker import FIX, FPS, Clock, img
from chesstracker.tracker import Tracker


def cal():
    return Calibration.load(FIX / "calibration.json")


def with_hand(frame, c, squares, k):
    """Paint a moving 'hand' (changing texture) over the given squares in the camera image."""
    f = frame.copy()
    inv = c.inverse_homography()
    s = c.square_px
    rng = np.random.default_rng(k)
    for name in squares:
        x0, y0, x1, y1 = c.square_rect(name)
        poly = cv2.perspectiveTransform(np.float32([[[x0, y0]], [[x1, y0]], [[x1, y1]], [[x0, y1]]]), inv)
        cv2.fillPoly(f, [poly.astype(np.int32).reshape(-1, 2)], tuple(int(v) for v in rng.integers(40, 200, 3)))
    return f


def feed_hand(tr, clock, frame, squares, seconds):
    c, ev = tr.aligner.cal, []
    for k in range(int(seconds * FPS)):
        ev += tr.process(with_hand(frame, c, squares, k), clock.t)
        clock.t += 1 / FPS
    return ev


def moves(ev):
    return [e.text for e in ev if e.kind == "move"]


def test_move_is_read_while_other_hand_hovers_far_away():
    tr, c = Tracker(cal()), Clock()
    c.feed(tr, img("00_start"), 1.0)
    c.hand(tr, img("01_hand_a"), img("01_hand_b"))
    # White has played e4; Black's hand is already over the a/b files on Black's side.
    ev = feed_hand(tr, c, img("02_after_e4"), ["a7", "b7", "a6", "b6"], 1.5)
    assert moves(ev) == ["e4"]
    assert not [e for e in ev if e.kind not in ("move",)]       # no questions while hands are around
    # Hand leaves: nothing changed there, so no phantom move or warning.
    ev = c.feed(tr, img("02_after_e4"), 2.0)
    assert ev == [] and len(tr.board.move_stack) == 1


def test_hand_next_to_the_move_waits_instead_of_guessing():
    tr, c = Tracker(cal()), Clock()
    c.feed(tr, img("00_start"), 1.0)
    c.hand(tr, img("01_hand_a"), img("01_hand_b"))
    # A hand over e3: e2-e3 can't be ruled out yet, so nothing is decided.
    ev = feed_hand(tr, c, img("02_after_e4"), ["e3"], 1.5)
    assert moves(ev) == [] and tr.pending is None
    ev = c.feed(tr, img("02_after_e4"), 1.5)
    assert moves(ev) == ["e4"]


def test_faster_than_before():
    """From the hand leaving to the move on screen: under 1 second."""
    tr, c = Tracker(cal()), Clock()
    c.feed(tr, img("00_start"), 1.0)
    c.hand(tr, img("01_hand_a"), img("01_hand_b"))
    t0 = c.t
    ev = c.feed(tr, img("02_after_e4"), 2.0)
    assert moves(ev) == ["e4"] and ev[-1].t - t0 < 1.0

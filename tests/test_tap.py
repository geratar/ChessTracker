"""'Move done' taps (Space / button, like a chess clock)."""
from test_tracker import FIX, FPS, Clock, img
from chesstracker.calibration import Calibration
from chesstracker.tracker import Tracker


def make(detect):
    return Tracker(Calibration.load(FIX / "calibration.json"), {"detect": detect})


def moves(ev):
    return [e.text for e in ev if e.kind == "move"]


def test_tap_mode_waits_for_the_tap_then_reads_at_once():
    tr, c = make("tap"), Clock()
    c.feed(tr, img("00_start"), 1.0)
    c.hand(tr, img("01_hand_a"), img("01_hand_b"))
    assert moves(c.feed(tr, img("02_after_e4"), 2.0)) == []      # no tap: nothing
    tr.tap(c.t)
    t0 = c.t
    ev = c.feed(tr, img("02_after_e4"), 0.5)
    assert moves(ev) == ["e4"] and ev[-1].t - t0 < 0.3


def test_tap_right_after_moving_reads_without_the_usual_wait():
    tr, c = make("tap"), Clock()
    c.feed(tr, img("00_start"), 1.0)
    seq = [("01", "02_after_e4", "e4"), ("03", "04_after_d5", "d5"), ("05", "06_after_exd5", "exd5")]
    for hand, still, san in seq:
        c.hand(tr, img(f"{hand}_hand_a"), img(f"{hand}_hand_b"), 0.6)
        tr.tap(c.t)                                   # tap the moment the hand leaves
        ev = c.feed(tr, img(still), 0.4)
        assert moves(ev) == [san]


def test_tap_in_automatic_mode_reads_immediately():
    tr, c = make("auto"), Clock()
    c.feed(tr, img("00_start"), 1.0)
    c.hand(tr, img("01_hand_a"), img("01_hand_b"))
    tr.tap(c.t)
    ev = c.feed(tr, img("02_after_e4"), 0.3)
    assert moves(ev) == ["e4"]


def test_tap_without_a_move_says_so():
    tr, c = make("tap"), Clock()
    c.feed(tr, img("00_start"), 1.0)
    tr.tap(c.t)
    ev = c.feed(tr, img("00_start"), 0.5)
    assert [e.kind for e in ev] == ["unrecognized"] and not tr.board.move_stack

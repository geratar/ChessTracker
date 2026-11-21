"""Move tracker: turns a stream of frames into confirmed chess moves.

The python-chess Board is the source of truth. A move is only applied when the
board has been still for a while, the observed square changes are consistent,
and exactly one legal move explains them. Otherwise the tracker reports and
waits (or asks for confirmation); it never guesses.
"""
from dataclasses import dataclass, field

import chess

from .detector import Aligner, MotionGate, change_scores, changed_squares, square_features
from .moves import ACCEPT, AMBIGUOUS, NO_MOVE, PROMOTION, match_move

TRACKER_DEFAULTS = {
    "motion_threshold": 4.0,       # mean abs diff on a 160x90 frame; ~3 when still, >6 with hands
    "stable_seconds": 0.6,         # how long the scene must be still before we look
    "confirm_seconds": 0.5,        # the same changed squares must persist this long after that
    "max_changed_squares": 8,      # more than this => hand, shadow or bumped board: wait
    "absorb_seconds": 3.0,         # unchanged board for this long => refresh reference (lighting drift)
    "min_change_score": 25.0,
    "median_factor": 3.0,
    "rel_to_max": 0.4,
}


@dataclass
class Event:
    kind: str          # move | ambiguous | promotion | unrecognized | obstructed | ready
    t: float
    text: str
    move: chess.Move = None
    candidates: list = field(default_factory=list)
    squares: set = field(default_factory=set)


class Tracker:
    def __init__(self, cal, settings=None, board=None):
        s = dict(TRACKER_DEFAULTS)
        s.update({k: v for k, v in (settings or {}).items() if k in TRACKER_DEFAULTS})
        self.s = s
        self.board = board if board is not None else chess.Board()
        self.aligner = Aligner(cal)
        self.gate = MotionGate(s["motion_threshold"], s["stable_seconds"])
        self.ref_feats = None          # board image of the last confirmed position
        self.ref_history = []          # earlier reference images, for undo
        self.pending = None            # MatchResult waiting for the user
        self.last_changed = None
        self.changed_since = None
        self.evaluated = False         # one decision per still period
        self.reported = None
        self.unchanged_since = None
        self.last_feats = None
        self.last_scores = None

    # --- public ------------------------------------------------------------
    @property
    def waiting_for_user(self):
        return self.pending is not None

    def process(self, frame, t):
        """Feed one frame (BGR) captured at time t (seconds). Returns a list of Events."""
        events = []
        stable = self.gate.update(frame, t)
        if not stable:
            self.last_changed, self.changed_since, self.evaluated = None, None, False
            self.unchanged_since = None
            return events

        self.aligner.update(frame)
        feats = square_features(self.aligner.calibration().warp(frame))
        self.last_feats = feats
        if self.ref_feats is None:
            self.ref_feats = feats
            events.append(Event("ready", t, "Reference position captured"))
            return events
        if self.pending is not None:
            return events

        scores = change_scores(self.ref_feats, feats)
        self.last_scores = scores
        changed = changed_squares(scores, self.s["min_change_score"], self.s["median_factor"],
                                  self.s["rel_to_max"])
        changed = frozenset(chess.parse_square(n) for n in changed)

        if changed != self.last_changed:
            self.last_changed, self.changed_since, self.evaluated = changed, t, False
            return events
        if self.evaluated or t - self.changed_since < self.s["confirm_seconds"]:
            return self._maybe_absorb(changed, feats, t, events)

        self.evaluated = True
        if len(changed) > self.s["max_changed_squares"]:
            return self._report(events, Event("obstructed", t,
                                f"{len(changed)} squares changed: hand, shadow or moved board? Waiting.",
                                squares=set(changed)))
        result = match_move(self.board, changed)
        if result.status == ACCEPT:
            events.append(self._apply(result.move, feats, t))
        elif result.status in (AMBIGUOUS, PROMOTION):
            self.pending = result
            kind = "promotion" if result.status == PROMOTION else "ambiguous"
            names = ", ".join(self.board.san(c.move) for c in result.candidates[:3])
            events.append(Event(kind, t, f"Please confirm: {names}", candidates=result.candidates,
                                squares=set(changed)))
        elif len(changed) <= 1:
            self.unchanged_since = self.unchanged_since or t
        else:
            self._report(events, Event("unrecognized", t,
                         "Squares changed but no legal move matches: " +
                         " ".join(chess.square_name(q) for q in sorted(changed)), squares=set(changed)))
        return events

    def confirm(self, move, t=0.0):
        """User picked a move (from candidates or typed). Applies it if legal."""
        if move not in self.board.legal_moves:
            raise ValueError(f"Illegal move {move.uci()} in {self.board.fen()}")
        self.pending = None
        return self._apply(move, self.last_feats, t)

    def reject(self):
        """User says nothing happened: keep the position and treat the current view as the reference."""
        self.pending = None
        self.ref_feats = self.last_feats

    def undo(self):
        """Take back the last move; the tracker expects the pieces to be put back."""
        if not self.board.move_stack:
            return None
        move = self.board.pop()
        self.pending = None
        if self.ref_history:
            self.ref_feats = self.ref_history.pop()
        self.last_changed, self.evaluated = None, False
        return move

    # --- internals ---------------------------------------------------------
    def _apply(self, move, feats, t):
        san = self.board.san(move)
        self.board.push(move)
        self.ref_history.append(self.ref_feats)
        self.ref_feats = feats
        self.reported = None
        self.unchanged_since = None
        return Event("move", t, san, move=move)

    def _report(self, events, ev):
        key = (ev.kind, frozenset(ev.squares))
        if key != self.reported:  # don't repeat the same warning every frame
            self.reported = key
            events.append(ev)
        return events

    def _maybe_absorb(self, changed, feats, t, events):
        """Slowly follow lighting drift and nudged pieces while nothing meaningful changed."""
        if len(changed) <= 1:
            self.unchanged_since = self.unchanged_since or t
            if t - self.unchanged_since >= self.s["absorb_seconds"]:
                self.ref_feats = feats
                self.unchanged_since = t
                self.last_changed = frozenset()
        else:
            self.unchanged_since = None
        return events

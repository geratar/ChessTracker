"""Move tracker: turns a stream of frames into confirmed chess moves.

The python-chess Board is the source of truth. A move is only applied when the
board has been still for a while, the observed square changes are consistent,
and exactly one legal move explains them. Otherwise the tracker reports and
waits (or asks for confirmation); it never guesses.
"""
from dataclasses import dataclass, field

import chess
import numpy as np

from .detector import Aligner, MotionGate, change_scores, changed_squares, square_features
from .moves import ACCEPT, AMBIGUOUS, PROMOTION, TWO_MOVES, MatchResult, candidates_for_square, match_move

TRACKER_DEFAULTS = {
    "motion_threshold": 4.0,       # mean abs diff on a 160x90 frame; ~3 when still, >6 with hands
    "stable_seconds": 0.6,         # how long the scene must be still before we look
    "confirm_seconds": 0.5,        # the same changed squares must persist this long after that
    "max_changed_squares": 8,      # more than this => hand, shadow or bumped board: wait
    "absorb_seconds": 3.0,         # unchanged board for this long => refresh reference (lighting drift)
    "min_change_score": 18.0,
    "median_factor": 3.0,
    "rel_to_max": 0.4,
    "strong_single_factor": 2.0,   # one square changed this strongly => probably a move, ask
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
        self.debug = None              # optional callable(str) for diagnostics

    # --- public ------------------------------------------------------------
    @property
    def waiting_for_user(self):
        return self.pending is not None

    def process(self, frame, t):
        """Feed one frame (BGR) captured at time t (seconds). Returns a list of Events."""
        events = []
        stable = self.gate.update(frame, t, self.aligner.roi())
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
        if self.debug:
            flat = scores.ravel()
            top = sorted(range(64), key=lambda i: -flat[i])[:6]
            names = "abcdefgh"
            self.debug(f"t={t:.1f} eval changed={[chess.square_name(q) for q in sorted(changed)]} "
                       f"top={[(names[i % 8] + str(8 - i // 8), round(float(flat[i]))) for i in top]} "
                       f"median={float(np.median(flat)):.1f} motion_thr={self.gate.threshold:.1f}")
        if len(changed) > self.s["max_changed_squares"]:
            return self._report(events, Event("obstructed", t,
                                f"{len(changed)} squares changed: hand, shadow or moved board? Waiting.",
                                squares=set(changed)))
        result = match_move(self.board, changed)
        if result.status == ACCEPT:
            events.append(self._apply([result.move], feats, t))
        elif result.status in (AMBIGUOUS, PROMOTION, TWO_MOVES):
            self.pending = result
            kind = {AMBIGUOUS: "ambiguous", PROMOTION: "promotion", TWO_MOVES: "two_moves"}[result.status]
            events.append(Event(kind, t, "Please confirm: " + ", ".join(
                self.describe(c) for c in result.candidates[:3]), candidates=result.candidates,
                squares=set(changed)))
        elif len(changed) == 1 and self._strong(changed):
            sq = next(iter(changed))
            cands = candidates_for_square(self.board, sq)
            if cands:
                self.pending = MatchResult(AMBIGUOUS, candidates=cands)
                events.append(Event("ambiguous", t, f"Only {chess.square_name(sq)} changed clearly. Which move? " +
                                    ", ".join(self.describe(c) for c in cands[:3]),
                                    candidates=cands, squares=set(changed)))
            else:
                self._report(events, Event("unrecognized", t,
                             f"{chess.square_name(sq)} changed but no legal move uses it", squares=set(changed)))
        elif len(changed) <= 1:
            self.unchanged_since = self.unchanged_since or t
        else:
            self._report(events, Event("unrecognized", t,
                         "Squares changed but no legal move matches: " +
                         " ".join(chess.square_name(q) for q in sorted(changed)), squares=set(changed)))
        return events

    def describe(self, candidate):
        """SAN text for a candidate (one or two moves)."""
        b = self.board.copy(stack=False)
        out = []
        for m in candidate.moves:
            out.append(b.san(m))
            b.push(m)
        return " ".join(out)

    def confirm(self, moves, t=0.0):
        """User picked a move, a list of moves, or a candidate. Applies them if legal."""
        if hasattr(moves, "moves"):
            moves = moves.moves
        if isinstance(moves, chess.Move):
            moves = [moves]
        b = self.board.copy(stack=False)
        for m in moves:
            if m not in b.legal_moves:
                raise ValueError(f"Illegal move {m.uci()} in {b.fen()}")
            b.push(m)
        self.pending = None
        return self._apply(moves, self.last_feats, t)

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
    def _apply(self, moves, feats, t):
        sans = []
        for m in moves:
            sans.append(self.board.san(m))
            self.board.push(m)
            self.ref_history.append(self.ref_feats)
        self.ref_feats = feats
        self.reported = None
        self.unchanged_since = None
        return Event("move", t, " ".join(sans), move=moves[-1])

    def _strong(self, changed):
        if self.last_scores is None:
            return False
        bar = self.s["strong_single_factor"] * self.s["min_change_score"]
        return any(self.last_scores[7 - chess.square_rank(q), chess.square_file(q)] >= bar for q in changed)

    def _report(self, events, ev):
        key = (ev.kind, frozenset(ev.squares))
        if key != self.reported:  # don't repeat the same warning every frame
            self.reported = key
            events.append(ev)
        return events

    def _maybe_absorb(self, changed, feats, t, events):
        """Slowly follow lighting drift and nudged pieces while nothing meaningful changed."""
        if len(changed) == 0 or (len(changed) == 1 and not self._strong(changed)):
            self.unchanged_since = self.unchanged_since or t
            if t - self.unchanged_since >= self.s["absorb_seconds"]:
                self.ref_feats = feats
                self.unchanged_since = t
                self.last_changed = frozenset()
        else:
            self.unchanged_since = None
        return events

"""Move tracker: turns a stream of frames into confirmed chess moves.

The python-chess Board is the source of truth. A move is only applied when the
board has been still for a while, the observed square changes are consistent,
and exactly one legal move explains them. Otherwise the tracker reports and
waits (or asks for confirmation); it never guesses.
"""
from collections import deque
from dataclasses import dataclass, field

import chess
import numpy as np

from .detector import SQUARE_NAMES, Aligner, SquareMotion, change_scores, changed_squares, square_features
from .moves import (ACCEPT, AMBIGUOUS, PROMOTION, TWO_MOVES, MatchResult, candidates_for_square,
                    expected_changes, match_move)

TRACKER_DEFAULTS = {
    "motion_threshold": 2.0,       # per-square mean abs diff (top-down board); ~0.3 still, >10 with a hand
    "stable_seconds": 0.4,         # a square (and its neighbours) must be still this long before we look
    "confirm_seconds": 0.3,        # the same changed squares must persist this long after that
    "max_moving_squares": 40,      # more of the board moving than this => wait for everything
    "max_changed_squares": 8,      # more than this => hand, shadow or bumped board: wait
    "absorb_seconds": 3.0,         # unchanged board for this long => refresh reference (lighting drift)
    "min_change_score": 18.0,
    "median_factor": 3.0,
    "rel_to_max": 0.4,
    "strong_single_factor": 2.0,   # one square changed this strongly => probably a move, ask
    "rel_margin": 0.2,             # best move must explain this much more of the change than the next
    "piece_height": 1.6,           # tallest piece height in square widths (0 = ignore camera geometry)
    "average_frames": 5,           # average this many still frames to cut camera noise (1 = off)
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
        self.shadows = cal.shadow_map(s["piece_height"]) if s["piece_height"] > 0 else None
        self.motion = SquareMotion(s["motion_threshold"], s["stable_seconds"])
        self.unsettled = set()         # squares a hand is over (or next to) right now
        self._partial_key = None       # hand position we last judged a partial view for
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
        self._avg = None               # running mean of the warped board while still
        self._avg_shift = None

    # --- public ------------------------------------------------------------
    @property
    def waiting_for_user(self):
        return self.pending is not None

    def is_still(self, t):
        return self.motion.all_settled(t)

    def process(self, frame, t):
        """Feed one frame (BGR) captured at time t (seconds). Returns a list of Events."""
        events = []
        warped = self.aligner.calibration().warp(frame)
        self.motion.update(warped, t)
        settled = self.motion.settled(t)
        if settled.all():              # re-check for a nudged camera only when nothing moves
            before = self.aligner.shift
            after = self.aligner.update(frame)
            if max(abs(after[0] - before[0]), abs(after[1] - before[1])) > 0.2:
                warped = self.aligner.calibration().warp(frame)
                self.motion.rebase(warped)    # our own correction is not motion
        unsettled = {chess.parse_square(SQUARE_NAMES[i]) for i in np.nonzero(~settled.ravel())[0]}
        self.unsettled = unsettled
        if len(unsettled) > self.s["max_moving_squares"] or (unsettled and self.ref_feats is None):
            self.last_changed, self.changed_since, self.evaluated = None, None, False
            self.unchanged_since = None
            self._avg = None
            return events

        feats = square_features(warped)
        self.last_feats = feats
        if self.ref_feats is None:
            self.ref_feats = feats
            events.append(Event("ready", t, "Reference position captured"))
            return events
        if self.pending is not None:
            return events

        scores = change_scores(self.ref_feats, feats)
        self.last_scores = scores
        changed = self._changed(scores, unsettled)

        if changed != self.last_changed:
            self.last_changed, self.changed_since, self.evaluated = changed, t, False
            self._partial_key = None
            self._avg = None           # only average frames that agree on what changed
            self._remember(warped)
            return events
        self._remember(warped)
        if unsettled:
            self.unchanged_since = None
            key = frozenset(unsettled)
            if self.evaluated or self._partial_key == key or not changed or \
                    t - self.changed_since < self.s["confirm_seconds"]:
                return events
            self._partial_key = key    # look again whenever the hand moves to other squares
            return self._decide_partial(changed, unsettled, t, events)
        self._partial_key = None
        if self.evaluated or t - self.changed_since < self.s["confirm_seconds"]:
            return self._maybe_absorb(changed, feats, t, events)

        self.evaluated = True
        if self._avg is not None and len(self._avg) > 1:
            # Decide on the mean of the agreeing still frames: same picture, less sensor noise.
            feats = square_features((sum(self._avg) / len(self._avg)).astype(np.uint8))
            self.last_feats = feats
            scores = change_scores(self.ref_feats, feats)
            self.last_scores = scores
            changed = self._changed(scores)
        self._log_eval(t, changed, scores)
        if len(changed) > self.s["max_changed_squares"]:
            return self._report(events, Event("obstructed", t,
                                f"{len(changed)} squares changed: hand, shadow or moved board? Waiting.",
                                squares=set(changed)))
        result = match_move(self.board, changed, shadows=self.shadows, strengths=self.last_strengths,
                            rel_margin=self.s["rel_margin"])
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
                         "Couldn't work out the move (changes seen on " +
                         " ".join(chess.square_name(q) for q in sorted(changed)) +
                         "). If you moved a piece, use 'Enter a move'.", squares=set(changed)))
        return events

    def _decide_partial(self, changed, unsettled, t, events):
        """A hand is still over part of the board. Accept a move elsewhere only when it is
        certain: it doesn't touch the hand's squares, explains every visible change, and no
        other legal move could explain the same changes using the squares we can't see.
        Otherwise just keep waiting (no questions while hands are around)."""
        if self._avg is not None and len(self._avg) > 1:
            feats = square_features((sum(self._avg) / len(self._avg)).astype(np.uint8))
            scores = change_scores(self.ref_feats, feats)
            changed = self._changed(scores, unsettled)
        else:
            feats, scores = self.last_feats, self.last_scores
        self._log_eval(t, changed, scores, unsettled)
        if len(changed) < 2 or len(changed) > self.s["max_changed_squares"]:
            return events
        result = match_move(self.board, changed, shadows=self.shadows, strengths=self.last_strengths,
                            rel_margin=self.s["rel_margin"], allow_two=False)
        if result.status != ACCEPT:
            return events
        move = result.move
        expected = expected_changes(self.board, move)
        if expected & unsettled:
            return events
        near = {q for e in expected for q in chess.SQUARES if chess.square_distance(q, e) <= 1}
        if not changed <= near:                       # something else changed too: maybe a second move
            return events
        for alt in self.board.legal_moves:
            if alt != move:
                e2 = expected_changes(self.board, alt)
                if e2 & unsettled and changed <= e2 | {q for e in e2 for q in chess.SQUARES
                                                      if chess.square_distance(q, e) <= 1}:
                    return events
        # New reference: the current picture, except under the hand (keep the old one there).
        ref = self._patched(feats, unsettled)
        self.last_feats = ref
        events.append(self._apply([move], ref, t))
        self.last_changed, self.evaluated = None, False
        return events

    def _patched(self, feats, keep_old):
        s = feats[0].shape[0] // 8
        out = tuple(a.copy() for a in feats)
        for q in keep_old:
            r, c = 7 - chess.square_rank(q), chess.square_file(q)
            for new, old in zip(out, self.ref_feats):
                new[r * s:(r + 1) * s, c * s:(c + 1) * s] = old[r * s:(r + 1) * s, c * s:(c + 1) * s]
        return out

    def _log_eval(self, t, changed, scores, unsettled=()):
        if not self.debug:
            return
        flat = scores.ravel()
        top = sorted(range(64), key=lambda i: -flat[i])[:6]
        names = "abcdefgh"
        self.debug(f"t={t:.1f} eval changed={[chess.square_name(q) for q in sorted(changed)]} "
                   f"top={[(names[i % 8] + str(8 - i // 8), round(float(flat[i]))) for i in top]} "
                   f"median={float(np.median(flat)):.1f} motion_thr={self.motion.threshold:.1f}"
                   + (f" hand_over={len(unsettled)}" if unsettled else ""))

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

    def set_timing(self, stable_seconds, confirm_seconds):
        self.s["stable_seconds"], self.s["confirm_seconds"] = stable_seconds, confirm_seconds
        self.motion.stable_seconds = stable_seconds

    def retarget(self, cal):
        """Same board, new camera resolution: keep the game and the reference image."""
        self.aligner = Aligner(cal)
        self.motion = SquareMotion(self.s["motion_threshold"], self.s["stable_seconds"])
        self._avg = None

    # --- internals ---------------------------------------------------------
    def _changed(self, scores, unsettled=()):
        if unsettled:                  # squares under a hand: unknown, not "changed"
            scores = scores.copy()
            for q in unsettled:
                scores[7 - chess.square_rank(q), chess.square_file(q)] = 0.0
        changed, bar = changed_squares(scores, self.s["min_change_score"], self.s["median_factor"],
                                       self.s["rel_to_max"], return_bar=True)
        self.last_strengths = {chess.parse_square(SQUARE_NAMES[i]): float(v) / bar
                               for i, v in enumerate(scores.ravel())}
        return frozenset(chess.parse_square(n) for n in changed)

    def _remember(self, warped):
        """Keep the last few warped frames of the current still period."""
        n = max(1, int(self.s["average_frames"]))
        shift = self.aligner.shift
        if (self._avg is None or self._avg_shift is None or
                max(abs(shift[0] - self._avg_shift[0]), abs(shift[1] - self._avg_shift[1])) > 0.5):
            self._avg, self._avg_shift = deque(maxlen=n), shift
        self._avg.append(warped.astype(np.float32))

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

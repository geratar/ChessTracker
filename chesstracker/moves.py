"""Match observed square changes against legal moves.

The previous confirmed position (a python-chess Board) is the source of truth.
Vision supplies the set of squares that changed between two stable frames;
this module decides which legal move (if any) explains them, or reports that
the situation is ambiguous so the UI can ask the user.
"""
from dataclasses import dataclass, field

import chess

ACCEPT, AMBIGUOUS, NO_MOVE, PROMOTION, TWO_MOVES = "accept", "ambiguous", "no_move", "promotion", "two_moves"


def changes_between(before, after):
    """Squares whose contents differ between two positions."""
    return frozenset(sq for sq in chess.SQUARES if before.piece_at(sq) != after.piece_at(sq))


def expected_changes(board, *moves):
    """Squares whose contents differ after playing `moves` on `board`
    (covers captures, castling, en passant and promotion automatically)."""
    after = board.copy(stack=False)
    for m in moves:
        after.push(m)
    return changes_between(board, after)


@dataclass
class Candidate:
    move: chess.Move                 # first (usually only) move
    score: float
    matched: int
    missing: int
    extra: int
    moves: list = None               # full sequence (two entries when a move was missed)

    def __post_init__(self):
        if self.moves is None:
            self.moves = [self.move]


@dataclass
class MatchResult:
    status: str                      # ACCEPT | AMBIGUOUS | NO_MOVE | PROMOTION | TWO_MOVES
    move: chess.Move = None          # set for ACCEPT (and PROMOTION: queen by default)
    candidates: list = field(default_factory=list)   # best first


def _near(sq, squares):
    return any(chess.square_distance(sq, e) == 1 for e in squares)


def match_move(board, changed, w_missing=1.0, w_extra=0.5, w_extra_near=0.25, min_score=1.5,
               min_margin=1.0, max_candidates=5, allow_two=True):
    """Rank legal moves by how well they explain `changed` (iterable of squares).

    score = matched - w_missing * missing - w_extra * extra
      matched: expected squares that changed
      missing: expected squares that did NOT change
      extra:   changed squares the move doesn't explain (occlusion, shadows);
               ones next to an expected square cost less (tall pieces hide neighbours)
    Accept only when the best move scores >= min_score AND beats the runner-up
    by >= min_margin; otherwise ask the user.
    """
    changed = frozenset(changed)
    if len(changed) < 2:
        return MatchResult(NO_MOVE)

    def score(moves):
        exp = expected_changes(board, *moves)
        matched = len(exp & changed)
        missing = len(exp - changed)
        extras = changed - exp
        near = sum(1 for q in extras if _near(q, exp))
        s = matched - w_missing * missing - w_extra * (len(extras) - near) - w_extra_near * near
        return Candidate(moves[0], s, matched, missing, len(extras), list(moves))

    scored = [score([mv]) for mv in board.legal_moves]

    # promotions to different pieces look identical: collapse to one entry (queen)
    by_squares = {}
    for c in scored:
        key = (c.move.from_square, c.move.to_square)
        if key not in by_squares or c.move.promotion == chess.QUEEN:
            by_squares[key] = c
    ranked = sorted(by_squares.values(), key=lambda c: c.score, reverse=True)[:max_candidates]

    if not ranked or ranked[0].score < min_score:
        if allow_two and len(changed) >= 3:
            two = _match_two(board, changed, score, ranked, min_score, max_candidates)
            if two:
                return MatchResult(TWO_MOVES, candidates=two)
        return MatchResult(NO_MOVE, candidates=ranked)
    best = ranked[0]
    if len(ranked) > 1 and best.score - ranked[1].score < min_margin:
        return MatchResult(AMBIGUOUS, candidates=ranked)
    if best.move.promotion:
        return MatchResult(PROMOTION, move=best.move, candidates=ranked)
    return MatchResult(ACCEPT, move=best.move, candidates=ranked)


def _match_two(board, changed, score, singles, min_score, max_candidates):
    """A move was missed: look for two consecutive moves that explain the changes.
    Only first moves touching a changed square are tried (keeps it fast)."""
    out = []
    for first in board.legal_moves:
        if first.from_square not in changed and first.to_square not in changed:
            continue
        b2 = board.copy(stack=False)
        b2.push(first)
        for second in b2.legal_moves:
            if second.from_square not in changed and second.to_square not in changed:
                continue
            if second.promotion not in (None, chess.QUEEN) or first.promotion not in (None, chess.QUEEN):
                continue
            c = score([first, second])
            if c.score >= min_score:
                out.append(c)
    out.sort(key=lambda c: c.score, reverse=True)
    return out[:max_candidates]


def candidates_for_square(board, square, max_candidates=5):
    """Moves that land on (preferred) or leave `square`: used when only one
    square visibly changed, e.g. because the other one is hidden behind pieces."""
    to = [m for m in board.legal_moves if m.to_square == square and m.promotion in (None, chess.QUEEN)]
    frm = [m for m in board.legal_moves if m.from_square == square and m.promotion in (None, chess.QUEEN)]
    return [Candidate(m, 0.0, 1, 1, 0) for m in (to + frm)[:max_candidates]]

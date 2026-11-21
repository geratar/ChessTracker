"""Match observed square changes against legal moves.

The previous confirmed position (a python-chess Board) is the source of truth.
Vision supplies the set of squares that changed between two stable frames;
this module decides which legal move (if any) explains them, or reports that
the situation is ambiguous so the UI can ask the user.
"""
from dataclasses import dataclass, field

import chess

ACCEPT, AMBIGUOUS, NO_MOVE, PROMOTION = "accept", "ambiguous", "no_move", "promotion"


def expected_changes(board, move):
    """Squares whose contents differ after `move` is played on `board`."""
    sq = {move.from_square, move.to_square}
    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        if board.is_kingside_castling(move):
            sq |= {chess.square(7, rank), chess.square(5, rank)}
            sq.add(chess.square(6, rank))
        else:
            sq |= {chess.square(0, rank), chess.square(3, rank)}
            sq.add(chess.square(2, rank))
    elif board.is_en_passant(move):
        sq.add(chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square)))
    return frozenset(sq)


@dataclass
class Candidate:
    move: chess.Move
    score: float
    matched: int
    missing: int
    extra: int


@dataclass
class MatchResult:
    status: str                      # ACCEPT | AMBIGUOUS | NO_MOVE | PROMOTION
    move: chess.Move = None          # set for ACCEPT (and PROMOTION: queen by default)
    candidates: list = field(default_factory=list)   # best first


def _near(sq, squares):
    return any(chess.square_distance(sq, e) == 1 for e in squares)


def match_move(board, changed, w_missing=1.0, w_extra=0.5, w_extra_near=0.25, min_score=1.5,
               min_margin=1.0, max_candidates=5):
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

    scored = []
    for mv in board.legal_moves:
        exp = expected_changes(board, mv)
        matched = len(exp & changed)
        missing = len(exp - changed)
        extras = changed - exp
        near = sum(1 for q in extras if _near(q, exp))
        extra = len(extras)
        s = matched - w_missing * missing - w_extra * (extra - near) - w_extra_near * near
        scored.append(Candidate(mv, s, matched, missing, extra))

    # promotions to different pieces look identical: collapse to one entry (queen)
    by_squares = {}
    for c in scored:
        key = (c.move.from_square, c.move.to_square)
        if key not in by_squares or c.move.promotion == chess.QUEEN:
            by_squares[key] = c
    ranked = sorted(by_squares.values(), key=lambda c: c.score, reverse=True)[:max_candidates]

    if not ranked or ranked[0].score < min_score:
        return MatchResult(NO_MOVE, candidates=ranked)
    best = ranked[0]
    if len(ranked) > 1 and best.score - ranked[1].score < min_margin:
        return MatchResult(AMBIGUOUS, candidates=ranked)
    if best.move.promotion:
        return MatchResult(PROMOTION, move=best.move, candidates=ranked)
    return MatchResult(ACCEPT, move=best.move, candidates=ranked)

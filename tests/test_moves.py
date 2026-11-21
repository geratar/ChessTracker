import chess

from chesstracker.moves import ACCEPT, AMBIGUOUS, NO_MOVE, PROMOTION, expected_changes, match_move

S = chess.parse_square


def sqs(*names):
    return {S(n) for n in names}


def test_normal_move():
    r = match_move(chess.Board(), sqs("e2", "e4"))
    assert r.status == ACCEPT and r.move == chess.Move.from_uci("e2e4")


def test_capture():
    b = chess.Board()
    for m in ("e4", "d5"):
        b.push_san(m)
    r = match_move(b, sqs("e4", "d5"))
    assert r.status == ACCEPT and b.san(r.move) == "exd5"


def test_kingside_castling():
    b = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    r = match_move(b, sqs("e1", "f1", "g1", "h1"))
    assert r.status == ACCEPT and b.is_kingside_castling(r.move)


def test_queenside_castling():
    b = chess.Board("r3kbnr/pppqpppp/2n5/3p1b2/3P1B2/2N5/PPPQPPPP/R3KBNR b KQkq - 5 5")
    r = match_move(b, sqs("e8", "d8", "c8", "a8"))
    assert r.status == ACCEPT and b.is_queenside_castling(r.move)


def test_castling_seen_as_king_move_only_is_not_silently_wrong():
    # Only king squares seen changing: castling explains them best but rook squares are missing.
    b = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    r = match_move(b, sqs("e1", "g1"))
    assert r.status != ACCEPT or b.is_kingside_castling(r.move)


def test_en_passant():
    b = chess.Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    r = match_move(b, sqs("e5", "f6", "f5"))
    assert r.status == ACCEPT and b.is_en_passant(r.move)
    assert expected_changes(b, r.move) == frozenset(sqs("e5", "f6", "f5"))


def test_promotion_asks_for_piece():
    b = chess.Board("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    r = match_move(b, sqs("e7", "e8"))
    assert r.status == PROMOTION and r.move.promotion == chess.QUEEN


def test_no_change_is_no_move():
    assert match_move(chess.Board(), set()).status == NO_MOVE
    assert match_move(chess.Board(), sqs("e2")).status == NO_MOVE


def test_noise_is_no_move():
    # changes that no legal move explains (e.g. a shadow across the middle)
    r = match_move(chess.Board(), sqs("d5", "e5", "f5"))
    assert r.status == NO_MOVE


def test_ambiguous_asks():
    # Knight on b1 could go to a3 or c3; seeing b1, a3 and c3 change is ambiguous
    r = match_move(chess.Board(), sqs("b1", "a3", "c3"))
    assert r.status == AMBIGUOUS
    names = {chess.Board().san(c.move) for c in r.candidates[:2]}
    assert names == {"Na3", "Nc3"}


def test_one_extra_square_from_occlusion_still_accepted():
    r = match_move(chess.Board(), sqs("e2", "e4", "e5"))
    assert r.status == ACCEPT and r.move == chess.Move.from_uci("e2e4")


def test_board_is_not_modified():
    b = chess.Board()
    fen = b.fen()
    match_move(b, sqs("e2", "e4"))
    assert b.fen() == fen


def test_two_moves_when_one_was_missed():
    from chesstracker.moves import TWO_MOVES
    b = chess.Board()
    r = match_move(b, sqs("c2", "c4", "d7", "d5"))
    assert r.status == TWO_MOVES
    first = r.candidates[0]
    assert [b.san(first.moves[0])] == ["c4"] and first.moves[1] == chess.Move.from_uci("d7d5")


def test_two_moves_with_hidden_origin_square():
    # c2 hidden behind other pieces: c4 d7 d5 (+ occlusion neighbours c5 c6) changed
    from chesstracker.moves import TWO_MOVES
    r = match_move(chess.Board(), sqs("c4", "c5", "d5", "c6", "d7"))
    assert r.status == TWO_MOVES
    assert any(c.moves == [chess.Move.from_uci("c2c4"), chess.Move.from_uci("d7d5")] for c in r.candidates)


def test_candidates_for_single_square():
    from chesstracker.moves import candidates_for_square
    c = candidates_for_square(chess.Board(), S("c4"))
    assert [x.move.uci() for x in c] == ["c2c4"]


# --- camera geometry (tall pieces hide the squares behind them) -------------
from pathlib import Path as _P
from chesstracker.calibration import Calibration as _Cal

_SHADOWS = _Cal.load(_P(__file__).parent / "fixtures" / "game1" / "calibration.json").shadow_map()


def test_shadow_map_points_away_from_camera():
    # In the user's first setup the camera sat at White's left: pieces lean toward the a-file / rank 8
    assert {S("d2"), S("d3")} <= _SHADOWS[S("e2")]
    assert S("f2") not in _SHADOWS[S("e2")]


def test_knight_move_with_occlusion_extras_found_with_geometry():
    b = chess.Board()
    # g1-f3 and every square the knight hides changed: without geometry nothing matches,
    # with geometry Nf3 is the top candidate (accepted or offered first)
    changed = {S("g1"), S("f3")} | _SHADOWS[S("f3")] | _SHADOWS[S("g1")]
    without = match_move(b, changed, allow_two=False)
    with_geo = match_move(b, changed, shadows=_SHADOWS, allow_two=False)
    assert without.status == "no_move"
    assert with_geo.status in ("accept", "ambiguous") and b.san(with_geo.candidates[0].move) == "Nf3"


def test_typical_occlusion_accepted():
    b = chess.Board()
    # e2-e4 plus one hidden square behind e4 and one behind e2
    changed = {S("e2"), S("e4")} | set(list(_SHADOWS[S("e4")])[:1]) | set(list(_SHADOWS[S("e2")])[:1])
    r = match_move(b, changed, shadows=_SHADOWS)
    assert r.status == "accept" and b.san(r.move) == "e4"


def test_geometry_does_not_invent_moves_from_shadow_only():
    # only shadow squares changed (e.g. a hand's shadow): still no move
    r = match_move(chess.Board(), _SHADOWS[S("e4")], shadows=_SHADOWS)
    assert r.status != "accept"


# --- real numbers from the user's debug.log (second setup) -----------------
_SH2 = _Cal.load(_P(__file__).parent / "fixtures" / "game2" / "calibration.json").shadow_map()


def _st(bar, **scores):
    st = {q: 3.5 / bar for q in chess.SQUARES}          # median noise
    st.update({S(k): v / bar for k, v in scores.items()})
    return st


def test_log_e4_with_neighbour_file_lit_up():
    changed = sqs("d2", "e2", "d4", "e4")
    r = match_move(chess.Board(), changed, shadows=_SH2, strengths=_st(18.4, e4=46, e2=36, d4=32, d2=32))
    assert r.status == "accept" and chess.Board().san(r.move) == "e4"


def test_log_black_e5():
    b = chess.Board()
    b.push_san("e4")
    r = match_move(b, sqs("d5", "e5", "d7", "e7"), shadows=_SH2,
                   strengths=_st(18.0, d5=33, e5=32, d7=31, e7=25))
    assert r.status == "accept" and b.san(r.move) == "e5"


def test_log_exd4_not_qxd4():
    b = chess.Board()
    for m in ("e4", "e5", "Nf3", "d5", "exd5", "Qxd5", "d4"):
        b.push_san(m)
    r = match_move(b, sqs("c4", "d4", "d5", "e5"), shadows=_SH2,
                   strengths=_st(23.2, d4=58, c4=38, d5=33, e5=31))
    assert r.status == "accept" and b.san(r.move) == "exd4"

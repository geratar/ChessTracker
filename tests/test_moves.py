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

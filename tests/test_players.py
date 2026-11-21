import json
import xml.dom.minidom

import chess
import pytest

import app
from chesstracker import players


def test_all_avatars_are_valid_svg():
    assert players.COUNT == 20
    svgs = {players.avatar_svg(i) for i in range(players.COUNT)}
    assert len(svgs) == 20
    for s in svgs:
        xml.dom.minidom.parseString(s)
    with pytest.raises(ValueError):
        players.avatar_svg(20)


def test_create_and_update_players(tmp_path):
    ps = players.Players(tmp_path / "players.json")
    a = ps.create("Anna", 3)
    ps.create("Ben", 5)
    with pytest.raises(ValueError):
        ps.create("anna", 1)
    with pytest.raises(ValueError):
        ps.create("  ", 1)
    ps.update(a["id"], avatar=7)
    assert ps.get(a["id"])["avatar"] == 7
    assert [p["name"] for p in json.loads((tmp_path / "players.json").read_text())] == ["Anna", "Ben"]


def test_explore_move_and_light_board():
    r = app.explore_move(chess.STARTING_FEN, "e2e4")
    assert r["san"] == "e4" and r["uci"] == "e2e4"
    with pytest.raises(ValueError):
        app.explore_move(chess.STARTING_FEN, "e2e5")
    promo = app.explore_move("8/P7/8/8/8/8/8/k6K w - - 0 1", "a7a8")
    assert promo["uci"] == "a7a8q"
    assert "#ebecd0" in app.board_svg(chess.STARTING_FEN)
    assert "#ebecd0" not in app.board_svg(chess.STARTING_FEN, explore=True)


FAKE_UCI = '''#!{py}
import sys
import chess
fen = chess.STARTING_FEN
for line in sys.stdin:
    c = line.split()
    if not c:
        continue
    if c[0] == "uci":
        print("id name fake"); print("uciok")
    elif c[0] == "isready":
        print("readyok")
    elif c[0] == "position":
        b = chess.Board() if c[1] == "startpos" else chess.Board(" ".join(c[2:8]))
        if "moves" in c:
            for m in c[c.index("moves") + 1:]:
                b.push_uci(m)
        fen = b.fen()
    elif c[0] == "go":
        m = sorted(chess.Board(fen).legal_moves, key=lambda x: x.uci())[0].uci()
        print("info depth 1 score cp 42 pv " + m); print("bestmove " + m)
    elif c[0] == "quit":
        break
    sys.stdout.flush()
'''


def test_evaluate_single_position_for_explored_lines(tmp_path):
    import sys
    from chesstracker.analysis import Analyzer
    eng = tmp_path / "engine"
    eng.mkdir()
    sf = eng / "stockfish"
    sf.write_text(FAKE_UCI.replace("{py}", sys.executable))
    sf.chmod(0o755)
    a = Analyzer(eng, tmp_path / "library", seconds=0.05)
    try:
        ev = a.evaluate(chess.STARTING_FEN)
        assert ev["cp"] == 42 and ev["best"] == "a2a3" and ev["best_san"] == "a3"
        assert a.evaluate(chess.STARTING_FEN) is ev        # cached
    finally:
        a.close()


def test_evaluate_without_stockfish_says_so(tmp_path, monkeypatch):
    from chesstracker import analysis
    monkeypatch.setattr(analysis, "find_stockfish", lambda d: None)
    with pytest.raises(ValueError):
        analysis.Analyzer(tmp_path, tmp_path).evaluate(chess.STARTING_FEN)

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

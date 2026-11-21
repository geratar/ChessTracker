import shutil
import time
from pathlib import Path

import chess
import pytest

from chesstracker.engine import Engine

FIX = Path(__file__).parent / "fixtures" / "game1"


@pytest.fixture
def engine(tmp_path):
    shutil.copy(FIX / "calibration.json", tmp_path / "calibration.json")
    e = Engine(source=str(FIX / "00_start.jpg"), data_dir=tmp_path)
    time.sleep(0.3)
    yield e
    e.shutdown()


def test_state_and_calibration_loaded(engine):
    s = engine.state()
    assert s["calibration"]["saved"] and len(s["calibration"]["corners"]) == 4
    assert s["mode"] == "setup"


def test_manual_move_correct_and_undo(engine):
    engine.start_tracking()
    engine.manual_move("e4")
    engine.manual_move("e7e5")
    assert engine.state()["moves"] == ["e4", "e5"]
    engine.correct_last("c5")
    assert engine.state()["moves"] == ["e4", "c5"]
    with pytest.raises(ValueError):
        engine.correct_last("Ke2")      # not legal for Black
    with pytest.raises(ValueError):
        engine.manual_move("nonsense")
    engine.undo()
    assert engine.state()["moves"] == ["e4"]


def test_promotion_by_squares_defaults_to_queen(engine):
    engine.start_tracking("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    engine.manual_move("e7e8")
    assert engine.state()["moves"] == ["e8=Q"]


def test_library_roundtrip(engine):
    engine.start_tracking()
    for m in ("e4", "e5", "Nf3"):
        engine.manual_move(m)
    gid = engine.save_game("Saturday game")
    games = engine.list_games()
    assert games[0]["name"] == "Saturday game" and games[0]["moves"] == 3
    g = engine.load_game(gid)
    assert [p["san"] for p in g["plies"][1:]] == ["e4", "e5", "Nf3"]
    assert g["plies"][0]["fen"] == chess.STARTING_FEN
    with pytest.raises(ValueError):
        engine.load_game("../calibration.json")
    engine.delete_game(gid)
    assert engine.list_games() == []


def test_settings(engine):
    engine.update_settings(theme="blue", flipped=True)
    assert engine.state()["settings"]["theme"] == "blue"
    assert engine.state()["settings"]["flipped"] is True
    with pytest.raises(ValueError):
        engine.update_settings(theme="pink")

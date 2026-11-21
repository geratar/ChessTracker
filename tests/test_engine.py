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


def test_result_and_unsaved_flag(engine):
    engine.start_tracking()
    engine.manual_move("e4")
    assert engine.state()["unsaved"]
    gid = engine.save_game("Won it", "1-0")
    assert not engine.state()["unsaved"]
    assert engine.list_games()[0]["result"] == "1-0"
    assert engine.load_game(gid)["result"] == "1-0"
    assert "1-0" in engine.load_game(gid)["pgn"]
    engine.manual_move("e5")
    assert engine.state()["unsaved"]
    with pytest.raises(ValueError):
        engine.save_game("x", "2-0")


@pytest.mark.skipif(__import__("chesstracker.analysis", fromlist=["x"]).find_stockfish("/none") is None,
                    reason="no stockfish")
def test_analysis_end_to_end(engine):
    engine.start_tracking()
    for m in ("e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"):
        engine.manual_move(m)
    gid = engine.save_game("Scholar", "1-0")
    engine.analyzer.seconds = 0.05
    engine.analyze(gid)
    for _ in range(200):
        st = engine.analysis(gid)
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert st["state"] == "done", st
    res = st["result"]
    assert len(res["evals"]) == 8 and len(res["moves"]) == 7
    assert res["moves"][5]["mark"] == "??"           # ...Nf6 allows mate
    assert res["evals"][-1]["cp"] == 10000


def test_rename_keeps_moves_and_result(engine):
    engine.start_tracking()
    engine.manual_move("d4")
    gid = engine.save_game("Old name", "0-1")
    engine.rename_game(gid, "Club night vs Anna")
    g = engine.load_game(gid)
    assert g["name"] == "Club night vs Anna" and g["result"] == "0-1" and g["plies"][1]["san"] == "d4"
    with pytest.raises(ValueError):
        engine.rename_game(gid, "  ")
    with pytest.raises(ValueError):
        engine.rename_game("../x.pgn", "a")


def test_corners_follow_a_higher_camera_resolution(tmp_path):
    """Calibrated at 720p, camera now gives 1080p: corners scale, no recalibration needed."""
    import cv2, json
    shutil.copy(FIX / "calibration.json", tmp_path / "calibration.json")
    old = json.loads((tmp_path / "calibration.json").read_text())
    img = cv2.imread(str(FIX / "00_start.jpg"))
    h, w = img.shape[:2]
    big = cv2.resize(img, (w * 3 // 2, h * 3 // 2))
    cv2.imwrite(str(tmp_path / "big.jpg"), big)
    e = Engine(source=str(tmp_path / "big.jpg"), data_dir=tmp_path)
    try:
        time.sleep(0.3)
        s = e.state()
        assert s["camera"]["frame_size"] == [w * 3 // 2, h * 3 // 2]
        for (x0, y0), (x1, y1) in zip(old["corners"], s["calibration"]["corners"]):
            assert abs(x1 - x0 * 1.5) < 1 and abs(y1 - y0 * 1.5) < 1
        assert s["calibration"]["square_px"] > 0
    finally:
        e.shutdown()


def test_speed_setting_changes_tracker_timing(engine):
    engine.start_tracking()
    engine.update_settings(speed="fast")
    assert engine.tracker.s["stable_seconds"] == 0.25 and engine.tracker.motion.stable_seconds == 0.25
    assert engine.state()["settings"]["speed"] == "fast"
    with pytest.raises(ValueError):
        engine.update_settings(speed="warp")

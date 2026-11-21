import cv2
import numpy as np
import pytest

from chesstracker.calibration import Calibration, order_clockwise, orientation_check

N = 400
# Camera-frame positions of the board's a8, h8, h1, a1 corners (angled view: far edge narrower)
A8, H8, H1, A1 = [420, 150], [860, 160], [1000, 600], [280, 590]


def topdown_board(n=N):
    """Top-down board, white at bottom: a1 dark. Each square's blue channel encodes its index."""
    img = np.zeros((n, n, 3), np.uint8)
    s = n // 8
    for row in range(8):
        for f in range(8):
            dark = (f + (7 - row)) % 2 == 0  # a1 (f=0, rank 0) dark
            v = 60 if dark else 200
            img[row * s:(row + 1) * s, f * s:(f + 1) * s] = (row * 8 + f, v, v)
    return img


def camera_frame():
    """Project the top-down board into a 1280x720 'camera' image."""
    src = np.float32([[0, 0], [N, 0], [N, N], [0, N]])
    dst = np.float32([A8, H8, H1, A1])
    H = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(topdown_board(), H, (1280, 720), flags=cv2.INTER_NEAREST)


def expected_square(row, f):
    return f"{'abcdefgh'[f]}{8 - row}"


def test_order_clockwise_any_click_order():
    pts = order_clockwise([A1, H8, A8, H1])
    assert pts.tolist() == [A8, H8, H1, A1]


def test_order_clockwise_rejects_wrong_count():
    with pytest.raises(ValueError):
        order_clockwise([[0, 0], [1, 1], [2, 2]])


def test_warp_maps_every_square_correctly():
    frame = camera_frame()
    cal = Calibration([A1, H1, A8, H8], rotation=0, warp_size=N)  # scrambled click order
    warped = cal.warp(frame)
    for row in range(8):
        for f in range(8):
            x0, y0, x1, y1 = (int(v) for v in cal.square_rect(expected_square(row, f)))
            centre = warped[(y0 + y1) // 2, (x0 + x1) // 2]
            assert centre[0] == row * 8 + f, f"wrong square at {expected_square(row, f)}"


def test_orientation_check_detects_rotation():
    frame = camera_frame()
    ok_count = 0
    for rot in range(4):
        cal = Calibration([A8, H8, H1, A1], rotation=rot, warp_size=N)
        ok, _ = orientation_check(cal.warp(frame), cal)
        ok_count += ok
        if rot % 2 == 1:
            assert not ok   # 90/270 deg puts a light square on a1
    assert ok_count == 2    # 0 and 180 deg both look right; colour alone can't tell them apart


def test_rotation_moves_a1():
    cal = Calibration([A8, H8, H1, A1], rotation=0, warp_size=N)
    assert cal.camera_to_square(A1[0] + 15, A1[1] - 15) == "a1"
    cal.rotation = 2
    assert cal.camera_to_square(A1[0] + 15, A1[1] - 15) == "h8"


def test_square_at_bounds():
    cal = Calibration([A8, H8, H1, A1], warp_size=N)
    assert cal.square_at(1, N - 1) == "a1"
    assert cal.square_at(N - 1, 1) == "h8"
    assert cal.square_at(-1, 5) is None
    assert cal.square_at(N + 1, 5) is None


def test_grid_projects_to_clicked_corners():
    cal = Calibration([A8, H8, H1, A1], warp_size=N)
    g = cal.grid_in_camera()
    assert np.allclose(g[0, 0], A8, atol=0.5)
    assert np.allclose(g[8, 8], H1, atol=0.5)


def test_save_load_roundtrip(tmp_path):
    cal = Calibration([A8, H8, H1, A1], rotation=3, warp_size=N, frame_size=[1280, 720], camera_index=1)
    p = tmp_path / "cal.json"
    cal.save(p)
    loaded = Calibration.load(p)
    assert loaded.to_dict() == cal.to_dict()
    assert np.allclose(loaded.homography(), cal.homography())


def test_load_missing_and_invalid(tmp_path):
    with pytest.raises(FileNotFoundError):
        Calibration.load(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text('{"corners": [[0, 0]]}')
    with pytest.raises(ValueError):
        Calibration.load(bad)

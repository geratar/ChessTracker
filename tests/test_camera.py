import cv2
import numpy as np
import pytest

from chesstracker.camera import FrameSource, backend_id


def test_image_source(tmp_path):
    p = tmp_path / "f.png"
    cv2.imwrite(str(p), np.full((10, 20, 3), 7, np.uint8))
    src = FrameSource(str(p))
    f = src.read()
    assert src.connected and f.shape == (10, 20, 3)


def test_video_source_loops(tmp_path):
    p = tmp_path / "v.avi"
    w = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"MJPG"), 10, (32, 24))
    for i in range(3):
        w.write(np.full((24, 32, 3), i * 80, np.uint8))
    w.release()
    src = FrameSource(str(p))
    frames = [src.read() for _ in range(7)]
    assert all(f is not None for f in frames)


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        FrameSource("does_not_exist.mp4")


def test_unknown_backend():
    with pytest.raises(ValueError):
        backend_id("bogus")


def test_missing_camera_does_not_crash():
    src = FrameSource(99, reconnect_interval_s=999)
    assert src.read() is None
    assert not src.connected

"""Webcam / video-file capture with automatic reconnection."""
import platform
import time
from pathlib import Path

import cv2

_BACKENDS = {
    "any": cv2.CAP_ANY,
    "avfoundation": cv2.CAP_AVFOUNDATION,
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
    "v4l2": cv2.CAP_V4L2,
}


def backend_id(name="auto"):
    if name == "auto":
        system = platform.system()
        if system == "Darwin":
            return cv2.CAP_AVFOUNDATION
        if system == "Windows":
            return cv2.CAP_DSHOW  # opens much faster than MSMF
        return cv2.CAP_ANY
    if name not in _BACKENDS:
        raise ValueError(f"Unknown camera_backend '{name}'. Use one of: auto, {', '.join(_BACKENDS)}")
    return _BACKENDS[name]


def list_cameras(max_index=5, backend="auto"):
    """Return [(index, width, height)] for cameras that deliver a frame."""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, backend_id(backend))
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                found.append((i, frame.shape[1], frame.shape[0]))
        cap.release()
    return found


class FrameSource:
    """Reads frames from a camera index, a video file, or a single image.

    Camera reads that fail trigger reconnect attempts instead of crashing,
    so a camera unplug shows up as `connected == False` until it comes back.
    Video files loop, which makes recorded sessions usable for repeatable tests.
    """

    def __init__(self, source=0, backend="auto", width=None, height=None,
                 reconnect_interval_s=2.0):
        self.source = source
        self.backend = backend
        self.width, self.height = width, height
        self.reconnect_interval_s = reconnect_interval_s
        self.cap = None
        self.image = None
        self.connected = False
        self._last_attempt = 0.0
        self._open()

    @property
    def is_camera(self):
        return isinstance(self.source, int)

    def _open(self):
        self._last_attempt = time.monotonic()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self.is_camera:
            self.cap = cv2.VideoCapture(self.source, backend_id(self.backend))
            if self.width:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height:
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        else:
            path = Path(self.source)
            if not path.exists():
                raise FileNotFoundError(f"Video/image not found: {path}")
            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"):
                self.image = cv2.imread(str(path))
                self.connected = self.image is not None
                return
            self.cap = cv2.VideoCapture(str(path))
        self.connected = self.cap.isOpened()

    def read(self):
        """Return a BGR frame, or None if no frame is available right now."""
        if self.image is not None:
            return self.image.copy()
        if self.connected:
            ok, frame = self.cap.read()
            if ok and frame is not None:
                return frame
            if not self.is_camera:  # end of video: loop
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
                return frame if ok else None
            self.connected = False
        if self.is_camera and time.monotonic() - self._last_attempt >= self.reconnect_interval_s:
            self._open()
        return None

    def release(self):
        if self.cap is not None:
            self.cap.release()

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
    """First backend to try (kept for callers that need a single id)."""
    return backend_candidates(name)[0]


def backend_candidates(name="auto"):
    """Backends to try in order. 'auto' tries several because some OpenCV
    builds can't capture by index with a given backend (seen with DSHOW)."""
    if name == "auto":
        system = platform.system()
        if system == "Darwin":
            return [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
        if system == "Windows":
            return [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
        return [cv2.CAP_V4L2, cv2.CAP_ANY]
    if name not in _BACKENDS:
        raise ValueError(f"Unknown camera_backend '{name}'. Use one of: auto, {', '.join(_BACKENDS)}")
    return [_BACKENDS[name]]


def open_camera(index, backend="auto"):
    """Open a camera index with the first backend that delivers a frame.
    Returns (VideoCapture, backend_name) or (None, None)."""
    for b in backend_candidates(backend):
        cap = cv2.VideoCapture(index, b)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                return cap, cap.getBackendName()
        cap.release()
    return None, None


def list_cameras(max_index=5, backend="auto"):
    """Return [(index, width, height, backend_name)] for cameras that deliver a frame."""
    found = []
    for i in range(max_index):
        cap, name = open_camera(i, backend)
        if cap is not None:
            found.append((i, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                          int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), name))
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
            self.cap, _ = open_camera(self.source, self.backend)
            if self.cap is None:
                self.connected = False
                return
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

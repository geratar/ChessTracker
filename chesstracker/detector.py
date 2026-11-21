"""Vision side of move tracking: alignment, stability gate, per-square change scores.

Pipeline per frame:
  1. Align: estimate the small camera/board shift (phase correlation on the board
     area) against a reference frame and shift the calibrated corners to match.
  2. Stability: frame-to-frame motion on a small blurred image. The board counts
     as still after `stable_seconds` of low motion (hands moving => not still).
  3. When still, compare the warped board with the last confirmed board image and
     give every square a change score (brightness-normalised L channel + edge
     strength, which shrugs off soft shadows and auto-exposure drift).
"""
from collections import deque

import cv2
import numpy as np

from .calibration import Calibration

SQUARE_NAMES = [f"{'abcdefgh'[f]}{8 - row}" for row in range(8) for f in range(8)]  # row-major, a8 first


class Aligner:
    """Tracks a small translation of the board relative to a reference frame."""

    def __init__(self, cal, margin_px=40, max_shift_px=25):
        self.cal = cal
        pts = np.asarray(cal.corners, dtype=np.float32)
        self.x0, self.y0 = (pts.min(0) - margin_px).astype(int)
        self.x1, self.y1 = (pts.max(0) + margin_px).astype(int)
        self.max_shift = max_shift_px
        self.ref = None
        self.win = None
        self.shift = (0.0, 0.0)

    def _crop(self, frame):
        h, w = frame.shape[:2]
        x0, y0 = max(self.x0, 0), max(self.y0, 0)
        x1, y1 = min(self.x1, w), min(self.y1, h)
        g = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        return g

    def roi(self, grow=0.25):
        """Board area plus a margin (hands reach in from the sides)."""
        w, h = self.x1 - self.x0, self.y1 - self.y0
        gx, gy = int(w * grow), int(h * grow)
        return (self.x0 - gx, self.y0 - gy, self.x1 + gx, self.y1 + gy)

    def set_reference(self, frame):
        self.ref = self._crop(frame)
        self.win = cv2.createHanningWindow((self.ref.shape[1], self.ref.shape[0]), cv2.CV_32F)
        self.shift = (0.0, 0.0)

    def update(self, frame):
        if self.ref is None:
            self.set_reference(frame)
            return self.shift
        g = self._crop(frame)
        if g.shape != self.ref.shape:
            return self.shift
        (dx, dy), resp = cv2.phaseCorrelate(self.ref, g, self.win)
        if resp > 0.3 and abs(dx) < self.max_shift and abs(dy) < self.max_shift:
            self.shift = (dx, dy)
        return self.shift

    def calibration(self):
        dx, dy = self.shift
        c = self.cal
        return Calibration([[x + dx, y + dy] for x, y in c.corners], c.rotation, c.warp_size,
                           c.frame_size, c.camera_index)


class MotionGate:
    """Says when the scene has been still long enough to trust.

    Cameras differ in sensor noise, so the threshold adapts: it is the larger of
    `motion_threshold` and `noise_factor` x the camera's measured noise floor
    (a low percentile of recent motion values).
    """

    def __init__(self, motion_threshold=4.0, stable_seconds=0.6, noise_factor=1.6, history=300):
        self.base_threshold = motion_threshold
        self.threshold = motion_threshold
        self.stable_seconds = stable_seconds
        self.noise_factor = noise_factor
        self.history = deque(maxlen=history)
        self.prev = None
        self.still_since = None
        self.motion = 0.0

    def update(self, frame, t, roi=None):
        """roi=(x0, y0, x1, y1): only watch this area (the board), so people
        moving elsewhere in the picture don't keep the board from counting as still."""
        if roi is not None:
            h, w = frame.shape[:2]
            x0, y0, x1, y1 = max(roi[0], 0), max(roi[1], 0), min(roi[2], w), min(roi[3], h)
            if x1 - x0 > 20 and y1 - y0 > 20:
                frame = frame[y0:y1, x0:x1]
        small = cv2.GaussianBlur(cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90)), (3, 3), 0)
        small = small.astype(np.float32)
        self.motion = 0.0 if self.prev is None else float(np.abs(small - self.prev).mean())
        self.prev = small
        if self.motion > 0:
            self.history.append(self.motion)
        if len(self.history) >= 15:
            floor = float(np.percentile(self.history, 20))
            self.threshold = max(self.base_threshold, self.noise_factor * floor)
        if self.motion > self.threshold:
            self.still_since = None
        elif self.still_since is None:
            self.still_since = t
        return self.is_stable(t)

    def is_stable(self, t):
        return self.still_since is not None and t - self.still_since >= self.stable_seconds


def square_features(warped):
    """Per-pixel features used for change detection (L channel and edge strength)."""
    blur = cv2.GaussianBlur(warped, (5, 5), 0)
    L = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    gx = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)
    edges = cv2.GaussianBlur(np.sqrt(gx * gx + gy * gy), (9, 9), 0)
    return L - L.mean(), edges


def change_scores(feat_a, feat_b, inner=0.8):
    """8x8 array (row 0 = rank 8, col 0 = file a) of change scores between two boards."""
    (La, Ea), (Lb, Eb) = feat_a, feat_b
    d = np.abs(La - Lb) + np.abs(Ea - Eb)
    n = d.shape[0]
    s = n // 8
    m = int(s * (1 - inner) / 2)
    return d[:s * 8, :s * 8].reshape(8, s, 8, s)[:, m:s - m, :, m:s - m].mean(axis=(1, 3))


def changed_squares(scores, min_score=25.0, median_factor=3.0, rel_to_max=0.4):
    """Squares whose score clears an absolute, a noise-relative and a max-relative bar."""
    flat = scores.ravel()
    bar = max(min_score, median_factor * float(np.median(flat)), rel_to_max * float(flat.max()))
    return {SQUARE_NAMES[i] for i in np.nonzero(flat >= bar)[0]}

"""Board calibration: 4 corners -> homography -> 64 squares.

Convention for the top-down ("warped") board image, once orientation is right:
white's side is at the bottom, a1 bottom-left, h8 top-right. `rotation`
(0-3, quarter turns) fixes which physical corner is a1; the user picks it by
pressing R until the labels match the real board.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

FILES = "abcdefgh"


def order_clockwise(points):
    """Sort 4 image points clockwise (in screen coordinates), starting top-left."""
    pts = np.asarray(points, dtype=np.float32)
    if pts.shape != (4, 2):
        raise ValueError("Need exactly 4 corner points")
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    pts = pts[np.argsort(ang)]                       # clockwise on screen (y down)
    start = int(np.argmin(pts.sum(axis=1)))         # top-left = smallest x+y
    return np.roll(pts, -start, axis=0)


def square_name(file_idx, rank_idx):
    return f"{FILES[file_idx]}{rank_idx + 1}"


@dataclass
class Calibration:
    corners: list                 # 4 [x, y] points in camera pixels (any click order)
    rotation: int = 0             # quarter turns, 0-3
    warp_size: int = 640
    frame_size: list = field(default_factory=list)   # [width, height] when calibrated
    camera_index: int = 0

    # --- geometry -----------------------------------------------------------
    def src_points(self):
        """Corners in the order that maps to dst TL, TR, BR, BL after rotation."""
        return np.roll(order_clockwise(self.corners), -self.rotation, axis=0)

    def dst_points(self):
        n = self.warp_size
        return np.float32([[0, 0], [n, 0], [n, n], [0, n]])

    def homography(self):
        """Camera pixels -> warped board pixels."""
        return cv2.getPerspectiveTransform(self.src_points(), self.dst_points())

    def inverse_homography(self):
        return cv2.getPerspectiveTransform(self.dst_points(), self.src_points())

    def warp(self, frame):
        n = self.warp_size
        return cv2.warpPerspective(frame, self.homography(), (n, n))

    @property
    def square_px(self):
        return self.warp_size / 8

    def square_rect(self, name):
        """(x0, y0, x1, y1) of a square in the warped image."""
        f, r = FILES.index(name[0]), int(name[1]) - 1
        s = self.square_px
        x0, y0 = f * s, (7 - r) * s
        return x0, y0, x0 + s, y0 + s

    def square_at(self, x, y):
        """Square name at a warped-image pixel, or None if outside the board."""
        s = self.square_px
        f, row = int(x // s), int(y // s)
        if not (0 <= f < 8 and 0 <= row < 8):
            return None
        return square_name(f, 7 - row)

    def grid_in_camera(self):
        """9x9 grid intersection points projected back into the camera image."""
        s = self.square_px
        pts = np.float32([[[i * s, j * s]] for j in range(9) for i in range(9)])
        return cv2.perspectiveTransform(pts, self.inverse_homography()).reshape(9, 9, 2)

    def shadow_map(self, piece_height=1.6, steps=24):
        """For each square, the other squares a standing piece on it hides from the camera.

        A piece's top appears straight above its base in the camera image, so we
        walk upward in the image from the square centre (by `piece_height` x the
        local square size) and map that line back onto the board. Returns
        {square_index (python-chess numbering): set of square indexes}.
        """
        H, Hinv = self.homography(), self.inverse_homography()
        s = self.square_px
        out = {}
        for f in range(8):
            for r in range(8):
                cx, cy = (f + 0.5) * s, (7 - r + 0.5) * s
                pts = cv2.perspectiveTransform(np.float32([[[cx, cy]], [[cx + s, cy]]]), Hinv).reshape(2, 2)
                base, side = pts[0], pts[1]
                size_img = float(np.linalg.norm(side - base))
                line = np.float32([[[base[0], base[1] - size_img * piece_height * k / steps]]
                                   for k in range(1, steps + 1)])
                board_pts = cv2.perspectiveTransform(line, H).reshape(-1, 2)
                hidden = set()
                for x, y in board_pts:
                    name = self.square_at(x, y)
                    if name and name != square_name(f, r):
                        hidden.add((int(name[1]) - 1) * 8 + FILES.index(name[0]))
                out[r * 8 + f] = hidden
        return out

    def camera_to_square(self, x, y):
        p = cv2.perspectiveTransform(np.float32([[[x, y]]]), self.homography())[0, 0]
        return self.square_at(*p)

    # --- persistence -------------------------------------------------------
    def to_dict(self):
        return {
            "corners": [[float(x), float(y)] for x, y in self.corners],
            "rotation": int(self.rotation) % 4,
            "warp_size": int(self.warp_size),
            "frame_size": list(self.frame_size),
            "camera_index": int(self.camera_index),
        }

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"No calibration file at {path}. Run calibrate.py and press S to save.")
        try:
            d = json.loads(path.read_text())
            cal = cls(**d)
            order_clockwise(cal.corners)   # validates shape
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise ValueError(f"Calibration file {path} is invalid ({e}). Recalibrate and save again.")
        return cal


def orientation_check(warped, cal):
    """Sanity hint: on a real board a1 and h8 are dark, a8 and h1 are light.

    Returns (looks_ok, message). Uses the mean brightness of the inner part of
    the 4 corner squares; pieces on them can fool it, so it's only a hint.
    """
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY) if warped.ndim == 3 else warped

    def mean(name):
        x0, y0, x1, y1 = (int(v) for v in cal.square_rect(name))
        m = int((x1 - x0) * 0.3)
        return float(gray[y0 + m:y1 - m, x0 + m:x1 - m].mean())

    dark = (mean("a1") + mean("h8")) / 2
    light = (mean("a8") + mean("h1")) / 2
    if dark < light:
        return True, "a1 is a dark square: OK"
    return False, "a1 looks LIGHT: board is probably rotated 90 deg (press R)"

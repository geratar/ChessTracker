"""Debug drawing for the live camera view and the top-down board view."""
import cv2
import numpy as np

from .calibration import FILES

GREEN, YELLOW, RED, WHITE, BLACK = (0, 220, 0), (0, 220, 255), (0, 0, 255), (255, 255, 255), (0, 0, 0)


def text(img, msg, org, color=WHITE, scale=0.6):
    cv2.putText(img, msg, org, cv2.FONT_HERSHEY_SIMPLEX, scale, BLACK, 3, cv2.LINE_AA)
    cv2.putText(img, msg, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def draw_camera_overlay(frame, corners, cal=None):
    """Clicked corners, and (when calibrated) the projected 8x8 grid + a1 marker."""
    out = frame.copy()
    if cal is not None:
        g = cal.grid_in_camera()
        for i in range(9):
            cv2.polylines(out, [g[i].astype(np.int32)], False, GREEN, 1, cv2.LINE_AA)
            cv2.polylines(out, [g[:, i].astype(np.int32)], False, GREEN, 1, cv2.LINE_AA)
        # label a1 and h8 at their square centres
        for name, (fi, row) in (("a1", (0, 7)), ("h8", (7, 0))):
            c = (g[row, fi] + g[row + 1, fi + 1]) / 2
            text(out, name, (int(c[0]) - 10, int(c[1]) + 5), YELLOW)
    for i, (x, y) in enumerate(corners):
        cv2.circle(out, (int(x), int(y)), 6, RED, 2, cv2.LINE_AA)
        text(out, str(i + 1), (int(x) + 8, int(y) - 8), RED)
    return out


def draw_board_overlay(warped, cal):
    """Grid and square names on the top-down view."""
    out = warped.copy()
    s = cal.square_px
    n = cal.warp_size
    for i in range(9):
        p = int(round(i * s))
        cv2.line(out, (p, 0), (p, n), GREEN, 1)
        cv2.line(out, (0, p), (n, p), GREEN, 1)
    for f in range(8):
        for r in range(8):
            x0, y0, _, _ = cal.square_rect(f"{FILES[f]}{r + 1}")
            text(out, f"{FILES[f]}{r + 1}", (int(x0) + 3, int(y0) + 14), WHITE, 0.4)
    return out

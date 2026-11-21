"""Simple 2D chessboard drawing with OpenCV (no extra GUI libraries)."""
import chess
import cv2
import numpy as np

LIGHT, DARK = (181, 217, 240), (99, 136, 181)
HIGHLIGHT = (80, 200, 120)


def draw_board(board, size=480, last_move=None, highlight=()):
    s = size // 8
    img = np.zeros((s * 8, s * 8, 3), np.uint8)
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        x, y = f * s, (7 - r) * s
        color = LIGHT if (f + r) % 2 else DARK
        if last_move and sq in (last_move.from_square, last_move.to_square):
            color = tuple(int(c * 0.6 + h * 0.4) for c, h in zip(color, HIGHLIGHT))
        cv2.rectangle(img, (x, y), (x + s, y + s), color, -1)
        if sq in highlight:
            cv2.rectangle(img, (x + 2, y + 2), (x + s - 3, y + s - 3), (0, 0, 255), 3)
        p = board.piece_at(sq)
        if p:
            cx, cy = x + s // 2, y + s // 2
            fill, ink = ((245, 245, 245), (20, 20, 20)) if p.color else ((30, 30, 30), (240, 240, 240))
            cv2.circle(img, (cx, cy), int(s * 0.38), fill, -1, cv2.LINE_AA)
            cv2.circle(img, (cx, cy), int(s * 0.38), (90, 90, 90), 1, cv2.LINE_AA)
            letter = p.symbol().upper()
            (tw, th), _ = cv2.getTextSize(letter, cv2.FONT_HERSHEY_DUPLEX, s / 60, 2)
            cv2.putText(img, letter, (cx - tw // 2, cy + th // 2), cv2.FONT_HERSHEY_DUPLEX, s / 60, ink, 2,
                        cv2.LINE_AA)
        if f == 0:
            cv2.putText(img, str(r + 1), (x + 2, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1)
        if r == 0:
            cv2.putText(img, "abcdefgh"[f], (x + s - 12, y + s - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1)
    return img

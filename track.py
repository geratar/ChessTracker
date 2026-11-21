"""Phase 2: live move tracking.

Start with the pieces in the starting position and the board calibrated
(run calibrate.py first). Keep hands off the board for a second at the start.

  python track.py                    live camera
  python track.py --source clip.mp4  replay a recording through the same UI

Keys (click the window first):
  1/2/3  confirm the suggested move when asked     X  nothing happened (dismiss)
  U      undo last move                            N  new game
  S      save PGN to data/games/                   V  start/stop recording
  Q      quit
"""
import argparse
import time

import chess
import chess.pgn
import cv2
import numpy as np

from chesstracker.board_view import draw_board
from chesstracker.calibration import Calibration
from chesstracker.camera import FrameSource
from chesstracker.config import load_config, resolve
from chesstracker.overlay import GREEN, RED, YELLOW, text
from chesstracker.tracker import Tracker

WIN = "Chess tracker"


def save_pgn(board, folder):
    folder.mkdir(parents=True, exist_ok=True)
    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = "Tracked game"
    game.headers["Date"] = time.strftime("%Y.%m.%d")
    p = folder / time.strftime("game_%Y%m%d_%H%M%S.pgn")
    p.write_text(str(game) + "\n")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int)
    ap.add_argument("--source", help="video file instead of the camera")
    args = ap.parse_args()
    cfg = load_config()
    try:
        cal = Calibration.load(resolve(cfg["calibration_path"]))
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(f"{e}\nRun calibrate.py first.")

    source = args.source or (args.camera if args.camera is not None else cfg["camera_index"])
    src = FrameSource(source, cfg["camera_backend"], cfg["frame_width"], cfg["frame_height"],
                      cfg["reconnect_interval_s"])
    fps = src.cap.get(cv2.CAP_PROP_FPS) if (not src.is_camera and src.cap) else None
    tracker = Tracker(cal, cfg)
    status, status_color = "Keep hands off the board...", YELLOW
    writer, i, t0 = None, 0, time.monotonic()
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)

    while True:
        frame = src.read()
        t = (i / fps) if fps else time.monotonic() - t0
        if frame is not None:
            i += 1
            if writer:
                writer.write(frame)
            for ev in tracker.process(frame, t):
                print(f"{t:7.2f}s {ev.kind}: {ev.text}")
                if ev.kind == "move":
                    status, status_color = f"Move: {ev.text}", GREEN
                elif ev.kind == "ready":
                    status, status_color = "Ready. Play!", GREEN
                elif ev.kind in ("ambiguous", "promotion"):
                    opts = "  ".join(f"[{k + 1}] {tracker.board.san(c.move)}"
                                     for k, c in enumerate(ev.candidates[:3]))
                    status, status_color = f"Which move? {opts}  [X] none", RED
                else:
                    status, status_color = ev.text, YELLOW

        cam = frame if frame is not None else np.zeros((cfg["frame_height"], cfg["frame_width"], 3), np.uint8)
        cam = cv2.resize(cam, (640, int(640 * cam.shape[0] / cam.shape[1])))
        if not src.connected:
            text(cam, "CAMERA DISCONNECTED - retrying...", (10, 30), RED, 0.7)
        text(cam, f"motion {tracker.gate.motion:.1f} {'still' if tracker.gate.is_stable(t) else 'moving'}",
             (10, cam.shape[0] - 10), GREEN if tracker.gate.is_stable(t) else YELLOW, 0.5)
        if writer:
            text(cam, "REC", (cam.shape[1] - 60, 25), RED, 0.7)

        last = tracker.board.peek() if tracker.board.move_stack else None
        hl = set()
        if tracker.pending:
            hl = set().union(*[{c.move.from_square, c.move.to_square} for c in tracker.pending.candidates[:1]])
        bv = draw_board(tracker.board, 480, last, hl)
        panel = np.full((max(bv.shape[0], cam.shape[0]) + 60, cam.shape[1] + bv.shape[1] + 20, 3), 32, np.uint8)
        panel[:cam.shape[0], :cam.shape[1]] = cam
        panel[:bv.shape[0], cam.shape[1] + 20:] = bv
        moves = tracker.board.root().variation_san(tracker.board.move_stack)
        text(panel, status, (10, panel.shape[0] - 35), status_color, 0.6)
        text(panel, moves[-110:], (10, panel.shape[0] - 10), (255, 255, 255), 0.45)
        cv2.imshow(WIN, panel)

        key = cv2.waitKey(1 if fps else 10) & 0xFF
        if key in (ord("q"), 27) or cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
            break
        if tracker.pending and key in (ord("1"), ord("2"), ord("3")):
            k = key - ord("1")
            if k < len(tracker.pending.candidates):
                ev = tracker.confirm(tracker.pending.candidates[k].move, t)
                status, status_color = f"Move: {ev.text} (confirmed)", GREEN
        elif key == ord("x"):
            tracker.reject()
            status, status_color = "Dismissed. Position unchanged.", YELLOW
        elif key == ord("u") and tracker.board.move_stack:
            m = tracker.undo()
            status, status_color = f"Undid {m.uci()}. Put the piece(s) back, then continue.", YELLOW
        elif key == ord("n"):
            tracker = Tracker(cal, cfg)
            status, status_color = "New game: set up the start position, hands off...", YELLOW
        elif key == ord("s"):
            p = save_pgn(tracker.board, resolve("data/games"))
            status, status_color = f"Saved {p.name}", GREEN
        elif key == ord("v") and frame is not None:
            if writer:
                writer.release()
                writer = None
            else:
                d = resolve(cfg["recordings_dir"])
                d.mkdir(parents=True, exist_ok=True)
                p = d / time.strftime("rec_%Y%m%d_%H%M%S.mp4")
                writer = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 15, frame.shape[1::-1])
    if writer:
        writer.release()
    src.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

"""Run the move tracker on a recorded video and print what it detects.

  python replay.py data/recordings/rec_xxx.mp4
  python replay.py clip.mp4 --fps 25 --show     (--show opens a debug window)
"""
import argparse

import cv2

from chesstracker.calibration import Calibration
from chesstracker.config import load_config, resolve
from chesstracker.tracker import Tracker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--calibration", help="calibration.json (default: from config)")
    ap.add_argument("--fps", type=float, help="override the video's frame rate")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    cal = Calibration.load(args.calibration or resolve(cfg["calibration_path"]))
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open {args.video}")
    fps = args.fps or cap.get(cv2.CAP_PROP_FPS) or 15
    tracker = Tracker(cal, cfg)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        for ev in tracker.process(frame, t):
            print(f"{t:7.2f}s  frame {i:5d}  {ev.kind:12s} {ev.text}")
            if ev.kind in ("ambiguous", "promotion"):
                best = ev.candidates[0].move
                print(f"{'':22s}(replay auto-confirms {tracker.board.san(best)})")
                tracker.confirm(best, t)
        if args.show:
            view = tracker.aligner.calibration().warp(frame)
            cv2.putText(view, f"motion {tracker.gate.motion:.1f}", (10, 25), 0, 0.7, (0, 0, 255), 2)
            cv2.imshow("replay", view)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        i += 1
    print("\nFinal position:", tracker.board.fen())
    print("Moves:", tracker.board.root().variation_san(tracker.board.move_stack))


if __name__ == "__main__":
    main()

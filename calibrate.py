"""Phase 1: live webcam preview + board calibration.

Run:  python calibrate.py                 (uses camera_index from config)
      python calibrate.py --camera 1
      python calibrate.py --source data/recordings/clip.mp4   (replay a recording)
      python calibrate.py --list           (list cameras and exit)
"""
import argparse
import time

import cv2
import numpy as np

from chesstracker.calibration import Calibration, orientation_check
from chesstracker.camera import FrameSource, list_cameras
from chesstracker.config import load_config, resolve
from chesstracker.overlay import RED, GREEN, YELLOW, draw_board_overlay, draw_camera_overlay, text

HELP = [
    "Click the 4 board corners (outer edge of the playing squares). Drag to adjust.",
    "R rotate a1   U undo   C clear   S save   L load",
    "G snapshot   V record   N/P next/prev camera   Q quit",
]
CAM_WIN, BOARD_WIN = "Camera", "Board (top-down)"
DRAG_RADIUS = 15


class App:
    def __init__(self, cfg, source):
        self.cfg = cfg
        self.cal_path = resolve(cfg["calibration_path"])
        self.rec_dir = resolve(cfg["recordings_dir"])
        self.corners, self.rotation = [], 0
        self.dragging = None
        self.status, self.status_until = "", 0.0
        self.writer = None
        self.frame_size = None
        self.camera_index = source if isinstance(source, int) else cfg["camera_index"]
        self.src = self._open(source)
        self._try_load(quiet=True)

    def _open(self, source):
        return FrameSource(source, self.cfg["camera_backend"], self.cfg["frame_width"],
                           self.cfg["frame_height"], self.cfg["reconnect_interval_s"])

    def say(self, msg, secs=3.0):
        print(msg)
        self.status, self.status_until = msg, time.monotonic() + secs

    def calibration(self):
        if len(self.corners) != 4:
            return None
        return Calibration(self.corners, self.rotation, self.cfg["warp_size_px"],
                           list(self.frame_size or []), self.camera_index)

    # --- mouse -------------------------------------------------------------
    def on_mouse(self, event, x, y, flags, _):
        if event == cv2.EVENT_LBUTTONDOWN:
            for i, (cx, cy) in enumerate(self.corners):
                if (cx - x) ** 2 + (cy - y) ** 2 <= DRAG_RADIUS ** 2:
                    self.dragging = i
                    return
            if len(self.corners) < 4:
                self.corners.append([float(x), float(y)])
        elif event == cv2.EVENT_MOUSEMOVE and self.dragging is not None:
            self.corners[self.dragging] = [float(x), float(y)]
        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging = None
        elif event == cv2.EVENT_RBUTTONDOWN and self.corners:
            self.corners.pop()

    # --- actions -----------------------------------------------------------
    def _try_load(self, quiet=False):
        try:
            cal = Calibration.load(self.cal_path)
        except FileNotFoundError as e:
            if not quiet:
                self.say(str(e))
            return
        except ValueError as e:
            self.say(str(e))
            return
        self.corners, self.rotation = [list(p) for p in cal.corners], cal.rotation
        self.say(f"Loaded calibration from {self.cal_path.name}")

    def save(self):
        cal = self.calibration()
        if cal is None:
            self.say("Click all 4 corners before saving.")
            return
        cal.save(self.cal_path)
        self.say(f"Saved calibration to {self.cal_path}")

    def snapshot(self, frame):
        self.rec_dir.mkdir(parents=True, exist_ok=True)
        p = self.rec_dir / time.strftime("snap_%Y%m%d_%H%M%S.png")
        cv2.imwrite(str(p), frame)
        self.say(f"Saved {p.name}")

    def toggle_record(self, frame):
        if self.writer:
            self.writer.release()
            self.writer = None
            self.say("Recording stopped")
            return
        self.rec_dir.mkdir(parents=True, exist_ok=True)
        p = self.rec_dir / time.strftime("rec_%Y%m%d_%H%M%S.mp4")
        h, w = frame.shape[:2]
        self.writer = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 15, (w, h))
        self.say(f"Recording to {p.name} (press V to stop)")

    def switch_camera(self, step):
        if not self.src.is_camera:
            return
        self.src.release()
        self.camera_index = max(0, self.camera_index + step)
        self.src = self._open(self.camera_index)
        self.say(f"Camera {self.camera_index}" + ("" if self.src.connected else " not available"))

    # --- main loop ---------------------------------------------------------
    def run(self):
        cv2.namedWindow(CAM_WIN, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(CAM_WIN, self.on_mouse)
        last_frame = None
        while True:
            frame = self.src.read()
            if frame is not None:
                last_frame = frame
                self.frame_size = [frame.shape[1], frame.shape[0]]
                if self.writer:
                    self.writer.write(frame)
            if last_frame is None:
                last_frame = np.zeros((self.cfg["frame_height"], self.cfg["frame_width"], 3), np.uint8)

            cal = self.calibration()
            view = draw_camera_overlay(last_frame, self.corners, cal)
            for i, line in enumerate(HELP):
                text(view, line, (10, 25 + 22 * i))
            if not self.src.connected:
                text(view, "CAMERA DISCONNECTED - retrying...", (10, view.shape[0] - 45), RED, 0.8)
            if self.writer:
                text(view, "REC", (view.shape[1] - 70, 30), RED, 0.8)
            if time.monotonic() < self.status_until:
                text(view, self.status, (10, view.shape[0] - 15), YELLOW)
            cv2.imshow(CAM_WIN, view)

            if cal is not None:
                warped = cal.warp(last_frame)
                ok, msg = orientation_check(warped, cal)
                board = draw_board_overlay(warped, cal)
                text(board, msg, (10, board.shape[0] - 10), GREEN if ok else RED)
                cv2.imshow(BOARD_WIN, board)

            key = cv2.waitKey(15) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("r"):
                self.rotation = (self.rotation + 1) % 4
            elif key == ord("u") and self.corners:
                self.corners.pop()
            elif key == ord("c"):
                self.corners = []
                try:
                    cv2.destroyWindow(BOARD_WIN)
                except cv2.error:
                    pass
            elif key == ord("s"):
                self.save()
            elif key == ord("l"):
                self._try_load()
            elif key == ord("g") and frame is not None:
                self.snapshot(frame)
            elif key == ord("v") and last_frame is not None:
                self.toggle_record(last_frame)
            elif key == ord("n"):
                self.switch_camera(+1)
            elif key == ord("p"):
                self.switch_camera(-1)
            # stop if the user closed the camera window
            if cv2.getWindowProperty(CAM_WIN, cv2.WND_PROP_VISIBLE) < 1:
                break
        if self.writer:
            self.writer.release()
        self.src.release()
        cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, help="camera index (overrides config.json)")
    ap.add_argument("--source", help="video or image file instead of a camera")
    ap.add_argument("--list", action="store_true", help="list available cameras and exit")
    args = ap.parse_args()
    cfg = load_config()

    if args.list:
        cams = list_cameras(cfg["max_cameras_to_scan"], cfg["camera_backend"])
        if not cams:
            print("No cameras found. Check the cable and camera permission for your terminal app.")
        for i, w, h in cams:
            print(f"Camera {i}: {w}x{h}")
        return

    source = args.source if args.source else (args.camera if args.camera is not None else cfg["camera_index"])
    app = App(cfg, source)
    if not app.src.connected:
        print(f"Could not open {source!r}. Try: python calibrate.py --list")
        if app.src.is_camera:
            print("On macOS, allow camera access for Terminal in System Settings > Privacy & Security > Camera.")
    app.run()


if __name__ == "__main__":
    main()

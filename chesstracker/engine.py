"""Background worker that owns the camera, calibration and tracker.

The web UI talks to one `Engine` instance. A thread keeps grabbing frames,
runs the tracker while tracking, and keeps the latest JPEGs for the live views.
All public methods are thread-safe.
"""
import json
import threading
import time

import chess
import chess.pgn
import cv2
import numpy as np

from .calibration import Calibration, orientation_check
from .camera import FrameSource, list_cameras
from .config import load_config, resolve
from .overlay import draw_board_overlay, draw_camera_overlay
from .tracker import Tracker

THEMES = {
    "brown": {"square light": "#f0d9b5", "square dark": "#b58863",
              "square light lastmove": "#cdd26a", "square dark lastmove": "#aaa23a"},
    "blue": {"square light": "#dee3e6", "square dark": "#8ca2ad",
             "square light lastmove": "#c3d888", "square dark lastmove": "#92b166"},
    "green": {"square light": "#ebecd0", "square dark": "#779556",
              "square light lastmove": "#f5f682", "square dark lastmove": "#b9ca43"},
}
SETTINGS_DEFAULTS = {"theme": "green", "flipped": False}


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(default)


class Engine:
    def __init__(self, cfg=None, source=None, data_dir=None):
        self.cfg = cfg or load_config()
        self.lock = threading.RLock()
        if data_dir is not None:
            from pathlib import Path
            data_dir = Path(data_dir)
            self.cal_path = data_dir / "calibration.json"
        else:
            data_dir = resolve("data")
            self.cal_path = resolve(self.cfg["calibration_path"])
        self.settings_path = data_dir / "settings.json"
        self.library_dir = data_dir / "library"
        self.settings = {**SETTINGS_DEFAULTS, **read_json(self.settings_path, {})}
        self.camera_index = self.settings.get("camera_index", self.cfg["camera_index"])
        self.src = None
        self.frame = None
        self.frame_size = None
        self.jpeg_camera = None
        self.jpeg_board = None
        self.corners = []
        self.rotation = 0
        self.saved_calibration = None
        try:
            c = Calibration.load(self.cal_path)
            self.corners, self.rotation, self.saved_calibration = [list(p) for p in c.corners], c.rotation, c
        except (FileNotFoundError, ValueError):
            pass
        self.mode = "setup"            # setup | tracking
        self.tracker = None
        self.status = "Choose your camera"
        self.status_kind = "info"
        self.log = []
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self._open_camera(source if source is not None else self.camera_index)
        self.thread.start()

    # --- camera ---------------------------------------------------------------
    def _open_camera(self, index):
        if self.src is not None:
            self.src.release()
        self.source = index
        self.src = FrameSource(index, self.cfg["camera_backend"], self.cfg["frame_width"],
                               self.cfg["frame_height"], self.cfg["reconnect_interval_s"])
        if isinstance(index, int):
            self.camera_index = index

    def scan_cameras(self):
        with self.lock:
            current = self.source
            if self.src.is_camera:
                self.src.release()
            cams = list_cameras(self.cfg["max_cameras_to_scan"], self.cfg["camera_backend"])
            if self.src.is_camera:
                self._open_camera(current)
        return [{"index": i, "label": f"Camera {i} ({w}x{h})"} for i, w, h, _ in cams]

    def select_camera(self, index):
        with self.lock:
            self._open_camera(int(index))
            self._save_settings(camera_index=int(index))

    # --- calibration -----------------------------------------------------------
    def calibration(self):
        if len(self.corners) != 4:
            return None
        return Calibration(self.corners, self.rotation, self.cfg["warp_size_px"],
                           list(self.frame_size or []), self.camera_index)

    def set_corners(self, corners):
        with self.lock:
            self.corners = [[float(x), float(y)] for x, y in corners][:4]

    def rotate(self):
        with self.lock:
            self.rotation = (self.rotation + 1) % 4

    def save_calibration(self):
        with self.lock:
            cal = self.calibration()
            if cal is None:
                raise ValueError("Click all 4 corners first")
            cal.save(self.cal_path)
            self.saved_calibration = cal

    # --- tracking --------------------------------------------------------------
    def start_tracking(self, fen=None):
        with self.lock:
            cal = self.calibration()
            if cal is None:
                raise ValueError("Calibrate the board first")
            board = chess.Board(fen) if fen else chess.Board()
            self.tracker = Tracker(cal, self.cfg, board)
            self.mode = "tracking"
            self._set_status("Keep hands off the board for a moment...", "info")

    def stop_tracking(self):
        with self.lock:
            self.mode = "setup"
            self.tracker = None

    def new_game(self):
        self.start_tracking()

    def confirm(self, index):
        with self.lock:
            t = self.tracker
            if not t or not t.pending:
                return
            cands = t.pending.candidates
            if 0 <= index < len(cands):
                ev = t.confirm(cands[index], time.monotonic())
                self._set_status(f"Move: {ev.text}", "ok")

    def reject(self):
        with self.lock:
            if self.tracker:
                self.tracker.reject()
                self._set_status("OK, position unchanged", "info")

    def undo(self):
        with self.lock:
            if self.tracker and self.tracker.board.move_stack:
                m = self.tracker.undo()
                self._set_status(f"Undid {m.uci()}. Put the piece(s) back.", "warn")

    def manual_move(self, text):
        """Enter a move by hand, e.g. 'e4' or 'g1f3' (used to fix a wrong detection)."""
        with self.lock:
            if not self.tracker:
                raise ValueError("Not tracking")
            move = self._parse(self.tracker.board, text)
            self.tracker.pending = None
            ev = self.tracker.confirm(move, time.monotonic())
            self._set_status(f"Move: {ev.text} (entered)", "ok")

    def correct_last(self, text):
        """Replace the last detected move with the one the user says was played.
        The pieces on the real board stay where they are."""
        with self.lock:
            if not self.tracker or not self.tracker.board.move_stack:
                raise ValueError("No move to correct")
            wrong = self.tracker.board.peek()
            b = self.tracker.board.copy()
            b.pop()
            move = self._parse(b, text)
            self.tracker.undo()
            ev = self.tracker.confirm(move, time.monotonic())
            self._set_status(f"Corrected {wrong.uci()} to {ev.text}", "ok")

    @staticmethod
    def _parse(board, text):
        text = text.strip()
        try:
            move = board.parse_san(text)
        except ValueError:
            try:
                move = chess.Move.from_uci(text)
            except ValueError:
                raise ValueError(f"'{text}' is not a move")
            if move not in board.legal_moves and board.piece_at(move.from_square) and \
                    board.piece_at(move.from_square).piece_type == chess.PAWN and \
                    chess.square_rank(move.to_square) in (0, 7):
                move.promotion = chess.QUEEN
        if move not in board.legal_moves:
            raise ValueError(f"{text} is not a legal move here")
        return move

    def _set_status(self, text, kind):
        self.status, self.status_kind = text, kind

    # --- settings ----------------------------------------------------------------
    def _save_settings(self, **kw):
        self.settings.update(kw)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(self.settings, indent=2))

    def update_settings(self, theme=None, flipped=None):
        with self.lock:
            if theme is not None:
                if theme not in THEMES:
                    raise ValueError(f"Unknown theme {theme}")
                self._save_settings(theme=theme)
            if flipped is not None:
                self._save_settings(flipped=bool(flipped))

    # --- library -----------------------------------------------------------------
    def save_game(self, name):
        with self.lock:
            if not self.tracker:
                raise ValueError("No game to save")
            board = self.tracker.board
            game = chess.pgn.Game.from_board(board)
            name = (name or "").strip() or "Untitled game"
            game.headers["Event"] = name
            game.headers["Date"] = time.strftime("%Y.%m.%d")
            game.headers["Time"] = time.strftime("%H:%M")
            self.library_dir.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name).strip()[:40]
            path = self.library_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{safe}.pgn"
            path.write_text(str(game) + "\n")
            return path.name

    def list_games(self):
        out = []
        for p in sorted(self.library_dir.glob("*.pgn"), reverse=True):
            with open(p) as f:
                g = chess.pgn.read_game(f)
            if g is None:
                continue
            out.append({"id": p.name, "name": g.headers.get("Event", p.stem),
                        "date": g.headers.get("Date", "?").replace(".", "-"),
                        "time": g.headers.get("Time", ""),
                        "moves": len(list(g.mainline_moves()))})
        return out

    def load_game(self, game_id):
        p = (self.library_dir / game_id).resolve()
        if p.parent != self.library_dir.resolve() or not p.exists():
            raise ValueError("Game not found")
        with open(p) as f:
            g = chess.pgn.read_game(f)
        board = g.board()
        plies = [{"fen": board.fen(), "san": None, "uci": None}]
        for m in g.mainline_moves():
            san = board.san(m)
            board.push(m)
            plies.append({"fen": board.fen(), "san": san, "uci": m.uci()})
        return {"id": game_id, "name": g.headers.get("Event", ""), "date": g.headers.get("Date", ""),
                "pgn": str(g), "plies": plies}

    def delete_game(self, game_id):
        p = (self.library_dir / game_id).resolve()
        if p.parent == self.library_dir.resolve() and p.exists():
            p.unlink()

    # --- state for the UI ---------------------------------------------------------
    def state(self):
        with self.lock:
            t = self.tracker
            pending = []
            if t and t.pending:
                pending = [t.describe(c) for c in t.pending.candidates[:3]]
            board = t.board if t else chess.Board()
            cal = self.calibration()
            return {
                "mode": self.mode,
                "camera": {"index": self.camera_index, "connected": bool(self.src and self.src.connected),
                           "frame_size": self.frame_size},
                "calibration": {"corners": self.corners, "rotation": self.rotation,
                                "saved": self.saved_calibration is not None,
                                "orientation_ok": self._orientation_ok(cal)},
                "status": self.status, "status_kind": self.status_kind,
                "fen": board.fen(),
                "lastmove": board.peek().uci() if board.move_stack else None,
                "moves": self._san_list(board),
                "pending": pending,
                "pending_kind": (t.pending.status if t and t.pending else None),
                "still": bool(t and t.gate.is_stable(time.monotonic())),
                "settings": self.settings,
                "themes": list(THEMES),
            }

    @staticmethod
    def _san_list(board):
        b = board.root()
        out = []
        for m in board.move_stack:
            out.append(b.san(m))
            b.push(m)
        return out

    def _orientation_ok(self, cal):
        if cal is None or self.frame is None:
            return None
        try:
            return bool(orientation_check(cal.warp(self.frame), cal)[0])
        except cv2.error:
            return None

    # --- worker thread -----------------------------------------------------------
    def _loop(self):
        while self.running:
            with self.lock:
                src = self.src
            frame = src.read() if src else None
            if frame is None:
                time.sleep(0.05)
                continue
            now = time.monotonic()
            with self.lock:
                self.frame = frame
                self.frame_size = [frame.shape[1], frame.shape[0]]
                if self.mode == "tracking" and self.tracker:
                    for ev in self.tracker.process(frame, now):
                        self._on_event(ev)
                cal = self.calibration()
            cam = draw_camera_overlay(frame, self.corners if self.mode == "setup" else [], cal)
            ok, buf = cv2.imencode(".jpg", cam, [cv2.IMWRITE_JPEG_QUALITY, 75])
            board_jpg = None
            if cal is not None:
                ok2, b = cv2.imencode(".jpg", draw_board_overlay(cal.warp(frame), cal), [cv2.IMWRITE_JPEG_QUALITY, 75])
                board_jpg = b.tobytes() if ok2 else None
            with self.lock:
                self.jpeg_camera = buf.tobytes() if ok else None
                self.jpeg_board = board_jpg
            if src and not src.is_camera:   # play recordings at their real speed
                time.sleep(max(0.0, 1 / 15 - (time.monotonic() - now)))
            else:
                time.sleep(0.01)

    def _on_event(self, ev):
        self.log.append((time.strftime("%H:%M:%S"), ev.kind, ev.text))
        self.log = self.log[-50:]
        if ev.kind == "move":
            self._set_status(f"Move: {ev.text}", "ok")
        elif ev.kind == "ready":
            self._set_status("Ready. Play!", "ok")
        elif ev.kind in ("ambiguous", "promotion", "two_moves"):
            q = "Missed a move? Pick one:" if ev.kind == "two_moves" else "Which move? Pick one:"
            self._set_status(q, "ask")
        else:
            self._set_status(ev.text, "warn")

    def shutdown(self):
        self.running = False
        if self.src:
            self.src.release()

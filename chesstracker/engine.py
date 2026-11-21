"""Background worker that owns the camera, calibration and tracker.

The web UI talks to one `Engine` instance. A thread keeps grabbing frames,
runs the tracker while tracking, and keeps the latest JPEGs for the live views.
All public methods are thread-safe.
"""
import json
import subprocess
import sys
import threading
import time

import chess
import chess.pgn
import cv2
import numpy as np

from .analysis import Analyzer
from .players import Players
from .calibration import Calibration, orientation_check
from .detector import min_square_px
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
SETTINGS_DEFAULTS = {"theme": "green", "flipped": False, "speed": "fast", "detect": "auto", "lost_sound": True}
MAC_ALERT = "/System/Library/Sounds/Sosumi.aiff"


def play_alert():
    """An attention sound on the computer running the app (so it works with the browser in the back)."""
    try:
        if sys.platform == "darwin":
            for _ in range(2):
                subprocess.run(["afplay", MAC_ALERT], timeout=5, check=False)
        elif sys.platform.startswith("win"):
            import winsound
            for _ in range(2):
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                time.sleep(0.4)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass
DETECT_MODES = ("auto", "tap")
# How long the squares of a move must be still before it is read (seconds).
SPEEDS = {"fast": {"stable_seconds": 0.13, "confirm_seconds": 0.0},   # 2 frames: blitz
          "normal": {"stable_seconds": 0.4, "confirm_seconds": 0.3},
          "careful": {"stable_seconds": 0.7, "confirm_seconds": 0.5}}


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
        self.corners_size = None       # frame size the corners were clicked at
        try:
            c = Calibration.load(self.cal_path)
            self.corners, self.rotation, self.saved_calibration = [list(p) for p in c.corners], c.rotation, c
            self.corners_size = list(c.frame_size) or None
        except (FileNotFoundError, ValueError):
            pass
        self.mode = "setup"            # setup | tracking
        self.clock = {"white": 0.0, "black": 0.0}   # thinking time per side (seconds)
        self._clock_t = None
        self.tracker = None
        self.status = "Choose your camera"
        self.status_kind = "info"
        self.log = []
        self.writer = None
        self.rec_path = None
        self.debug_path = data_dir / "debug.log"
        self.data_dir = data_dir
        self.saved_plies = 0           # moves already saved to the library
        self.analyzer = Analyzer(data_dir / "engine", self.library_dir)
        self.players = Players(data_dir / "players.json")
        self._last_alert = -1e9
        self.alert = play_alert          # replaced in tests
        self.game_players = {"white": None, "black": None}   # player ids for the current game
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
            self.corners_size = list(self.frame_size) if self.frame_size else None

    def _rescale_corners(self):
        """Camera now delivers a different resolution: move the corners with it."""
        (w0, h0), (w1, h1) = self.corners_size, self.frame_size
        if self.corners and abs(w0 / h0 - w1 / h1) < 0.02:   # same picture, more pixels
            self.corners = [[x * w1 / w0, y * h1 / h0] for x, y in self.corners]
            self._debug(f"camera resolution {w0}x{h0} -> {w1}x{h1}: corners rescaled")
            if self.tracker:
                self.tracker.retarget(self.calibration())
        elif self.corners:
            self.corners = []
            self._set_status("The camera's picture shape changed. Please mark the board corners again.", "warn")
        self.corners_size = list(self.frame_size)

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
    def start_tracking(self, fen=None, white=None, black=None):
        with self.lock:
            cal = self.calibration()
            if cal is None:
                raise ValueError("Calibrate the board first")
            for pid in (white, black):
                if pid and self.players.get(pid) is None:
                    raise ValueError("Player not found")
            if white and white == black:
                raise ValueError("Pick two different players")
            self.game_players = {"white": white or None, "black": black or None}
            board = chess.Board(fen) if fen else chess.Board()
            self.tracker = Tracker(cal, self._tracker_settings(), board)
            self.saved_plies = 0
            self.tracker.debug = self._debug
            self.clock = {"white": 0.0, "black": 0.0}
            self._clock_t = time.monotonic()
            self._debug(f"--- start tracking fen={board.fen()} corners={cal.corners} rot={cal.rotation} "
                        f"frame={self.frame_size}")
            self.mode = "tracking"
            self._set_status("Keep hands off the board for a moment...", "info")

    def stop_tracking(self):
        with self.lock:
            self.mode = "setup"
            self.tracker = None

    def new_game(self, white=None, black=None):
        self.start_tracking(white=white, black=black)

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

    def _debug(self, text):
        try:
            self.debug_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.debug_path, "a") as f:
                f.write(time.strftime("%H:%M:%S ") + text + "\n")
        except OSError:
            pass

    def toggle_recording(self):
        """Record the raw camera video (for diagnosing detection problems)."""
        with self.lock:
            if self.writer:
                self.writer.release()
                self.writer = None
                self._debug(f"recording stopped {self.rec_path}")
                return {"recording": False, "file": str(self.rec_path)}
            if self.frame is None:
                raise ValueError("No camera picture yet")
            d = self.data_dir / "recordings"
            d.mkdir(parents=True, exist_ok=True)
            self.rec_path = d / time.strftime("rec_%Y%m%d_%H%M%S.mp4")
            h, w = self.frame.shape[:2]
            self.writer = cv2.VideoWriter(str(self.rec_path), cv2.VideoWriter_fourcc(*"mp4v"), 15, (w, h))
            self._rec_next = time.monotonic()
            self._debug(f"recording started {self.rec_path}")
            return {"recording": True, "file": str(self.rec_path)}

    def _set_status(self, text, kind):
        self.status, self.status_kind = text, kind

    # --- settings ----------------------------------------------------------------
    def _save_settings(self, **kw):
        self.settings.update(kw)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(self.settings, indent=2))

    def _tracker_settings(self):
        return {**self.cfg, **SPEEDS.get(self.settings.get("speed"), SPEEDS["normal"]),
                "detect": self.settings.get("detect", "auto")}

    def update_settings(self, theme=None, flipped=None, speed=None, detect=None, lost_sound=None):
        with self.lock:
            if lost_sound is not None:
                self._save_settings(lost_sound=bool(lost_sound))
            if detect is not None:
                if detect not in DETECT_MODES:
                    raise ValueError(f"Unknown mode {detect}")
                self._save_settings(detect=detect)
                if self.tracker:
                    self.tracker.s["detect"] = detect
            if speed is not None:
                if speed not in SPEEDS:
                    raise ValueError(f"Unknown speed {speed}")
                self._save_settings(speed=speed)
                if self.tracker:
                    self.tracker.set_timing(**SPEEDS[speed])
            if theme is not None:
                if theme not in THEMES:
                    raise ValueError(f"Unknown theme {theme}")
                self._save_settings(theme=theme)
            if flipped is not None:
                self._save_settings(flipped=bool(flipped))

    # --- library -----------------------------------------------------------------
    def save_game(self, name, result="*"):
        with self.lock:
            if not self.tracker:
                raise ValueError("No game to save")
            if result not in ("1-0", "0-1", "1/2-1/2", "*"):
                raise ValueError(f"Unknown result {result}")
            board = self.tracker.board
            game = chess.pgn.Game.from_board(board)
            game.headers["Result"] = result
            name = (name or "").strip() or "Untitled game"
            game.headers["Event"] = name
            game.headers["Date"] = time.strftime("%Y.%m.%d")
            game.headers["Time"] = time.strftime("%H:%M")
            for side in ("white", "black"):
                p = self.players.get(self.game_players.get(side)) if self.game_players.get(side) else None
                if p:
                    game.headers[side.capitalize()] = p["name"]
                    game.headers[side.capitalize() + "Avatar"] = str(p["avatar"])
                    game.headers[side.capitalize() + "Id"] = p["id"]
            self.library_dir.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name).strip()[:40]
            path = self.library_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{safe}.pgn"
            path.write_text(str(game) + "\n")
            self.saved_plies = len(board.move_stack)
            return path.name

    def list_games(self):
        out = []
        if not self.library_dir.exists():
            return []
        for p in sorted(self.library_dir.glob("*.pgn"), reverse=True):
            with open(p) as f:
                g = chess.pgn.read_game(f)
            if g is None:
                continue
            out.append({"id": p.name, "name": g.headers.get("Event", p.stem),
                        "date": g.headers.get("Date", "?").replace(".", "-"),
                        "time": g.headers.get("Time", ""),
                        "moves": len(list(g.mainline_moves())),
                        "result": g.headers.get("Result", "*"), **self._game_players(g)})
        return out

    def player_stats(self):
        """Per player: results overall / by colour, head-to-head, first moves and recent games."""
        players = self.players.all()
        by_id = {p["id"]: p for p in players}
        by_name = {p["name"].lower(): p for p in players}
        stats = {p["id"]: {**p, "games": 0, "wins": 0, "losses": 0, "draws": 0, "unfinished": 0,
                           "white": {"games": 0, "wins": 0, "draws": 0, "losses": 0},
                           "black": {"games": 0, "wins": 0, "draws": 0, "losses": 0},
                           "moves": 0, "first": None, "last": None, "opponents": {}, "openings": {},
                           "recent": [], "streak": ""} for p in players}
        files = sorted(self.library_dir.glob("*.pgn")) if self.library_dir.exists() else []
        for f in files:                      # oldest first (file names start with the date)
            with open(f) as fh:
                g = chess.pgn.read_game(fh)
            if g is None:
                continue
            h = g.headers
            ids = {}
            for side in ("white", "black"):
                pid = h.get(side.capitalize() + "Id")
                p = by_id.get(pid) or by_name.get(h.get(side.capitalize(), "").lower())
                ids[side] = p["id"] if p else None
            moves = list(g.mainline_moves())
            result = h.get("Result", "*")
            date = h.get("Date", "?").replace(".", "-")
            for side, other in (("white", "black"), ("black", "white")):
                pid = ids[side]
                if pid is None:
                    continue
                st = stats[pid]
                outcome = {"1-0": "win" if side == "white" else "loss",
                           "0-1": "win" if side == "black" else "loss",
                           "1/2-1/2": "draw"}.get(result, "unfinished")
                st["games"] += 1
                st["moves"] += (len(moves) + 1) // 2
                st[{"win": "wins", "loss": "losses", "draw": "draws", "unfinished": "unfinished"}[outcome]] += 1
                col = st[side]
                col["games"] += 1
                if outcome != "unfinished":
                    col[{"win": "wins", "loss": "losses", "draw": "draws"}[outcome]] += 1
                st["first"] = st["first"] or date
                st["last"] = date
                opp_id = ids[other]
                opp = by_id[opp_id]["name"] if opp_id else (h.get(other.capitalize(), "?") if h.get(other.capitalize(), "?") != "?" else "Anonymous")
                o = st["opponents"].setdefault(opp_id or "anon:" + opp, {"name": opp, "avatar": by_id[opp_id]["avatar"] if opp_id else None,
                                                                        "games": 0, "wins": 0, "draws": 0, "losses": 0})
                o["games"] += 1
                if outcome != "unfinished":
                    o[{"win": "wins", "loss": "losses", "draw": "draws"}[outcome]] += 1
                idx = 0 if side == "white" else 1
                if len(moves) > idx:
                    b = g.board()
                    if idx:
                        b.push(moves[0])
                    san = b.san(moves[idx])
                    key = f"{side}:{san}"
                    st["openings"][key] = st["openings"].get(key, 0) + 1
                if outcome != "unfinished":
                    letter = outcome[0].upper()
                    st["streak"] = (st["streak"] + letter) if st["streak"].endswith(letter) or not st["streak"] else letter
                st["recent"].append({"id": f.name, "name": h.get("Event", f.stem), "date": date,
                                     "colour": side, "opponent": opp, "result": outcome, "moves": len(moves)})
        out = []
        for st in stats.values():
            finished = st["wins"] + st["draws"] + st["losses"]
            st["win_rate"] = round(100 * st["wins"] / finished) if finished else None
            st["score_rate"] = round(100 * (st["wins"] + st["draws"] / 2) / finished) if finished else None
            st["avg_moves"] = round(st["moves"] / st["games"]) if st["games"] else None
            st["opponents"] = sorted(st["opponents"].values(), key=lambda o: -o["games"])
            fav = {}
            for side in ("white", "black"):
                cands = [(n, k.split(":", 1)[1]) for k, n in st["openings"].items() if k.startswith(side)]
                fav[side] = max(cands)[1] if cands else None
            st["favourite"] = fav
            del st["openings"]
            st["streak"] = {"kind": st["streak"][:1], "length": len(st["streak"])} if st["streak"] else None
            st["recent"] = st["recent"][::-1][:10]
            out.append(st)
        return sorted(out, key=lambda x: (-x["games"], x["name"].lower()))

    @staticmethod
    def _game_players(g):
        out = {}
        for side in ("white", "black"):
            name = g.headers.get(side.capitalize(), "?")
            av = g.headers.get(side.capitalize() + "Avatar", "")
            out[side] = ({"name": name, "avatar": int(av) if av.isdigit() else None}
                         if name and name != "?" else None)
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
                "result": g.headers.get("Result", "*"), "pgn": str(g), "plies": plies,
                **self._game_players(g)}

    def analyze(self, game_id):
        g = self.load_game(game_id)
        self.analyzer.start(game_id, [p["fen"] for p in g["plies"]])

    def analysis(self, game_id):
        self.load_game(game_id)   # validates the id
        return self.analyzer.status(game_id)

    def rename_game(self, game_id, name):
        name = (name or "").strip()
        if not name:
            raise ValueError("The name can't be empty")
        p = (self.library_dir / game_id).resolve()
        if p.parent != self.library_dir.resolve() or not p.exists():
            raise ValueError("Game not found")
        with self.lock:
            with open(p) as f:
                g = chess.pgn.read_game(f)
            g.headers["Event"] = name
            p.write_text(str(g) + "\n")   # same file name, so the saved analysis stays linked

    def delete_game(self, game_id):
        p = (self.library_dir / game_id).resolve()
        if p.parent == self.library_dir.resolve() and p.exists():
            p.unlink()
            a = self.analyzer.result_path(game_id)
            if a.exists():
                a.unlink()

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
                                "orientation_ok": self._orientation_ok(cal),
                                "square_px": round(min_square_px(self.corners)) if len(self.corners) == 4 else None},
                "status": self.status, "status_kind": self.status_kind,
                "fen": board.fen(),
                "lastmove": board.peek().uci() if board.move_stack else None,
                "moves": self._san_list(board),
                "pending": pending,
                "pending_kind": (t.pending.status if t and t.pending else None),
                "still": bool(t and t.is_still(time.monotonic())),
                "settings": self.settings,
                "recording": self.writer is not None,
                "clock": self._clock_state(),
                "players": {side: self.players.get(pid) if pid else None
                            for side, pid in self.game_players.items()},
                "unsaved": bool(t and len(t.board.move_stack) > self.saved_plies),
                "outcome": board.result() if board.is_game_over() else "*",
                "themes": list(THEMES),
            }

    def _clock_state(self):
        self._tick()
        t = self.tracker
        return {**{k: round(v, 1) for k, v in self.clock.items()},
                "turn": ("white" if t.board.turn == chess.WHITE else "black") if t else None,
                "reading": bool(t and t.tap_at is not None)}

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
                if self.corners_size and self.corners_size != self.frame_size:
                    self._rescale_corners()
                if self.writer and now >= self._rec_next:   # steady 15 fps in the file
                    self.writer.write(frame)
                    self._rec_next = max(self._rec_next + 1 / 15, now - 0.2)
                if self.mode == "tracking" and self.tracker:
                    self._tick()
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

    def tap(self):
        """'Move done' (Space / big button): read the board now, like pressing a chess clock."""
        with self.lock:
            if not self.tracker:
                raise ValueError("Not tracking")
            self._tick()
            self._debug("tap")
            self.tracker.tap(time.monotonic())
            self._set_status("Reading the move...", "info")

    def _tick(self):
        if self.tracker is None or self._clock_t is None:
            return
        now = time.monotonic()
        side = "white" if self.tracker.board.turn == chess.WHITE else "black"
        if not self.tracker.board.is_game_over():
            self.clock[side] += now - self._clock_t
        self._clock_t = now

    def _on_event(self, ev):
        self._debug(f"event {ev.kind}: {ev.text}")
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
            if ev.kind == "lost":
                self._lost_alert()

    def _lost_alert(self):
        now = time.monotonic()
        if not self.settings.get("lost_sound", True) or now - self._last_alert < 20:
            return
        self._last_alert = now
        threading.Thread(target=self.alert, daemon=True).start()

    def test_sound(self):
        threading.Thread(target=self.alert, daemon=True).start()

    def shutdown(self):
        self.running = False
        self.analyzer.close()
        if self.writer:
            self.writer.release()
        if self.src:
            self.src.release()

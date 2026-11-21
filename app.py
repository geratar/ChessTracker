"""ChessEmeg app: opens in your web browser (runs locally, no internet needed).

  python app.py            then open http://localhost:8765 (opens automatically)
"""
import argparse
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import chess
import chess.svg

from chesstracker import updater
from chesstracker.engine import THEMES, Engine

WEB = Path(__file__).resolve().parent / "chesstracker" / "web"
ENGINE = None
CONTENT_TYPES = {".html": "text/html", ".js": "application/javascript", ".css": "text/css",
                 ".svg": "image/svg+xml", ".png": "image/png"}


def board_svg(fen, lastmove=None, theme="green", flipped=False, size=560, arrow=None):
    board = chess.Board(fen)
    lm = chess.Move.from_uci(lastmove) if lastmove else None
    arrows = []
    if arrow:
        a = chess.Move.from_uci(arrow)
        arrows = [chess.svg.Arrow(a.from_square, a.to_square, color="#3b82f6cc")]
    check = board.king(board.turn) if board.is_check() else None
    colors = dict(THEMES.get(theme, THEMES["green"]))
    colors.update({"margin": "#302e2b", "coord": "#bababa"})
    return chess.svg.board(board, lastmove=lm, check=check, size=size, arrows=arrows,
                           orientation=chess.BLACK if flipped else chess.WHITE, colors=colors)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        e = ENGINE
        if url.path in ("/", "/index.html"):
            return self._file(WEB / "index.html")
        if url.path.startswith("/static/"):
            return self._file(WEB / url.path[len("/static/"):])
        if url.path == "/api/state":
            return self._send(200, {**e.state(), "started": STARTED})
        if url.path == "/api/update/check":
            return self._send(200, check_update(force=q.get("force") == "1"))
        if url.path == "/api/board.svg":
            s = e.settings
            fen = q.get("fen") or e.state()["fen"]
            flipped = q.get("flipped", str(s.get("flipped", False))).lower() == "true"
            try:
                svg = board_svg(fen, q.get("lastmove"), q.get("theme", s.get("theme")), flipped,
                                arrow=q.get("arrow"))
            except ValueError as err:
                return self._send(400, {"error": str(err)})
            return self._send(200, svg, "image/svg+xml")
        if url.path == "/api/library":
            return self._send(200, e.list_games())
        if url.path == "/api/game":
            try:
                return self._send(200, e.load_game(q.get("id", "")))
            except ValueError as err:
                return self._send(404, {"error": str(err)})
        if url.path == "/api/analysis":
            try:
                return self._send(200, e.analysis(q.get("id", "")))
            except ValueError as err:
                return self._send(404, {"error": str(err)})
        if url.path == "/stream.mjpg":
            return self._stream(q.get("view", "camera"))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        e = ENGINE
        path = urlparse(self.path).path
        try:
            d = self._json_body()
            actions = {
                "/api/cameras": lambda: e.scan_cameras(),
                "/api/camera": lambda: e.select_camera(d["index"]),
                "/api/corners": lambda: e.set_corners(d["corners"]),
                "/api/rotate": lambda: e.rotate(),
                "/api/calibration/save": lambda: e.save_calibration(),
                "/api/tracking/start": lambda: e.start_tracking(d.get("fen")),
                "/api/tracking/stop": lambda: e.stop_tracking(),
                "/api/new_game": lambda: e.new_game(),
                "/api/confirm": lambda: e.confirm(int(d["index"])),
                "/api/reject": lambda: e.reject(),
                "/api/undo": lambda: e.undo(),
                "/api/move": lambda: e.manual_move(d["move"]),
                "/api/correct": lambda: e.correct_last(d["move"]),
                "/api/settings": lambda: e.update_settings(d.get("theme"), d.get("flipped"), d.get("speed"), d.get("detect")),
                "/api/library/save": lambda: {"id": e.save_game(d.get("name"), d.get("result", "*"))},
                "/api/analyze": lambda: e.analyze(d["id"]),
                "/api/library/delete": lambda: e.delete_game(d["id"]),
                "/api/library/rename": lambda: e.rename_game(d["id"], d.get("name")),
                "/api/record": lambda: e.toggle_recording(),
                "/api/tap": lambda: e.tap(),
                "/api/update/apply": lambda: apply_update(),
            }
            if path not in actions:
                return self._send(404, {"error": "not found"})
            result = actions[path]()
            return self._send(200, result if result is not None else {"ok": True})
        except (ValueError, KeyError) as err:
            return self._send(400, {"error": str(err)})

    def _file(self, path):
        path = path.resolve()
        if WEB.resolve() not in path.parents and path != WEB.resolve() or not path.is_file():
            return self._send(404, {"error": "not found"})
        self._send(200, path.read_bytes(), CONTENT_TYPES.get(path.suffix, "application/octet-stream"))

    def _stream(self, view):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        last = None
        try:
            while ENGINE.running:
                jpg = ENGINE.jpeg_board if view == "board" else ENGINE.jpeg_camera
                if jpg is not None and jpg is not last:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                     str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                    last = jpg
                time.sleep(0.07)
        except (BrokenPipeError, ConnectionResetError):
            pass


STARTED = time.time()
_update = {"t": 0, "result": None}


def check_update(force=False):
    if force or _update["result"] is None or time.time() - _update["t"] > 600:
        _update["result"], _update["t"] = updater.check(), time.time()
    return _update["result"]


def apply_update():
    info = check_update(force=True)
    if info.get("error"):
        raise ValueError(info["error"])
    if not info.get("available"):
        return {"updated": False}
    reqs = updater.apply(info["commit"], info["files"])
    print(f"Updated {len(info['files'])} files. Restarting...")

    def restart():
        time.sleep(0.5)                 # let the reply reach the browser
        if reqs:
            print("Installing new requirements...")
            updater.install_requirements()
        ENGINE.shutdown()               # free the camera for the new process
        updater.restart()
    threading.Thread(target=restart, daemon=True).start()
    return {"updated": True, "files": len(info["files"])}


def main():
    global ENGINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--source", help="video file instead of the camera (for testing)")
    args = ap.parse_args()
    ENGINE = Engine(source=args.source)
    for attempt in range(20):          # after an update the old process may still hold the port
        try:
            server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
            break
        except OSError:
            if attempt == 19:
                raise
            time.sleep(0.5)
    server.daemon_threads = True
    url = f"http://localhost:{args.port}"
    print(f"ChessEmeg is running at {url}  (close this window to quit)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ENGINE.shutdown()


if __name__ == "__main__":
    main()

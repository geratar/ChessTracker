"""Stockfish: find or download the engine, and analyse saved games.

The engine is downloaded automatically the first time (from the official
Stockfish GitHub releases) into data/engine/, so nothing has to be installed.
"""
import io
import json
import os
import platform
import shutil
import ssl
import stat
import subprocess
import tarfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import chess
import chess.engine

RELEASE_API = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
MATE_CP = 10000


# --- finding / installing the engine ------------------------------------------------
def find_stockfish(engine_dir):
    engine_dir = Path(engine_dir)
    if engine_dir.exists():
        for p in sorted(engine_dir.iterdir()):
            if p.name.startswith("stockfish") and p.is_file() and os.access(p, os.X_OK):
                return str(p)
    for cand in (shutil.which("stockfish"), "/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish",
                 "/usr/games/stockfish"):
        if cand and Path(cand).is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def choose_asset(names, system=None, machine=None):
    """Pick the best release file for this computer from the release's file names."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    key = {"darwin": "macos", "windows": "windows", "linux": "ubuntu"}.get(system, system)
    alt = {"ubuntu": "linux"}.get(key)
    ours = [n for n in names if key in n.lower() or (alt and alt in n.lower())]
    arm = machine in ("arm64", "aarch64")
    prefs = (["universal", "apple-silicon", "m1", "arm64"] if arm and key == "macos" else
             ["arm64", "universal"] if arm else
             ["x86-64-universal", "universal", "x86-64-avx2", "x86-64-sse41-popcnt", "x86-64-modern", "x86-64"])
    for p in prefs:
        for n in ours:
            if p in n.lower() and not (not arm and ("arm" in n.lower() or "apple" in n.lower())):
                return n
    return None


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "ChessTracker", **({"Accept": accept} if accept else {})})
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError:
        raise                      # the server answered (e.g. 404): curl would only hide that
    except Exception:
        if shutil.which("curl"):   # macOS system curl uses the system certificates
            return subprocess.run(["curl", "-fsSL", "-A", "ChessTracker", url], check=True,
                                  capture_output=True, timeout=300).stdout
        raise


def install_from_archive(data, name, engine_dir):
    """Extract the stockfish executable from a release archive into engine_dir."""
    engine_dir = Path(engine_dir)
    engine_dir.mkdir(parents=True, exist_ok=True)
    members = []
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                base = Path(info.filename).name
                if base.startswith("stockfish") and not info.is_dir() and (base.endswith(".exe") or "." not in base):
                    members.append((base, z.read(info)))
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                base = Path(m.name).name
                if m.isfile() and base.startswith("stockfish") and "." not in base.replace(".exe", ""):
                    members.append((base, t.extractfile(m).read()))
    if not members:
        raise RuntimeError(f"No stockfish program found inside {name}")
    base, blob = max(members, key=lambda x: len(x[1]))   # the engine is by far the biggest file
    target = engine_dir / ("stockfish.exe" if base.endswith(".exe") else "stockfish")
    target.write_bytes(blob)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(target)


def download_stockfish(engine_dir, progress=lambda msg: None):
    progress("Looking up the latest Stockfish...")
    rel = json.loads(_fetch(RELEASE_API, "application/vnd.github+json"))
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    name = choose_asset(list(assets))
    if not name:
        raise RuntimeError("No Stockfish download found for this computer")
    progress(f"Downloading {name} (one time only)...")
    path = install_from_archive(_fetch(assets[name]), name, engine_dir)
    progress("Stockfish installed")
    return path


# --- analysis ------------------------------------------------------------------------------
def _cp(score):
    """Score from White's point of view as centipawns (mates become +-10000)."""
    w = score.white()
    if w.is_mate():
        m = w.mate()
        return MATE_CP if m > 0 else -MATE_CP
    return w.score()


def classify(loss):
    if loss >= 300:
        return "??"
    if loss >= 100:
        return "?"
    if loss >= 50:
        return "?!"
    return ""


def analyse_positions(engine_path, fens, seconds=0.3, progress=lambda done, total: None):
    """Evaluate each position. Returns a list of dicts (one per position)."""
    out = []
    with chess.engine.SimpleEngine.popen_uci(engine_path) as eng:
        for i, fen in enumerate(fens):
            board = chess.Board(fen)
            if board.is_game_over():
                res = board.result()
                cp = MATE_CP if res == "1-0" else -MATE_CP if res == "0-1" else 0
                out.append({"cp": cp, "mate": None, "best": None, "best_san": None, "pv": ""})
            else:
                info = eng.analyse(board, chess.engine.Limit(time=seconds))
                score = info["score"]
                pv = info.get("pv", [])[:6]
                mate = score.white().mate() if score.white().is_mate() else None
                out.append({"cp": _cp(score), "mate": mate,
                            "best": pv[0].uci() if pv else None,
                            "best_san": board.san(pv[0]) if pv else None,
                            "pv": board.variation_san(pv) if pv else ""})
            progress(i + 1, len(fens))
    return out


def annotate(fens, evals):
    """Per move: how much the mover lost (centipawns) and a ??/?/?! mark."""
    moves = []
    for i in range(1, len(fens)):
        white_moved = chess.Board(fens[i - 1]).turn == chess.WHITE
        before, after = evals[i - 1]["cp"], evals[i]["cp"]
        loss = (before - after) if white_moved else (after - before)
        loss = max(0, min(loss, 2000))
        moves.append({"loss": loss, "mark": classify(loss), "best_san": evals[i - 1]["best_san"]})
    return moves


class Analyzer:
    """Runs one analysis at a time in the background; results cached as JSON."""

    def __init__(self, engine_dir, library_dir, seconds=0.3):
        self.engine_dir = Path(engine_dir)
        self.library_dir = Path(library_dir)
        self.seconds = seconds
        self.jobs = {}
        self.lock = threading.Lock()

    def result_path(self, game_id):
        return self.library_dir / (Path(game_id).stem + ".analysis.json")

    def status(self, game_id):
        with self.lock:
            job = dict(self.jobs.get(game_id, {}))
        if not job:
            p = self.result_path(game_id)
            if p.exists():
                return {"state": "done", "result": json.loads(p.read_text())}
            return {"state": "none"}
        if job.get("state") == "done":
            job["result"] = json.loads(self.result_path(game_id).read_text())
        return job

    def start(self, game_id, fens):
        with self.lock:
            if self.jobs.get(game_id, {}).get("state") in ("downloading", "running"):
                return
            self.jobs[game_id] = {"state": "running", "progress": 0.0, "message": "Starting..."}
        threading.Thread(target=self._run, args=(game_id, fens), daemon=True).start()

    def _set(self, game_id, **kw):
        with self.lock:
            self.jobs[game_id].update(kw)

    def _run(self, game_id, fens):
        try:
            path = find_stockfish(self.engine_dir)
            if not path:
                self._set(game_id, state="downloading")
                path = download_stockfish(self.engine_dir, lambda m: self._set(game_id, message=m))
            self._set(game_id, state="running", message="Analysing...")
            evals = analyse_positions(path, fens, self.seconds,
                                      lambda d, t: self._set(game_id, progress=d / t,
                                                             message=f"Analysing position {d} of {t}"))
            result = {"evals": evals, "moves": annotate(fens, evals), "engine": Path(path).name}
            self.result_path(game_id).write_text(json.dumps(result))
            self._set(game_id, state="done", progress=1.0, message="Done")
        except Exception as e:  # report any failure to the UI instead of crashing
            self._set(game_id, state="error", message=f"Analysis failed: {e}")

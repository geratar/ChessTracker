"""Update the app in place from GitHub, without git, tokens or a browser download.

Files Python writes are not quarantined by macOS, so after one update the
"Privacy & Security -> Open Anyway" step is never needed again. Your `data`
folder, `.venv` and `config.json` are never touched.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from .analysis import _fetch
from .config import ROOT

REPO = "geratar/ChessTracker"
BRANCH = "main"
KEEP = ("data/", ".venv/", "config.json", ".git/")


def blob_sha(data):
    """Git's id for a file's content, so we can compare without git."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _skip(path):
    return any(path == k.rstrip("/") or path.startswith(k) for k in KEEP)


def local_differs(path, sha, root=ROOT):
    p = Path(root) / path
    if not p.is_file():
        return True
    data = p.read_bytes()
    # Windows may have converted line endings; compare both forms.
    return sha not in (blob_sha(data), blob_sha(data.replace(b"\r\n", b"\n")))


def check(root=ROOT, fetch=_fetch):
    """Return {available, files, commit, message, date} for the latest version on GitHub."""
    try:
        info = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"))
        sha = info["sha"]
        tree = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/trees/{sha}?recursive=1"))
    except Exception as e:  # noqa: BLE001 - shown to the user
        msg = str(e)
        if "404" in msg:
            msg = "The GitHub repository is private, so the app can't see updates. Make it public to enable this."
        return {"available": False, "error": msg}
    files = [t["path"] for t in tree.get("tree", [])
             if t["type"] == "blob" and not _skip(t["path"]) and local_differs(t["path"], t["sha"], root)]
    c = info.get("commit", {})
    return {"available": bool(files), "files": files, "commit": sha,
            "message": (c.get("message") or "").splitlines()[0] if c.get("message") else "",
            "date": (c.get("committer") or {}).get("date", "")}


def apply(commit, files, root=ROOT, fetch=_fetch):
    """Download the version `commit` and write the changed `files`. Returns True if requirements changed."""
    data = fetch(f"https://codeload.github.com/{REPO}/zip/{commit}")
    root = Path(root)
    wanted = set(files)
    reqs_changed = False
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir() or "/" not in info.filename:
                continue
            rel = info.filename.split("/", 1)[1]          # drop "ChessTracker-<sha>/"
            if rel not in wanted or _skip(rel):
                continue
            dest = (root / rel).resolve()
            if root.resolve() not in dest.parents:        # never write outside the app folder
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = z.read(info)
            tmp = dest.with_name(dest.name + ".updating")
            tmp.write_bytes(content)
            mode = (info.external_attr >> 16) & 0o777
            if dest.exists():
                mode = mode or dest.stat().st_mode & 0o777
            if rel.endswith((".command", ".sh")):
                mode = 0o755
            if mode and os.name != "nt":
                os.chmod(tmp, mode)
            os.replace(tmp, dest)
            reqs_changed |= rel == "requirements.txt"
    return reqs_changed


def install_requirements(root=ROOT):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(Path(root) / "requirements.txt")],
                   check=False, timeout=600)


def restart():
    """Start the updated app in place of this one (same window, no new browser tab)."""
    args = [a for a in sys.argv if a != "--no-browser"] + ["--no-browser"]
    if os.name == "nt":
        subprocess.Popen([sys.executable] + args)
        os._exit(0)
    os.execv(sys.executable, [sys.executable] + args)

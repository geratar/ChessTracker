"""In-app updater, against a fake GitHub (no network)."""
import io
import json
import os
import zipfile

from chesstracker import updater


def fake_github(files, sha="abc123"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for path, data in files.items():
            info = zipfile.ZipInfo(f"ChessTracker-{sha}/{path}")
            info.external_attr = (0o755 if path.endswith(".command") else 0o644) << 16
            z.writestr(info, data)
    tree = {"tree": [{"path": p, "type": "blob", "sha": updater.blob_sha(d)} for p, d in files.items()]}
    commit = {"sha": sha, "commit": {"message": "Better tracking\n\nmore", "committer": {"date": "2026-11-21T12:00:00Z"}}}

    def fetch(url, accept=None):
        if "/git/trees/" in url:
            return json.dumps(tree).encode()
        if "/commits/" in url:
            return json.dumps(commit).encode()
        assert url.endswith(f"/zip/{sha}")
        return buf.getvalue()
    return fetch


def test_update_writes_changed_files_and_keeps_data(tmp_path):
    (tmp_path / "app.py").write_bytes(b"old\n")
    (tmp_path / "same.txt").write_bytes(b"same\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "calibration.json").write_text("mine")
    remote = {"app.py": b"new\n", "same.txt": b"same\n", "ChessTracker.command": b"#!/bin/bash\n",
              "chesstracker/new.py": b"x = 1\n", "data/calibration.json": b"theirs", "requirements.txt": b"a\n"}
    fetch = fake_github(remote)
    info = updater.check(tmp_path, fetch)
    assert info["available"] and info["message"] == "Better tracking"
    assert set(info["files"]) == {"app.py", "ChessTracker.command", "chesstracker/new.py", "requirements.txt"}
    assert updater.apply(info["commit"], info["files"], tmp_path, fetch) is True
    assert (tmp_path / "app.py").read_bytes() == b"new\n"
    assert (tmp_path / "chesstracker" / "new.py").exists()
    assert (tmp_path / "data" / "calibration.json").read_text() == "mine"
    if os.name != "nt":
        assert os.stat(tmp_path / "ChessTracker.command").st_mode & 0o111
    assert updater.check(tmp_path, fetch)["available"] is False


def test_windows_line_endings_count_as_same(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x\r\ny\r\n")
    assert updater.check(tmp_path, fake_github({"a.py": b"x\ny\n"}))["available"] is False


def test_private_repo_gives_a_clear_message(tmp_path):
    def fetch(url, accept=None):
        raise RuntimeError("HTTP Error 404: Not Found")
    r = updater.check(tmp_path, fetch)
    assert not r["available"] and "private" in r["error"]


def test_network_errors_are_explained(tmp_path):
    def fetch(url, accept=None):
        raise OSError("Command ['curl'] returned non-zero exit status 56.")
    r = updater.check(tmp_path, fetch)
    assert "internet" in r["error"]

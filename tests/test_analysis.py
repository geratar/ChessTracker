import io
import tarfile
import zipfile

import chess
import pytest

from chesstracker import analysis
from chesstracker.analysis import annotate, choose_asset, classify, find_stockfish, install_from_archive

OLD = ["stockfish-macos-m1-apple-silicon.tar", "stockfish-macos-x86-64-avx2.tar",
       "stockfish-macos-x86-64-sse41-popcnt.tar", "stockfish-windows-x86-64-avx2.zip",
       "stockfish-ubuntu-x86-64-avx2.tar", "stockfish-android-armv8.tar"]
NEW = ["stockfish-macos-universal.tar.gz", "stockfish-windows-x86-64-universal.zip",
       "stockfish-linux-x86-64-universal.tar.gz", "stockfish-linux-arm64-universal.tar.gz",
       "stockfish-windows-arm64-universal.zip"]


def test_choose_asset_old_and_new_release_names():
    assert choose_asset(OLD, "Darwin", "arm64") == "stockfish-macos-m1-apple-silicon.tar"
    assert choose_asset(OLD, "Darwin", "x86_64") == "stockfish-macos-x86-64-avx2.tar"
    assert choose_asset(OLD, "Windows", "AMD64") == "stockfish-windows-x86-64-avx2.zip"
    assert choose_asset(NEW, "Darwin", "arm64") == "stockfish-macos-universal.tar.gz"
    assert choose_asset(NEW, "Darwin", "x86_64") == "stockfish-macos-universal.tar.gz"
    assert choose_asset(NEW, "Windows", "AMD64") == "stockfish-windows-x86-64-universal.zip"
    assert choose_asset(NEW, "Linux", "x86_64") == "stockfish-linux-x86-64-universal.tar.gz"


def test_install_from_tar_and_zip(tmp_path):
    blob = b"#!/bin/sh\n" + b"x" * 1000
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in (("stockfish/stockfish-macos-universal", blob), ("stockfish/README.md", b"hi")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    p = install_from_archive(buf.getvalue(), "stockfish-macos-universal.tar.gz", tmp_path / "e1")
    assert open(p, "rb").read() == blob and find_stockfish(tmp_path / "e1") == p

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("stockfish/stockfish-windows-x86-64-avx2.exe", blob)
        z.writestr("stockfish/AUTHORS", b"a")
    p = install_from_archive(zbuf.getvalue(), "stockfish-windows-x86-64-avx2.zip", tmp_path / "e2")
    assert p.endswith("stockfish.exe")


def test_classify_and_annotate():
    assert classify(350) == "??" and classify(150) == "?" and classify(60) == "?!" and classify(10) == ""
    b = chess.Board()
    fens = [b.fen()]
    b.push_san("e4"); fens.append(b.fen())
    b.push_san("f6"); fens.append(b.fen())
    evals = [{"cp": 30, "best_san": "e4"}, {"cp": 35, "best_san": "e5"}, {"cp": 200, "best_san": "d4"}]
    moves = annotate(fens, evals)
    assert moves[0]["mark"] == "" and moves[1]["mark"] == "?" and moves[1]["best_san"] == "e5"


@pytest.mark.skipif(find_stockfish("/nonexistent") is None, reason="no stockfish on this machine")
def test_real_engine_finds_mate_in_one():
    b = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")   # Rd8#
    ev = analysis.analyse_positions(find_stockfish("/nonexistent"), [b.fen()], seconds=0.2)
    assert ev[0]["best_san"] == "Rd8#" and ev[0]["cp"] == analysis.MATE_CP

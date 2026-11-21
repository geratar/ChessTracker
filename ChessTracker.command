#!/bin/bash
# macOS: double-click to open ChessEmeg. Keep this window open while you play.
cd "$(dirname "$0")"
PY=""
for p in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if [ -x "$p" ]; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python is not installed. Get the macOS installer from https://www.python.org/downloads/"
  echo "Press any key to close."; read -n 1; exit 1
fi
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import cv2, chess, certifi" 2>/dev/null; then
  echo "First start: setting up (about a minute)..."
  rm -rf .venv
  "$PY" -m venv .venv && .venv/bin/pip install -q -r requirements.txt || { echo "Setup failed (see above). Press any key."; read -n 1; exit 1; }
fi
echo "Opening ChessEmeg in your browser. Keep this window open; close it to quit."
.venv/bin/python app.py "$@"

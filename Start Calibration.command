#!/bin/bash
# macOS: double-click to run calibrate.py. First run sets everything up.
cd "$(dirname "$0")"
PY=""
for p in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if [ -x "$p" ]; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python is not installed. Get the macOS installer from https://www.python.org/downloads/"
  echo "Press any key to close."; read -n 1; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up (about a minute)..."
  rm -rf .venv
  "$PY" -m venv .venv && .venv/bin/pip install -q -r requirements.txt || { echo "Setup failed (see above). Press any key."; read -n 1; exit 1; }
fi
.venv/bin/python calibrate.py "$@"

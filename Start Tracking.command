#!/bin/bash
# macOS: double-click to start move tracking.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: setting up (takes a minute)..."
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || { echo "Setup failed. Is Python 3 installed? See README.md"; read -n 1; exit 1; }
fi
.venv/bin/python track.py "$@"

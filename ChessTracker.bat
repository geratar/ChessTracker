@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First start: setting up...
  py -m venv .venv
  .venv\Scripts\python -m pip install -q -r requirements.txt
)
echo Opening ChessEmeg in your browser. Keep this window open; close it to quit.
.venv\Scripts\python app.py
pause
